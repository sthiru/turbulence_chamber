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
    ReconnectRequest, HotPlateToggleRequest, DataCaptureRequest, DataPointWithImage
)
from arduino_comm import arduino_comm
from camera_acquisition import BaslerCamera, PYLON_AVAILABLE
from cn2.cn2_optical import CN2OpticalCalculator
from cn2.cn2_thermal import calculate_cn2
from calibration.calibration_agent import CalibrationAgent
from calibration.models import CalibrationRequest, CalibrationControl
from calibration.config import CalibrationConfig
from csv_utils import init_csv_file, append_to_csv
from utils import load_configuration, get_configuration, set_configuration, get_workspace_root, get_calibration_data_folder, create_capture_folder, calculate_beam_centroid
from ws_connection_manager import ConnectionManager
from ws_video_stream_manager import VideoStreamManager
from ws_calibration_manager import CalibrationConnectionManager
from arduino_comm import apply_settings_to_arduino

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events"""
    global background_task, video_streaming_task
    
    # Startup
    logger.info("Starting Temperature Control System server...")
    
    # Connect to Arduino
    logger.debug(f"Attempting to connect to Arduino on {arduino_comm.port}...")
    success = await arduino_comm.connect()
    if success:
        logger.debug("Arduino connected successfully")
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
    background_task = asyncio.create_task(background_status_polling())
    
    yield
    
    # Shutdown
    await arduino_comm.disconnect()
    if video_streaming_task:
        video_streaming_task.cancel()
    if background_task:
        background_task.cancel()

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

# Constants
MAX_HISTORY_SIZE = get_configuration("max_history_size", 1000)
POLLING_INTERVAL = get_configuration("polling_interval", 1.0)

# Global variables for background polling
background_task = None
video_streaming_task = None
last_broadcast_time = 0
polling_interval = POLLING_INTERVAL  # Current polling interval (can be updated at runtime)

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
camera_images_dir = os.path.join(workspace_root, "camera_images")
if os.path.exists(camera_images_dir):
    app.mount("/camera_images", StaticFiles(directory=camera_images_dir), name="camera_images")

# Initialize camera system
camera_images_folder = os.path.join(workspace_root, "camera_images")
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

# Status history storage
status_history = deque(maxlen=MAX_HISTORY_SIZE)

# Data storage for Arduino status records
status_update_queue = asyncio.Queue()

# Data capture state
data_capture_active = False
current_capture_session = None
captured_data_points = []
centroid_history = []  # Store centroid values with timestamps for CN² calculation
# Global variables for background polling
background_task = None
video_streaming_task = None
last_broadcast_time = 0
polling_interval = POLLING_INTERVAL  # Current polling interval (can be updated at runtime)

# Background polling task
async def background_status_polling():
    """Background task to poll Arduino for status and broadcast to WebSocket clients"""
    global last_broadcast_time
    
    while True:
        try:
            if arduino_comm.is_connected:
                # Get status from Arduino
                response = await arduino_comm.get_status()
            else:
                # logger.info("Arduino not connected, skipping status poll")
                await asyncio.sleep(polling_interval)
                continue
            if response.status == "ok":
                if response.data is None:
                    logger.warning("Response data is None, skipping status update")
                    await asyncio.sleep(polling_interval)
                    continue
                    
                status_data = response.data.dict()
                status_data["device_status"] = "online"
                status_data["arduino_port"] = arduino_comm.port if arduino_comm.is_connected else None
                status_data["system_ready"] = True  # System is ready when Arduino responds successfully
                status_data["timestamp"] = datetime.now().isoformat()
                status_data["image_filename"] = 'camera_images'
                
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
                
                global data_capture_active, current_capture_session, captured_data_points, cn2_calculator, centroid_history
                # Calculate optical CN² if we have temperature differences
                if(camera_initialized):               
                    if data_capture_active and current_capture_session:
                        try:
                            logger.debug(f"Data capture active, session: {current_capture_session['id']}")
                            logger.debug(f"Capture folder: {current_capture_session['folder']}")
                            image_filename = camera.capture_and_save(current_capture_session['image_folder'])
                            
                            if image_filename:
                                # Add image filename to status data
                                status_data["image_filename"] = image_filename
                                logger.debug(f"Successfully captured image: {image_filename}")
                                
                                # Calculate beam centroid for the captured image
                                try:
                                    status_data["centroid_x"], status_data["centroid_y"] = calculate_beam_centroid(image_filename)
                                    
                                    # Store centroid in history with timestamp
                                    centroid_history.append({
                                        "timestamp": datetime.now(),
                                        "centroid_x": status_data["centroid_x"],
                                        "centroid_y": status_data["centroid_y"]
                                    })
                                    
                                    # Calculate optical CN² from stored centroids
                                    cn2_optical = cn2_calculator.calculate_cn2_from_centroids(centroid_history)
                                    status_data["cn2_optical"] = cn2_optical
                                except Exception as e:
                                    logger.warning(f"Error calculating beam centroid or optical CN²: {e}")
                                    status_data["centroid_x"] = None
                                    status_data["centroid_y"] = None
                            else:
                                logger.warning("Image capture returned None")
                                status_data["centroid_x"] = None
                                status_data["centroid_y"] = None
                        except Exception as e:
                            logger.warning(f"Failed to capture image during data capture: {e}")
                            import traceback
                            traceback.print_exc()
                    else:
                        logger.debug("Data capture not active or no session")                    
                
                # Store in history
                status_history.append(status_data.copy())
                
                # Store in captured data points if capture is active
                if data_capture_active and current_capture_session:
                    data_point = status_data.copy()
                    data_point["session_id"] = current_capture_session["id"]
                    captured_data_points.append(data_point)
                    logger.debug(f"Captured data point {len(captured_data_points)}")
                    
                    # Append to CSV file if available
                    if current_capture_session.get("csv_filepath"):
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
                            csv_data["cn2_row1_500"] = csv_data["cn2"][0]
                            csv_data["cn2_row1_300"] = csv_data["cn2"][1]
                            csv_data["cn2_row2_500"] = csv_data["cn2"][2]
                            csv_data["cn2_row2_300"] = csv_data["cn2"][3]
                        csv_data["session_id"] = current_capture_session["id"]
                        append_to_csv(current_capture_session["csv_filepath"], csv_data)
                
                # Broadcast to all connected clients
                if ws_connection_manager.active_connections:
                    logger.debug(f"Broadcasting data to {len(ws_connection_manager.active_connections)} clients")
                    
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
                    logger.debug("Sent current data to WebSocket clients")
                    
                    # Also send system status only when it changed
                    current_system_status = {
                        "device_status": status_data.get("device_status", "unknown"),
                        "system_ready": status_data.get("system_ready", False),
                        "arduino_port": status_data.get("arduino_port"),
                        "timestamp": status_data.get("timestamp")
                    }
                    await ws_connection_manager.broadcast(json.dumps({
                        "type": "system_status",
                        **current_system_status
                    }))
                else:
                    logger.debug("No WebSocket clients connected, skipping broadcast")
                
            else:
                # Send error status
                error_status = {
                    "device_status": "offline",
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
                    logger.warning(f"Error status changed: {error_status['error']}")
                else:
                    logger.debug("No WebSocket clients connected, skipping error broadcast")
                
        except Exception as e:
            logger.error(f"Error in background polling: {e}")
            error_status = {
                "type": "system_status",
                "device_status": "error",
                "error": str(e),
                "arduino_port": arduino_comm.port if arduino_comm.is_connected else None,
                "system_ready": False,
                "timestamp": datetime.now().isoformat()
            }
            
            if ws_connection_manager.active_connections:
                await ws_connection_manager.broadcast(json.dumps(error_status))
        
        # Wait for next polling interval
        await asyncio.sleep(polling_interval)

# Video streaming background task
async def video_streaming_worker():
    """Background task to handle video streaming to connected clients"""
    logger.debug("Starting video streaming worker")
    
    while True:
        try:
            # Check if there are active video streaming clients
            if ws_video_manager.active_connections:
                logger.debug(f"Active video clients: {len(ws_video_manager.active_connections)}")
                
                # Ensure camera streaming is active
                if not camera.is_streaming:
                    camera.start_video_stream()
                
                # Get latest frame from camera
                frame_data = camera.get_latest_frame()
                
                if frame_data:
                    logger.debug(f"Got video frame, length: {len(frame_data)}")
                    
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
                            logger.debug(f"Sent frame to client {client_id}")
                        except Exception as e:
                            logger.warning(f"Failed to send frame to client {client_id}: {e}")
                            clients_to_remove.append(client_id)
                    
                    # Remove disconnected clients
                    for client_id in clients_to_remove:
                        ws_video_manager.disconnect(client_id)
                else:
                    logger.debug("No video frame available")
                
                # Small delay to control frame rate
                await asyncio.sleep(0.033)  # ~30 FPS
            else:
                # No video clients, stop camera streaming to save resources
                if camera.is_streaming and not data_capture_active:
                    logger.info("No video clients, stopping camera streaming")
                    camera.stop_video_stream()
                # Wait before checking again
                await asyncio.sleep(1.0)
                
        except Exception as e:
            logger.error(f"Error in video streaming worker: {e}")
            await asyncio.sleep(1.0)  # Brief delay on error
    
    logger.debug("Video streaming worker stopped")

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
        await apply_settings_to_arduino()
        
        return {"status": "success", "message": "Configuration saved and applied to Arduino"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/settings/apply")
async def apply_settings():
    """Apply settings from JSON file to Arduino"""
    try:
        await apply_settings_to_arduino()
        return {"status": "success", "message": "Settings applied to Arduino"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/camera/status")
async def get_camera_status_endpoint():
    """Get camera system status"""
    try:
        return camera.get_camera_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Calibration API endpoints
@app.post("/api/calibration/windflow/start")
async def start_windflow_calibration(fan_speed_step: int = 5, settling_time_ms: int = 1000, num_samples: int = 3):
    """Start fan-to-windflow sensor calibration"""
    try:
        session = await calibration_agent.start_windflow_calibration(fan_speed_step, settling_time_ms, num_samples)
        return {
            "status": "success",
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
            return {"status": "success", "message": "Calibration paused"}
        elif control.action == "resume":
            calibration_agent.resume_calibration()
            return {"status": "success", "message": "Calibration resumed"}
        elif control.action == "stop":
            calibration_agent.stop_calibration()
            return {"status": "success", "message": "Calibration stopped"}
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
                "status": "success",
                "has_session": True,
                "session": session_info
            }
        else:
            return {
                "status": "success",
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
            "status": "success",
            "message": "Calibration session cleared"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/calibration/hotplate/start")
async def start_hotplate_calibration(
    temp_min: float = 80.0,
    temp_max: float = 120.0,
    temp_step: float = 2.0,
    fan_speeds: str = "255,191,128,64",
    recording_duration: int = 900,
    sampling_interval: int = 10
):
    """Start hot plate 4D calibration (temperature × fan speed)"""
    try:
        # Parse fan speeds string to list - handle both single values and comma-separated lists
        if "," in fan_speeds:
            fan_speeds_list = [int(x.strip()) for x in fan_speeds.split(",") if x.strip()]
        else:
            # Handle single value
            fan_speeds_list = [int(fan_speeds.strip()) if fan_speeds.strip() else 255]

        session = await calibration_agent.start_hotplate_calibration(
            temp_min, temp_max, temp_step, fan_speeds_list, recording_duration, sampling_interval
        )
        num_temp_steps = int((temp_max - temp_min) / temp_step) + 1
        total_steps = num_temp_steps * len(fan_speeds_list)
        total_duration_hours = (total_steps * recording_duration) / 3600
        return {
            "status": "success",
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
                "status": "success",
                "lookup_table": data.get("lookup_table"),
                "calibration_id": data.get("calibration_id"),
                "timestamp": data.get("timestamp")
            }
        else:
            return {
                "status": "error",
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
            "status": "success",
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
                "status": "success",
                "polynomials": data.get('polynomials', [])
            }
        else:
            return {
                "status": "info",
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
                "status": "success",
                "metadata": data
            }
        else:
            return {
                "status": "info",
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
                    "status": "success",
                    "data": data
                }
            else:
                return {
                    "status": "info",
                    "message": "No calibration data available. Run calibration to generate data."
                }
        else:
            # Construct path to session CSV file
            session_folder = os.path.join(DEFAULT_CONFIG.calibration_data_folder, session_id)
            csv_file = os.path.join(session_folder, "calibration_data.csv")
            
            if not os.path.exists(csv_file):
                return {
                    "status": "error",
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
                "status": "success",
                "data": data
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/data-capture")
async def toggle_data_capture(request: DataCaptureRequest):
    """Start or stop data capture with camera images"""
    global data_capture_active, current_capture_session, captured_data_points, video_streaming_task, cn2_calculator, centroid_history
    
    try:
        # Check camera availability
        camera_status = camera.get_camera_status()
        camera_available = camera_status.get("initialized", False)
        
        if request.start:
            # Start data capture
            if data_capture_active:
                return {"status": "error", "message": "Data capture already active"}
                        
            # Create new capture session
            capture_folder = get_calibration_data_folder()
            image_capture_folder = create_capture_folder()
            current_capture_session = {
                "id": request.capture_id or f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "start_time": datetime.now().isoformat(),
                "folder": capture_folder,
                "image_folder": image_capture_folder,
                "data_points": []
            }
            cn2_calculator = CN2OpticalCalculator(current_capture_session['image_folder'])
            
            # Clear centroid history for new session
            centroid_history.clear()
            
            # Initialize CSV file for data capture
            csv_filepath = init_csv_file(capture_folder, f"turbulance_data{datetime.now().strftime('%Y%m%d_%H%M%S')}")
            if csv_filepath:
                current_capture_session["csv_filepath"] = csv_filepath
            else:
                logger.warning("Failed to initialize CSV file, data will only be stored in memory")
            
            data_capture_active = True
            captured_data_points = []
            
            logger.info(f"Started data capture session: {current_capture_session['id']}")
            return {
                "status": "success",
                "message": "Data capture started",
                "session_id": current_capture_session["id"],
                "folder": capture_folder,
                "camera_available": camera_available
            }
            
        else:
            # Stop data capture
            if not data_capture_active:
                return {"status": "error", "message": "No active data capture session"}
            
            session_info = current_capture_session.copy()
            session_info["end_time"] = datetime.now().isoformat()
            session_info["total_data_points"] = len(captured_data_points)
            
            logger.info(f"Stopping data capture, data points count: {len(captured_data_points)}")
             
            # Reset capture state
            data_capture_active = False
            # current_capture_session = None
            captured_data_points = []
            
            # Stop camera video streaming
            camera.stop_video_stream()
            
            # Stop video streaming worker if no other active connections
            if len(ws_video_manager.active_connections) == 0:
                logger.info("Stopping video streaming worker - no active connections")
                if video_streaming_task and not video_streaming_task.done():
                    video_streaming_task.cancel()
                    try:
                        await video_streaming_task
                    except asyncio.CancelledError:
                        pass
                video_streaming_task = None
            
            logger.info(f"Stopped data capture session: {session_info['id']}")
            return {
                "status": "success",
                "message": "Data capture stopped",
                "session_info": session_info
            }
            
    except Exception as e:
        logger.error(f"Error toggling data capture: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/data-capture/status")
async def get_data_capture_status():
    """Get current data capture status"""
    global data_capture_active, current_capture_session, captured_data_points
    
    return {
        "active": data_capture_active,
        "session": current_capture_session,
        "data_points_count": len(captured_data_points)
    }

@app.get("/api/data-capture/download")
async def download_captured_data():
    """Download captured data as CSV"""
    global current_capture_session
    
    try:
        # Try to return the existing CSV file if available
        if current_capture_session and current_capture_session.get("csv_filepath"):
            csv_filepath = current_capture_session["csv_filepath"]
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
    global polling_interval
    
    if interval < 0.5 or interval > 60:
        raise HTTPException(status_code=400, detail="Polling interval must be between 0.5 and 60 seconds")
    
    polling_interval = interval
    logger.info(f"Polling interval updated to {interval} seconds")
    
    return {
        "status": "success",
        "message": f"Polling interval set to {interval} seconds",
        "polling_interval": polling_interval
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
            logger.debug(f"Attempting to reconnect Arduino to port: {request.port}")
        else:
            logger.debug(f"Attempting to reconnect Arduino to port: {arduino_comm.port}")
        
        # Reconnect
        success = await arduino_comm.connect()
        
        if success:
            logger.debug("Arduino successfully connected")
            return {
                "status": "success", 
                "message": f"Arduino connected to {arduino_comm.port}",
                "port": arduino_comm.port
            }
        else:
            logger.error("Failed to reconnect Arduino")
            return {
                "status": "error", 
                "message": "Failed to connect to Arduino",
                "port": arduino_comm.port
            }
            
    except Exception as e:
        logger.error(f"Error reconnecting Arduino: {e}")
        return {
            "status": "error", 
            "message": f"Connection error: {str(e)}"
        }

@app.post("/api/arduino/force-reconnect")
async def force_reconnect_arduino():
    """Force immediate Arduino reconnection"""
    try:
        logger.debug("Force reconnecting Arduino...")
        await arduino_comm.disconnect()
        await asyncio.sleep(1)  # Brief delay
        success = await arduino_comm.connect()
        
        return {
            "status": "success" if success else "error",
            "message": "Force reconnection completed" if success else "Force reconnection failed",
            "connected": success,
            "port": arduino_comm.port
        }
        
    except Exception as e:
        logger.error(f"Force reconnect error: {e}")
        return {
            "status": "error",
            "message": f"Force reconnect failed: {str(e)}"
        }

@app.post("/api/history_size")
async def set_history_size(request: dict = Body(...)):
    """Set the maximum history size"""
    try:
        size = request.get("size")
        if not isinstance(size, int) or size < 10 or size > 1000:
            raise HTTPException(status_code=400, detail="History size must be between 10 and 1000")
        
        # Update the global max size
        global status_history, MAX_HISTORY_SIZE
        MAX_HISTORY_SIZE = size
        
        # Recreate deque with new max size
        old_history = list(status_history)
        status_history = deque(maxlen=MAX_HISTORY_SIZE)
        
        # Add back the most recent records (up to new limit)
        for record in old_history[-MAX_HISTORY_SIZE:]:
            status_history.append(record)
        
        logger.info(f"History size updated to {MAX_HISTORY_SIZE} records")
        
        return {
            "status": "success",
            "message": f"History size set to {MAX_HISTORY_SIZE} records",
            "max_size": MAX_HISTORY_SIZE,
            "current_count": len(status_history)
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
            "status": "success",
            "data": list(status_history),
            "count": len(status_history),
            "max_size": MAX_HISTORY_SIZE
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
        recent_data = list(status_history)[-limit:] if limit < len(status_history) else list(status_history)
        
        return {
            "status": "success",
            "data": recent_data,
            "count": len(recent_data),
            "limit": limit,
            "max_size": MAX_HISTORY_SIZE
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
        "device_status": "offline",
        "system_ready": False,
        "arduino_port": arduino_comm.port if arduino_comm.is_connected else None,
        "polling_interval": polling_interval,
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
    global video_streaming_task
    logger.info(f"New video streaming connection attempt from client: {client_id}")
    
    # Check camera status before accepting connection
    camera_status = camera.get_camera_status()
    camera_available = camera_status.get("initialized", False)
    
    if not camera_available:
        logger.warning(f"Camera not connected - rejecting video streaming connection from client: {client_id}")
        await websocket.accept()
        await websocket.send_text(json.dumps({
            "type": "error",
            "message": "Camera not connected or not available",
            "timestamp": datetime.now().isoformat()
        }))
        await websocket.close()
        return
    
    await ws_video_manager.connect(websocket, client_id)
    
    # Start video streaming worker if not already running
    if video_streaming_task is None or video_streaming_task.done():
        video_streaming_task = asyncio.create_task(video_streaming_worker())
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
