import sys
import os

# Add current directory to Python path for module imports
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Body
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import uvicorn
from typing import Optional
from functools import lru_cache
import asyncio
import json
import logging
from datetime import datetime
from collections import deque
import cv2

from models import (
    TemperatureCommand, FanCommand, HotPlateCommand, 
    SystemStatus, ArduinoResponse, DeviceStatus,
    ReconnectRequest, HotPlateToggleRequest, DataCaptureRequest, DataPointWithImage,
    Cn2TargetRequest
)
from arduino_comm import arduino_comm
from camera_acquisition import BaslerCamera, PYLON_AVAILABLE
from cn2.cn2_optical import CN2OpticalCalculator
from cn2.cn2_thermal import calculate_cn2
from cn2.cn2_controller import Cn2Controller
from calibration.calibration_agent import CalibrationAgent
from calibration.models import CalibrationRequest, CalibrationControl
from calibration.config import CalibrationConfig
from csv_utils import init_csv_file, append_to_csv
from utils import load_configuration, get_configuration, set_configuration, get_workspace_root, get_calibration_data_folder, create_capture_folder, calculate_beam_centroid
from ws_connection_manager import ConnectionManager
from ws_video_stream_manager import VideoStreamManager
from ws_calibration_manager import CalibrationConnectionManager
from arduino_comm import apply_settings_to_arduino
from constants import (
    CAMERA_IMAGES_FOLDER, CAMERA_FILENAME_FORMAT, CAMERA_VIDEO_FRAME_DELAY,
    CENTROID_HISTORY_THRESHOLD, CN2_ROW1_500_INDEX, CN2_ROW1_300_INDEX,
    CN2_ROW2_500_INDEX, CN2_ROW2_300_INDEX, FAN_SPEED_MAX, HOT_PLATE_ID_MAX,
    HOT_PLATE_ID_MIN, MAX_HISTORY_SIZE, POLLING_INTERVAL_DEFAULT,
    CALIBRATION_WINDFLOW_FAN_SPEED_STEP_DEFAULT,
    CALIBRATION_WINDFLOW_SETTLING_TIME_DEFAULT,
    CALIBRATION_WINDFLOW_NUM_SAMPLES_DEFAULT,
    CALIBRATION_HOTPLATE_TEMP_MIN_DEFAULT,
    CALIBRATION_HOTPLATE_TEMP_MAX_DEFAULT,
    CALIBRATION_HOTPLATE_TEMP_STEP_DEFAULT,
    CALIBRATION_HOTPLATE_FAN_SPEEDS_DEFAULT,
    CALIBRATION_HOTPLATE_RECORDING_DURATION_DEFAULT,
    CALIBRATION_HOTPLATE_SAMPLING_INTERVAL_DEFAULT,
    FAN_COUNT, HOT_PLATE_COUNT,
    ResponseStatus, DeviceStatus as DeviceStatusEnum
)
from state_manager import state_manager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events"""
    # Startup
    logger.info("Starting Temperature Control System server...")
    
    # Connect to Arduino
    success = await arduino_comm.connect()
    if success:
        logger.info("Arduino connected successfully")
        # Apply settings from JSON file to Arduino
        await apply_settings_to_arduino(arduino_comm)        
    else:
        logger.warning("Failed to connect to Arduino - server will run without Arduino")
        logger.info("Please check:")
        logger.info("1. Arduino is connected via USB")
        logger.info("2. Correct COM port is being used")
        logger.info("3. Arduino sketch is uploaded and running")
        logger.info("4. No other program is using the serial port")
        
    # Start background polling 
    state_manager.background_task = asyncio.create_task(background_status_polling())
    
    yield
    
    # Shutdown
    await arduino_comm.disconnect()
    if state_manager.video_streaming_task:
        state_manager.video_streaming_task.cancel()
    if state_manager.background_task:
        state_manager.background_task.cancel()

# Initialize FastAPI app
app = FastAPI(
    title="Turbulance Control System",
    description="API for controlling Arduino-based turbulance control system",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize state manager with configuration
state_manager.max_history_size = get_configuration("max_history_size", MAX_HISTORY_SIZE)
state_manager.polling_interval = get_configuration("polling_interval", POLLING_INTERVAL_DEFAULT)

# Mount static files
workspace_root = get_workspace_root()
static_dir = os.path.join(workspace_root, "web")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Mount assets folder for local libraries
assets_dir = os.path.join(workspace_root, "web", "assets")
if os.path.exists(assets_dir):
    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

# Mount webfonts folder for Font Awesome (inside assets)
webfonts_dir = os.path.join(workspace_root, "web", "assets", "webfonts")
if os.path.exists(webfonts_dir):
    app.mount("/webfonts", StaticFiles(directory=webfonts_dir), name="webfonts")

# Mount camera images directory
camera_images_dir = os.path.join(workspace_root, CAMERA_IMAGES_FOLDER)
if os.path.exists(camera_images_dir):
    app.mount("/camera_images", StaticFiles(directory=camera_images_dir), name="camera_images")

# Initialize camera system
camera_images_folder = os.path.join(workspace_root, CAMERA_IMAGES_FOLDER)
pfs_file_path = os.path.join(workspace_root, "camera_settings.pfs")  # Default PFS file path

# Initialize camera (singleton)
camera = BaslerCamera.get_instance(camera_images_folder)

camera_initialized = camera.initialize_camera(pfs_file_path)

# WebSocket connection manager
ws_connection_manager = ConnectionManager()

# Video websocket streaming connection manager
ws_video_manager = VideoStreamManager(camera)

# Calibration Callback
def calibration_status_callback(session):
    """Callback to broadcast calibration status updates to all WebSocket clients"""
    # Broadcast directly when session updates
    asyncio.create_task(ws_calibration_manager.broadcast({
        "type": "calibration_status",
        "session": session.model_dump(mode='json'),
        "progress": session.get_progress(),
        "estimated_remaining_time": session.get_estimated_remaining_time()
    }))

# Calibration Webscoket connection manager
ws_calibration_manager = CalibrationConnectionManager()

# Initialize calibration agent
calibration_agent = CalibrationAgent(arduino_comm)
# Set status callback (only set once globally, but safe to set again)
calibration_agent.set_status_callback(calibration_status_callback)

# Initialize CN² optical calculator
cn2_calculator = CN2OpticalCalculator()

# Initialize CN² target controller (lookup-table based actuator setpoints)
cn2_controller = Cn2Controller()

# Data storage for Arduino status records
state_manager.status_update_queue = asyncio.Queue()

# Background polling task
async def background_status_polling():
    """Background task to poll Arduino for status and broadcast to WebSocket clients"""
    
    while True:
        try:
            if arduino_comm.is_connected:
                # Get status from Arduino
                response = await arduino_comm.get_status()
            else:
                await asyncio.sleep(state_manager.polling_interval)
                continue
            if response.status == ResponseStatus.OK:
                if response.data is None:
                    logger.warning("Response data is None, skipping status update")
                    await asyncio.sleep(state_manager.polling_interval)
                    continue
                    
                status_data = response.data.dict()
                status_data["device_status"] = DeviceStatusEnum.ONLINE
                status_data["arduino_port"] = arduino_comm.port if arduino_comm.is_connected else None
                status_data["system_ready"] = True  # System is ready when Arduino responds successfully
                status_data["timestamp"] = datetime.now().isoformat()
                status_data["image_filename"] = None
                
                # Calculate CN² and add to status data
                try:
                    cn2_value = calculate_cn2(
                        status_data.get("temperatures", []),
                        [status_data.get("bmpTemperature_internal"), status_data.get("bmpTemperature_external")],
                        [status_data.get("bmpPressure_internal"), status_data.get("bmpPressure_external")]
                    )
                    status_data["cn2"] = cn2_value
                except Exception as e:
                    logger.warning(f"Error calculating CN²: {e}")
                    status_data["cn2"] = None
                # Use the latest image from the independent fast image capture task
                if camera_initialized and state_manager.data_capture_active:
                    last_image = state_manager.last_image_filename
                    if last_image:
                        status_data["image_filename"] = last_image

                    if state_manager.last_centroid_x is not None and state_manager.last_centroid_y is not None:
                        status_data["centroid_x"] = state_manager.last_centroid_x
                        status_data["centroid_y"] = state_manager.last_centroid_y

                    # Calculate optical CN² from stored centroids once enough data points are available
                    if state_manager.get_centroid_history_length() >= CENTROID_HISTORY_THRESHOLD:
                        try:
                            cn2_optical = cn2_calculator.calculate_cn2_from_centroids(state_manager.centroid_history)
                            status_data["cn2_optical"] = cn2_optical
                        except Exception as e:
                            logger.warning(f"Error calculating optical CN²: {e}")
                            status_data["cn2_optical"] = None
                    else:
                        status_data["cn2_optical"] = None
                
                # Store in history
                state_manager.add_to_status_history(status_data)
                
                # Store in captured data points if capture is active
                if state_manager.data_capture_active and state_manager.current_capture_session:
                    data_point = status_data.copy()
                    data_point["session_id"] = state_manager.current_capture_session["id"]
                    state_manager.add_captured_data_point(data_point)
                    
                    # Append to CSV file if available
                    if state_manager.current_capture_session.get("csv_filepath"):
                        csv_data = status_data.copy()
                        # Convert temperatures list to comma-separated string
                        if "temperatures" in csv_data:
                            for i in range(len(csv_data["temperatures"])):
                                csv_data[f"temp_sensor_{i+1}"] = csv_data["temperatures"][i]                            
                            for i in range(len(csv_data["target_temperatures"])):
                                csv_data[f"target_temp_{i+1}"] = csv_data["target_temperatures"][i]
                            for i in range(len(csv_data["fan_speeds"])):
                                csv_data[f"fan_speed_{i+1}"] = csv_data["fan_speeds"][i]
                            for i in range(len(csv_data["hot_plate_states"])):
                                csv_data[f"hot_plate_{i+1}"] = csv_data["hot_plate_states"][i]
                            for i in range(len(csv_data["flow_rates"])):
                                csv_data[f"flow_rate_{i+1}"] = csv_data["flow_rates"][i]
                            csv_data["cn2_row1_500"] = csv_data["cn2"][CN2_ROW1_500_INDEX]
                            csv_data["cn2_row1_300"] = csv_data["cn2"][CN2_ROW1_300_INDEX]
                            csv_data["cn2_row2_500"] = csv_data["cn2"][CN2_ROW2_500_INDEX]
                            csv_data["cn2_row2_300"] = csv_data["cn2"][CN2_ROW2_300_INDEX]
                        csv_data["session_id"] = state_manager.current_capture_session["id"]
                        append_to_csv(state_manager.current_capture_session["csv_filepath"], csv_data)
                
                # Broadcast to all connected clients
                if ws_connection_manager.active_connections:
                    # Get camera status for streaming
                    camera_status = camera.get_camera_status()
                    
                    # Always send current data as current_data message
                    current_data_message = {
                        "type": "current_data",
                        "data": [{
                            **status_data,
                            "camera_status": camera_status,
                            "image_filename": status_data.get("image_filename"),
                            "timestamp": status_data.get("timestamp")
                        }],
                        "count": 1,
                        "latest_only": True
                    }
                    
                    await ws_connection_manager.broadcast(json.dumps(current_data_message))
                    
                    # Also send system status only when it changed
                    current_system_status = {
                        "device_status": status_data.get("device_status", DeviceStatusEnum.UNKNOWN),
                        "system_ready": status_data.get("system_ready", False),
                        "arduino_port": status_data.get("arduino_port"),
                        "timestamp": status_data.get("timestamp")
                    }
                    await ws_connection_manager.broadcast(json.dumps({
                        "type": "system_status",
                        **current_system_status
                    }))
                
            else:
                # Send error status
                error_status = {
                    "device_status": DeviceStatusEnum.OFFLINE,
                    "error": response.msg if response.msg else "Arduino not connected",
                    "arduino_port": arduino_comm.port if arduino_comm.is_connected else None,
                    "system_ready": False,
                    "timestamp": datetime.now().isoformat()
                }
                
                if ws_connection_manager.active_connections:
                    await ws_connection_manager.broadcast(json.dumps({
                        "type": "system_status",
                        **error_status
                    }))
                
        except Exception as e:
            logger.error(f"Error in background polling: {e}")
            error_status = {
                "type": "system_status",
                "device_status": DeviceStatusEnum.ERROR,
                "error": str(e),
                "arduino_port": arduino_comm.port if arduino_comm.is_connected else None,
                "system_ready": False,
                "timestamp": datetime.now().isoformat()
            }
            
            if ws_connection_manager.active_connections:
                await ws_connection_manager.broadcast(json.dumps(error_status))
        
        # Wait for next polling interval
        await asyncio.sleep(state_manager.polling_interval)

# Independent image capture worker for high-rate image acquisition
async def image_capture_worker():
    """Capture images as fast as possible while a data capture session is active.

    The worker writes images to the current capture session folder and keeps the
    latest filename/centroid on state_manager. The slower background_status_polling
    loop reads these cached values instead of blocking on the camera.
    """
    logger.info("Image capture worker started")
    try:
        while state_manager.data_capture_active and state_manager.current_capture_session:
            try:
                session = state_manager.current_capture_session
                folder = session.get("image_folder") if session else None

                if folder and camera_initialized:
                    image_filename = camera.capture_and_save(folder)
                    if image_filename:
                        state_manager.last_image_filename = image_filename

                        # Offload centroid calculation to avoid blocking the event loop
                        centroid = await asyncio.to_thread(calculate_beam_centroid, image_filename)
                        if centroid:
                            cx, cy = centroid
                            state_manager.last_centroid_x = float(cx)
                            state_manager.last_centroid_y = float(cy)

                            # Only store valid (non-zero) centroids for optical CN² history
                            if cx != 0 or cy != 0:
                                state_manager.add_centroid_to_history({
                                    "timestamp": datetime.now(),
                                    "centroid_x": float(cx),
                                    "centroid_y": float(cy)
                                })
                    else:
                        logger.warning("Image capture returned None")

                # Yield control so background polling and WebSockets stay responsive
                await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Error in image capture worker: {e}")
                await asyncio.sleep(0.1)
    finally:
        logger.info("Image capture worker stopped")

# Video streaming background task
async def video_streaming_worker():
    """Background task to handle video streaming to connected clients"""
    
    while True:
        try:
            # Check if there are active video streaming clients
            if ws_video_manager.active_connections:
                # Ensure camera streaming is active
                if not camera.is_streaming:
                    camera.start_video_stream()
                
                # Get latest frame from camera
                frame_data = camera.get_latest_frame()
                
                if frame_data:
                    # Send frame to all connected video clients
                    message = json.dumps({
                        "type": "video_frame",
                        "frame": frame_data,
                        "timestamp": datetime.now().isoformat()
                    })
                    
                    # Send to each video client
                    clients_to_remove = []
                    for client_id in list(ws_video_manager.active_connections.keys()):
                        try:
                            await ws_video_manager.send_frame(client_id, message)
                        except Exception as e:
                            logger.warning(f"Failed to send frame to client {client_id}: {e}")
                            clients_to_remove.append(client_id)
                    
                    # Remove disconnected clients
                    for client_id in clients_to_remove:
                        ws_video_manager.disconnect(client_id)
                
                # Small delay to control frame rate
                await asyncio.sleep(CAMERA_VIDEO_FRAME_DELAY)
            else:
                # No video clients, stop camera streaming to save resources
                if camera.is_streaming and not state_manager.data_capture_active:
                    camera.stop_video_stream()
                # Wait before checking again
                await asyncio.sleep(1.0)
                
        except Exception as e:
            logger.error(f"Error in video streaming worker: {e}")
            await asyncio.sleep(1.0)

# API Routes
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "arduino_connected": arduino_comm.is_connected,
        "arduino_port": arduino_comm.port
    }

@app.get("/")
async def root():
    """Serve the main dashboard page"""
    web_file = os.path.join(workspace_root, "web", "index.html")
    if os.path.exists(web_file):
        return FileResponse(web_file)
    else:
        raise HTTPException(status_code=404, detail="Main page not found")

@app.get("/configuration")
async def configuration():
    """Serve the configuration interface"""
    web_file = os.path.join(workspace_root, "web", "configuration.html")
    if os.path.exists(web_file):
        return FileResponse(web_file)
    else:
        return {"message": "Main interface not found", "version": "1.0.0"}

@app.get("/calibration")
async def calibration():
    """Serve the calibration interface"""
    web_file = os.path.join(workspace_root, "web", "calibration.html")
    if os.path.exists(web_file):
        return FileResponse(web_file)
    else:
        return {"message": "Calibration interface not found", "version": "1.0.0"}

@app.get("/api/status")
async def get_system_status():
    """Get current system status"""
    import time
    start_time = time.time()
    try:
        response = await arduino_comm.get_status()
        elapsed = time.time() - start_time
        logger.info(f"/api/status endpoint took {elapsed:.3f}s")
        
        if response.status == "ok":
            return response.data
        else:
            raise HTTPException(status_code=500, detail=response.msg)
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"/api/status endpoint failed after {elapsed:.3f}s: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/temperature/set")
async def set_temperature(command: TemperatureCommand):
    """Set target temperature for hot plate"""
    try:
        response = await arduino_comm.set_temperature(command.sensor, command.target)
        if response.status == "ok":
            return {"status": "success", "message": "Temperature set successfully"}
        else:
            raise HTTPException(status_code=400, detail=response.msg)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/fan/set")
async def set_fan_speed(command: FanCommand):
    """Set fan speed"""
    if command.speed < 0 or command.speed > 255:
        raise HTTPException(status_code=400, detail="Fan speed must be between 0 and 255")
    
    try:
        response = await arduino_comm.set_fan_speed(command.fan, command.speed)
        if response.status == "ok":
            return {"status": "success", "message": "Fan speed set successfully"}
        else:
            raise HTTPException(status_code=400, detail=response.msg)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/hotplate/{plate_id}/toggle")
async def toggle_hot_plate(plate_id: int, request: HotPlateToggleRequest):
    """Toggle hot plate on/off"""
    if plate_id < 0 or plate_id > 1:
        raise HTTPException(status_code=400, detail="Invalid hot plate ID")
    
    try:
        response = await arduino_comm.toggle_hot_plate(plate_id, request.state)
        if response.status == "ok":
            return {"status": "success", "message": f"Hot plate {plate_id + 1} {'enabled' if request.state else 'disabled'}"}
        else:
            raise HTTPException(status_code=400, detail=response.msg)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/settings")
async def get_settings(key: str = None):
    """Get configuration settings from JSON file"""
    try:
        settings = load_configuration()
        if key:
            return settings.get(key)
        return settings
    except FileNotFoundError:
        return {"error": "Configuration file not found"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/settings")
async def save_settings(settings: dict):
    """Save configuration settings to JSON file"""
    try:
        set_configuration(settings)
        
        # Apply settings to Arduino
        await apply_settings_to_arduino(arduino_comm)
        
        return {"status": ResponseStatus.SUCCESS, "message": "Configuration saved and applied to Arduino"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/settings/apply")
async def apply_settings():
    """Apply settings from JSON file to Arduino"""
    try:
        await apply_settings_to_arduino(arduino_comm)
        return {"status": ResponseStatus.SUCCESS, "message": "Settings applied to Arduino"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/cn2/apply")
async def apply_cn2_target(request: Cn2TargetRequest):
    """Compute and apply actuator setpoints for a target Cn² value."""
    if request.target_cn2 < cn2_controller.cn2_min or request.target_cn2 > cn2_controller.cn2_max:
        raise HTTPException(
            status_code=400,
            detail=f"target_cn2 must be between {cn2_controller.cn2_min} and {cn2_controller.cn2_max}"
        )

    actuators = cn2_controller.get_actuators_for_cn2(request.target_cn2)
    result = {
        "status": ResponseStatus.SUCCESS,
        "target_cn2": actuators["target_cn2"],
        "dt": actuators["required_dt"],
        "hotplate_temp": actuators["hotplate_temp"],
        "fan_speed": actuators["fan_speed"],
        "applied": False
    }

    if not request.dry_run:
        if not arduino_comm.is_connected:
            raise HTTPException(status_code=503, detail="Arduino not connected")

        for plate in range(HOT_PLATE_COUNT):
            temp_resp = await arduino_comm.set_temperature(plate, actuators["hotplate_temp"])
            if temp_resp.status != "ok":
                raise HTTPException(status_code=400, detail=f"Failed to set hotplate {plate} temp: {temp_resp.msg}")

        for plate in range(HOT_PLATE_COUNT):
            toggle_resp = await arduino_comm.toggle_hot_plate(plate, True)
            if toggle_resp.status != "ok":
                raise HTTPException(status_code=400, detail=f"Failed to enable hotplate {plate}: {toggle_resp.msg}")

        for fan in range(FAN_COUNT):
            fan_resp = await arduino_comm.set_fan_speed(fan, actuators["fan_speed"])
            if fan_resp.status != "ok":
                raise HTTPException(status_code=400, detail=f"Failed to set fan {fan} speed: {fan_resp.msg}")

        result["applied"] = True

    return result

@app.get("/api/camera/status")
async def get_camera_status_endpoint():
    """Get camera system status"""
    try:
        return camera.get_camera_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Calibration API endpoints
@app.post("/api/calibration/windflow/start")
async def start_windflow_calibration(
    fan_speed_step: int = CALIBRATION_WINDFLOW_FAN_SPEED_STEP_DEFAULT,
    settling_time_ms: int = CALIBRATION_WINDFLOW_SETTLING_TIME_DEFAULT,
    num_samples: int = CALIBRATION_WINDFLOW_NUM_SAMPLES_DEFAULT
):
    """Start fan-to-windflow sensor calibration"""
    try:
        session = await calibration_agent.start_windflow_calibration(fan_speed_step, settling_time_ms, num_samples)
        return {
            "status": ResponseStatus.SUCCESS,
            "message": "Windflow calibration started",
            "session_id": session.session_id,
            "total_steps": session.total_steps,
            "fan_speed_step": fan_speed_step,
            "settling_time_ms": settling_time_ms,
            "num_samples": num_samples,
            "estimated_duration": f"~{(session.total_steps * (settling_time_ms/1000 + num_samples * 0.2) / 60):.1f} minutes"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/calibration/control")
async def control_calibration(control: CalibrationControl):
    """Control calibration (pause, resume, stop)"""
    try:
        if control.action == "pause":
            calibration_agent.pause_calibration()
            return {"status": ResponseStatus.SUCCESS, "message": "Calibration paused"}
        elif control.action == "resume":
            calibration_agent.resume_calibration()
            return {"status": ResponseStatus.SUCCESS, "message": "Calibration resumed"}
        elif control.action == "stop":
            calibration_agent.stop_calibration()
            return {"status": ResponseStatus.SUCCESS, "message": "Calibration stopped"}
        else:
            raise HTTPException(status_code=400, detail=f"Invalid action: {control.action}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/calibration/session")
async def get_current_calibration_session():
    """Get information about the current calibration session"""
    try:
        session_info = calibration_agent.get_current_session_info()
        if session_info:
            return {
                "status": ResponseStatus.SUCCESS,
                "has_session": True,
                "session": session_info
            }
        else:
            return {
                "status": ResponseStatus.SUCCESS,
                "has_session": False,
                "message": "No active calibration session"
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/calibration/session/clear")
async def clear_calibration_session():
    """Clear the current calibration session"""
    try:
        calibration_agent.clear_session()
        return {
            "status": ResponseStatus.SUCCESS,
            "message": "Calibration session cleared"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/calibration/hotplate/start")
async def start_hotplate_calibration(
    temp_min: float = CALIBRATION_HOTPLATE_TEMP_MIN_DEFAULT,
    temp_max: float = CALIBRATION_HOTPLATE_TEMP_MAX_DEFAULT,
    temp_step: float = CALIBRATION_HOTPLATE_TEMP_STEP_DEFAULT,
    fan_speeds: str = CALIBRATION_HOTPLATE_FAN_SPEEDS_DEFAULT,
    recording_duration: int = CALIBRATION_HOTPLATE_RECORDING_DURATION_DEFAULT,
    sampling_interval: int = CALIBRATION_HOTPLATE_SAMPLING_INTERVAL_DEFAULT
):
    """Start hot plate 4D calibration (temperature × fan speed)"""
    try:
        # Parse fan speeds string to list - handle both single values and comma-separated lists
        if "," in fan_speeds:
            fan_speeds_list = [int(x.strip()) for x in fan_speeds.split(",") if x.strip()]
        else:
            # Handle single value
            fan_speeds_list = [int(fan_speeds.strip()) if fan_speeds.strip() else FAN_SPEED_MAX]

        session = await calibration_agent.start_hotplate_calibration(
            temp_min, temp_max, temp_step, fan_speeds_list, recording_duration, sampling_interval
        )
        num_temp_steps = int((temp_max - temp_min) / temp_step) + 1
        total_steps = num_temp_steps * len(fan_speeds_list)
        total_duration_hours = (total_steps * recording_duration) / 3600
        return {
            "status": ResponseStatus.SUCCESS,
            "message": "Hot plate 4D calibration started",
            "session_id": session.session_id,
            "total_steps": session.total_steps,
            "temp_min": temp_min,
            "temp_max": temp_max,
            "temp_step": temp_step,
            "fan_speeds": fan_speeds_list,
            "recording_duration": recording_duration,
            "sampling_interval": sampling_interval,
            "estimated_duration": f"~{total_duration_hours:.1f} hours"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/calibration/lookup-table")
async def get_calibration_lookup_table():
    """Get the latest combined calibration lookup table"""
    try:
        # Load from calibration_data folder
        calib_folder = calibration_agent.config.calibration_data_folder
        calib_folder_abs = os.path.abspath(calib_folder)
        lookup_table_path = os.path.join(calib_folder_abs, "combined_calibration.json")

        if os.path.exists(lookup_table_path):
            import json
            with open(lookup_table_path, 'r') as f:
                data = json.load(f)
            return {
                "status": ResponseStatus.SUCCESS,
                "lookup_table": data.get("lookup_table"),
                "calibration_id": data.get("calibration_id"),
                "timestamp": data.get("timestamp")
            }
        else:
            return {
                "status": ResponseStatus.ERROR,
                "message": "No combined calibration lookup table found"
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/calibration/lookup-table/interpolate")
async def interpolate_lookup_table(hotplate_temp: float, fan_speed: int):
    """Interpolate lookup table for given temperature and fan speed"""
    try:
        # Load lookup table
        calib_folder = calibration_agent.config.calibration_data_folder
        calib_folder_abs = os.path.abspath(calib_folder)
        lookup_table_path = os.path.join(calib_folder_abs, "combined_calibration.json")

        if not os.path.exists(lookup_table_path):
            raise HTTPException(status_code=404, detail="No lookup table found")

        import json
        from server.calibration.combined_calibration import CombinedLookupTable, CombinedCalibrator

        with open(lookup_table_path, 'r') as f:
            data = json.load(f)

        lookup_table = CombinedLookupTable(**data['lookup_table'])
        calibrator = CombinedCalibrator()

        result = calibrator.interpolate_lookup_table(lookup_table, hotplate_temp, fan_speed)

        return {
            "status": ResponseStatus.SUCCESS,
            "result": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/calibration/windflow-polynomials")
async def get_windflow_polynomials():
    """Get the latest fan-to-windflow polynomial calibration results from calibration_data root folder"""
    try:
        import json
        import os
        from calibration.config import DEFAULT_CONFIG

        # Load from calibration_data root folder
        calib_folder = os.path.abspath(DEFAULT_CONFIG.calibration_data_folder)
        filepath = os.path.join(calib_folder, "windflow_polynomials.json")

        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                data = json.load(f)
            return {
                "status": ResponseStatus.SUCCESS,
                "polynomials": data.get('polynomials', [])
            }
        else:
            return {
                "status": ResponseStatus.OK,
                "message": "No windflow polynomials available. Run calibration to generate polynomial curves."
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/calibration/latest-metadata")
async def get_latest_calibration_metadata():
    """Get the latest session metadata from calibration_data root folder"""
    try:
        import json
        import os
        from calibration.config import DEFAULT_CONFIG

        # Load from calibration_data root folder
        calib_folder = os.path.abspath(DEFAULT_CONFIG.calibration_data_folder)
        filepath = os.path.join(calib_folder, "session_metadata.json")

        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                data = json.load(f)
            return {
                "status": ResponseStatus.SUCCESS,
                "metadata": data
            }
        else:
            return {
                "status": ResponseStatus.OK,
                "message": "No session metadata available. Run calibration to generate metadata."
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/calibration/data")
async def get_calibration_data(session_id: str = None):
    """Get calibration data for a specific session, or latest data if session_id is None"""
    import csv
    import os
    from calibration.config import DEFAULT_CONFIG
    
    try:
        # If session_id is None, load from root calibration_data folder
        if session_id is None or session_id == "none":
            calib_folder = os.path.abspath(DEFAULT_CONFIG.calibration_data_folder)
            csv_file = os.path.join(calib_folder, "calibration_data.csv")
            
            if os.path.exists(csv_file):
                data = []
                with open(csv_file, 'r') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        data.append(row)
                return {
                    "status": ResponseStatus.SUCCESS,
                    "data": data
                }
            else:
                return {
                    "status": ResponseStatus.OK,
                    "message": "No calibration data available. Run calibration to generate data."
                }
        else:
            # Construct path to session CSV file
            session_folder = os.path.join(DEFAULT_CONFIG.calibration_data_folder, session_id)
            csv_file = os.path.join(session_folder, "calibration_data.csv")
            
            if not os.path.exists(csv_file):
                return {
                    "status": ResponseStatus.ERROR,
                    "message": f"Calibration data not found for session {session_id}"
                }
            
            # Read CSV data
            data = []
            with open(csv_file, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    data.append({
                        "timestamp": row.get("timestamp", ""),
                        "fan_speed": int(row.get("fan_speed", 0)),
                        "sensor_0_avg": float(row.get("sensor_0_avg", 0)) if row.get("sensor_0_avg") else None,
                        "sensor_1_avg": float(row.get("sensor_1_avg", 0)) if row.get("sensor_1_avg") else None,
                        "sensor_2_avg": float(row.get("sensor_2_avg", 0)) if row.get("sensor_2_avg") else None,
                        "sensor_3_avg": float(row.get("sensor_3_avg", 0)) if row.get("sensor_3_avg") else None
                    })
            
            return {
                "status": ResponseStatus.SUCCESS,
                "data": data
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/data-capture")
async def toggle_data_capture(request: DataCaptureRequest, acquisition_type: str = "data"):
    """Start or stop data capture with camera images"""
    
    try:
        # Check camera availability
        camera_status = camera.get_camera_status()
        camera_available = camera_status.get("initialized", False)
        
        if request.start:
            # Start data capture
            if state_manager.data_capture_active:
                return {"status": ResponseStatus.ERROR, "message": "Data capture already active"}
                        
            # Create new capture session with acquisition_type-specific folder
            capture_folder = get_calibration_data_folder()
            
            # Create subfolder based on acquisition_type
            acquisition_folder = os.path.join(capture_folder, acquisition_type)
            os.makedirs(acquisition_folder, exist_ok=True)
            
            image_capture_folder = create_capture_folder()
            state_manager.current_capture_session = {
                "id": request.capture_id or f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "start_time": datetime.now().isoformat(),
                "folder": acquisition_folder,
                "image_folder": image_capture_folder,
                "acquisition_type": acquisition_type,
                "data_points": []
            }
            
            # Clear centroid history for new session
            state_manager.clear_centroid_history()
            
            # Initialize CSV file for data capture with acquisition_type in filename
            csv_filename = f"{acquisition_type}_data{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            csv_filepath = init_csv_file(acquisition_folder, csv_filename)
            if csv_filepath:
                state_manager.current_capture_session["csv_filepath"] = csv_filepath
            else:
                logger.warning("Failed to initialize CSV file, data will only be stored in memory")
            
            # Arm hotplates when starting data acquisition
            for plate in range(HOT_PLATE_COUNT):
                resp = await arduino_comm.toggle_hot_plate(plate, True)
                if resp.status != "ok":
                    raise HTTPException(status_code=400, detail=f"Failed to enable hotplate {plate}: {resp.msg}")
            
            state_manager.data_capture_active = True
            state_manager.clear_captured_data_points()

            # Reset last captured image/centroid state
            state_manager.last_image_filename = None
            state_manager.last_centroid_x = None
            state_manager.last_centroid_y = None

            # Start independent fast image capture worker
            if camera_initialized:
                if state_manager.image_capture_task and not state_manager.image_capture_task.done():
                    state_manager.image_capture_task.cancel()
                    try:
                        await state_manager.image_capture_task
                    except asyncio.CancelledError:
                        pass

                # Stop any active video streaming so the capture worker has exclusive camera access
                await asyncio.to_thread(camera.stop_video_stream)

                state_manager.image_capture_task = asyncio.create_task(image_capture_worker())
            
            logger.info(f"Started data capture session: {state_manager.current_capture_session['id']}")
            return {
                "status": ResponseStatus.SUCCESS,
                "message": "Data capture started",
                "session_id": state_manager.current_capture_session["id"],
                "folder": capture_folder,
                "camera_available": camera_available
            }
            
        else:
            # Stop data capture
            if not state_manager.data_capture_active:
                return {"status": ResponseStatus.ERROR, "message": "No active data capture session"}
            
            session_info = state_manager.current_capture_session.copy()
            session_info["end_time"] = datetime.now().isoformat()
            session_info["total_data_points"] = len(state_manager.captured_data_points)
            
            logger.info(f"Stopping data capture, data points count: {len(state_manager.captured_data_points)}")
             
            # Reset capture state
            state_manager.data_capture_active = False
            state_manager.clear_captured_data_points()

            # Stop independent image capture worker
            if state_manager.image_capture_task and not state_manager.image_capture_task.done():
                state_manager.image_capture_task.cancel()
                try:
                    await state_manager.image_capture_task
                except asyncio.CancelledError:
                    pass
            state_manager.image_capture_task = None
            state_manager.last_image_filename = None
            state_manager.last_centroid_x = None
            state_manager.last_centroid_y = None
            
            # Stop camera video streaming
            camera.stop_video_stream()
            
            # Disarm hotplates when stopping data acquisition
            for plate in range(HOT_PLATE_COUNT):
                try:
                    await arduino_comm.toggle_hot_plate(plate, False)
                except Exception as e:
                    logger.warning(f"Failed to disable hotplate {plate}: {e}")
            
            # Stop video streaming worker if no other active connections
            if len(ws_video_manager.active_connections) == 0:
                logger.info("Stopping video streaming worker - no active connections")
                if state_manager.video_streaming_task and not state_manager.video_streaming_task.done():
                    state_manager.video_streaming_task.cancel()
                    try:
                        await state_manager.video_streaming_task
                    except asyncio.CancelledError:
                        pass
                state_manager.video_streaming_task = None
            
            logger.info(f"Stopped data capture session: {session_info['id']}")
            return {
                "status": ResponseStatus.SUCCESS,
                "message": "Data capture stopped",
                "session_info": session_info
            }
            
    except Exception as e:
        logger.error(f"Error toggling data capture: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/data-capture/status")
async def get_data_capture_status():
    """Get current data capture status"""
    
    return {
        "active": state_manager.data_capture_active,
        "session": state_manager.current_capture_session,
        "data_points_count": len(state_manager.captured_data_points)
    }

@app.get("/api/data-capture/download")
async def download_captured_data():
    """Download captured data as CSV"""
    
    try:
        # Try to return the existing CSV file if available
        if state_manager.current_capture_session and state_manager.current_capture_session.get("csv_filepath"):
            csv_filepath = state_manager.current_capture_session["csv_filepath"]
            if os.path.exists(csv_filepath):
                filename = os.path.basename(csv_filepath)
                return FileResponse(
                    csv_filepath,
                    media_type="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={filename}"}
                )
        
        # Fallback: no CSV file available
        logger.warning("No CSV file available for download")
        raise HTTPException(status_code=404, detail="No captured data file available")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading captured data: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/polling_interval")
async def set_polling_interval(interval: float):
    """Set the polling interval for Arduino status updates"""
    
    if interval < 0.5 or interval > 60:
        raise HTTPException(status_code=400, detail="Polling interval must be between 0.5 and 60 seconds")
    
    state_manager.polling_interval = interval
    logger.info(f"Polling interval updated to {interval} seconds")
    
    return {
        "status": ResponseStatus.SUCCESS,
        "message": f"Polling interval set to {interval} seconds",
        "polling_interval": state_manager.polling_interval
    }

@app.post("/api/arduino/reconnect")
async def reconnect_arduino(request: ReconnectRequest = None):
    """Reconnect Arduino to specified port or default"""
    try:
        # Disconnect first
        await arduino_comm.disconnect()
        
        # Update port if provided
        if request and request.port:
            arduino_comm.port = request.port
        
        # Reconnect
        success = await arduino_comm.connect()
        
        if success:
            return {
                "status": ResponseStatus.SUCCESS, 
                "message": f"Arduino connected to {arduino_comm.port}",
                "port": arduino_comm.port
            }
        else:
            logger.error("Failed to reconnect Arduino")
            return {
                "status": ResponseStatus.ERROR, 
                "message": "Failed to connect to Arduino",
                "port": arduino_comm.port
            }
            
    except Exception as e:
        logger.error(f"Error reconnecting Arduino: {e}")
        return {
            "status": ResponseStatus.ERROR, 
            "message": f"Connection error: {str(e)}"
        }

@app.post("/api/arduino/force-reconnect")
async def force_reconnect_arduino():
    """Force immediate Arduino reconnection"""
    try:
        await arduino_comm.disconnect()
        await asyncio.sleep(1)  # Brief delay
        success = await arduino_comm.connect()
        
        return {
            "status": ResponseStatus.SUCCESS if success else ResponseStatus.ERROR,
            "message": "Force reconnection completed" if success else "Force reconnection failed",
            "connected": success,
            "port": arduino_comm.port
        }
        
    except Exception as e:
        logger.error(f"Force reconnect error: {e}")
        return {
            "status": ResponseStatus.ERROR,
            "message": f"Force reconnect failed: {str(e)}"
        }

@app.post("/api/history_size")
async def set_history_size(request: dict = Body(...)):
    """Set the maximum history size"""
    try:
        size = request.get("size")
        if not isinstance(size, int) or size < 10 or size > 1000:
            raise HTTPException(status_code=400, detail="History size must be between 10 and 1000")
        
        # Update the max size in state manager
        state_manager.max_history_size = size
        
        logger.info(f"History size updated to {size} records")
        
        return {
            "status": ResponseStatus.SUCCESS,
            "message": f"History size set to {size} records",
            "max_size": size,
            "current_count": state_manager.get_status_history_length()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting history size: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to set history size: {str(e)}")

@app.get("/api/history")
async def get_history():
    """Get historical data as JSON"""
    try:
        return {
            "status": ResponseStatus.SUCCESS,
            "data": list(state_manager.status_history),
            "count": state_manager.get_status_history_length(),
            "max_size": state_manager.max_history_size
        }
    except Exception as e:
        logger.error(f"Error getting history: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get history: {str(e)}")

@app.get("/api/history/{limit:int}")
async def get_history_limit(limit: int):
    """Get limited number of recent records as JSON"""
    try:
        if limit <= 0:
            raise HTTPException(status_code=400, detail="Limit must be greater than 0")
        
        # Get the most recent records
        recent_data = list(state_manager.status_history)[-limit:] if limit < state_manager.get_status_history_length() else list(state_manager.status_history)
        
        return {
            "status": ResponseStatus.SUCCESS,
            "data": recent_data,
            "count": len(recent_data),
            "limit": limit,
            "max_size": state_manager.max_history_size
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting limited history: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get history: {str(e)}")

@app.websocket("/ws/status")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time status updates"""
    logger.info("New WebSocket connection attempt...")
    await ws_connection_manager.connect(websocket)
    
    # Send system status immediately for fast footer update
    current_status = {
        "type": "system_status",
        "device_status": DeviceStatusEnum.OFFLINE,
        "system_ready": False,
        "arduino_port": arduino_comm.port if arduino_comm.is_connected else None,
        "polling_interval": state_manager.polling_interval,
        "timestamp": datetime.now().isoformat()
    }
    await websocket.send_text(json.dumps(current_status))
    
    # Keep connection alive and handle incoming messages
    while True:
        try:
            message = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            # Parse incoming message
            try:
                data = json.loads(message)
                if data.get("type") == "ping":
                    await websocket.send_text(json.dumps(current_status))
                elif data.get("type") == "get_status":
                    # Send current status
                    await websocket.send_text(json.dumps(current_status))
            except json.JSONDecodeError:
                logger.warning("Invalid JSON received from WebSocket")
            
        except asyncio.TimeoutError:
            # Send ping to keep connection alive
            await websocket.send_text('{"type":"ping"}')
            
        except WebSocketDisconnect:
            logger.info("WebSocket client disconnected")
            break
            
        except Exception as e:
            logger.error(f"WebSocket connection error: {e}")
            break
    
    ws_connection_manager.disconnect(websocket)

@app.websocket("/ws/video/{client_id}")
async def video_streaming_websocket(websocket: WebSocket, client_id: str):
    """WebSocket endpoint for video streaming"""
    logger.info(f"New video streaming connection attempt from client: {client_id}")
    
    # Check camera status before accepting connection
    camera_status = camera.get_camera_status()
    camera_available = camera_status.get("initialized", False)
    
    if not camera_available:
        logger.warning(f"Camera not connected - rejecting video streaming connection from client: {client_id}")
        await websocket.accept()
        await websocket.send_text(json.dumps({
            "type": ResponseStatus.ERROR,
            "message": "Camera not connected or not available",
            "timestamp": datetime.now().isoformat()
        }))
        await websocket.close()
        return
    
    await ws_video_manager.connect(websocket, client_id)
    
    # Start video streaming worker if not already running
    if state_manager.video_streaming_task is None or state_manager.video_streaming_task.done():
        state_manager.video_streaming_task = asyncio.create_task(video_streaming_worker())
        logger.info("Video streaming worker started for camera overlay view")
    
    # Ensure video streaming is started
    streaming_status = camera.get_streaming_status()
    if not streaming_status.get("is_streaming", False):
        logger.info("Starting video streaming for new client connection")
        camera.start_video_stream()
        # Wait a moment for streaming to start
        await asyncio.sleep(1.0)
        streaming_status = camera.get_streaming_status()
    
    # Send initial status
    await websocket.send_text(json.dumps({
        "type": "stream_status",
        "status": streaming_status,
        "client_id": client_id,
        "timestamp": datetime.now().isoformat()
    }))
    
    logger.info(f"Video streaming connection established for client: {client_id}")
    
    # Keep connection alive and handle incoming messages
    while True:
        try:
            message = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            
            # Parse incoming message
            try:
                data = json.loads(message)
                if data.get("type") == "ping":
                    await websocket.send_text('{"type":"pong"}')
                elif data.get("type") == "start_stream":
                    # Start video streaming if not already active
                    if not streaming_status.get("is_streaming", False):
                        success = camera.start_video_stream()
                        await websocket.send_text(json.dumps({
                            "type": "stream_response",
                            "action": "start",
                            "success": success,
                            "message": "Video streaming started" if success else "Failed to start video streaming",
                            "timestamp": datetime.now().isoformat()
                        }))
                elif data.get("type") == "stop_stream":
                    # Stop video streaming and disconnect client
                    camera.stop_video_stream()
                    await websocket.send_text(json.dumps({
                        "type": "stream_response",
                        "action": "stop",
                        "success": True,
                        "message": "Video streaming stopped successfully",
                        "timestamp": datetime.now().isoformat()
                    }))
                    await websocket.close()
                    ws_video_manager.disconnect(client_id)
                    break
                elif data.get("type") == "test_frame":
                    # Send a test frame
                    test_frame = camera.get_latest_frame()
                    if test_frame:
                        await websocket.send_text(json.dumps({
                            "type": "video_frame",
                            "frame": test_frame,
                            "timestamp": datetime.now().isoformat()
                        }))
                    else:
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "message": "No test frame available",
                            "timestamp": datetime.now().isoformat()
                        }))
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON received from video client {client_id}")
            
        except asyncio.TimeoutError:
            # Send ping to keep connection alive
            await websocket.send_text('{"type":"ping"}')
            
        except WebSocketDisconnect:
            logger.info(f"Video streaming client disconnected: {client_id}")
            break
            
        except Exception as e:
            logger.error(f"Error handling video WebSocket message from {client_id}: {e}")
            break
    
    ws_video_manager.disconnect(client_id)
    
    # Stop video streaming worker if no active connections and not in data capture
    if len(ws_video_manager.active_connections) == 0 and not data_capture_active:
        logger.info("Stopping video streaming worker - no active connections and not in data capture")
        if video_streaming_task and not video_streaming_task.done():
            video_streaming_task.cancel()
            try:
                await video_streaming_task
            except asyncio.CancelledError:
                pass
        video_streaming_task = None

@app.websocket("/ws/calibration")
async def calibration_websocket(websocket: WebSocket):
    """WebSocket endpoint for real-time calibration status updates"""
    await ws_calibration_manager.connect(websocket)
    
    # Send current status immediately
    session = calibration_agent.get_session_status()
    if session:
        await websocket.send_text(json.dumps({
            "type": "calibration_status",
            "session": session.model_dump(mode='json'),
            "progress": session.get_progress(),
            "estimated_remaining_time": session.get_estimated_remaining_time()
        }))
    
    # Keep connection alive without timeout - client will disconnect when calibration completes
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.info("Calibration WebSocket client disconnected")
    except Exception as e:
        logger.error(f"Calibration WebSocket error: {e}")
    finally:
        ws_calibration_manager.disconnect(websocket)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
