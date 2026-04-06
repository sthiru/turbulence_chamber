import sys
import os

# Add current directory to Python path for module imports
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks, Body
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict
from functools import lru_cache
import asyncio
import json
import time
import logging
from datetime import datetime
from collections import deque
import csv
import io
import math
import os

from models import (
    TemperatureCommand, FanCommand, HotPlateCommand, 
    SystemStatus, ArduinoResponse, DeviceStatus
)
from arduino_comm import arduino_comm
from camera_acquisition import (
    initialize_camera_system, capture_camera_image, get_camera_status, cleanup_camera_system,
    start_camera_video_stream, stop_camera_video_stream, get_latest_video_frame,
    get_camera_streaming_status, add_video_streaming_client, remove_video_streaming_client,
    diagnose_camera_connection, get_camera_instance
)
from cn2_optical import calculate_cn2_optical, get_cn2_status

# Pydantic model for reconnect request
class ReconnectRequest(BaseModel):
    port: str = None

# Pydantic model for hotplate toggle request
class HotPlateToggleRequest(BaseModel):
    state: bool

# Pydantic model for data capture request
class DataCaptureRequest(BaseModel):
    start: bool
    capture_id: Optional[str] = None

# Pydantic model for data point with image
class DataPointWithImage(BaseModel):
    timestamp: str
    temperatures: List[float]
    target_temperatures: List[float]
    fan_speeds: List[int]
    hot_plate_states: List[bool]
    cn2: Optional[float] = None
    cn2_optical: Optional[float] = None
    temperature_bme: List[float]
    humidity: List[float]
    pressure: List[float]
    image_filename: Optional[str] = None

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
MAX_HISTORY_SIZE = 1000

# Initialize FastAPI app
app = FastAPI(
    title="Temperature Control System",
    description="API for controlling Arduino-based temperature control system",
    version="1.0.0"
)

# Mount static files
static_dir = os.path.join(os.path.dirname(__file__), "..", "web")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Mount camera images directory
camera_images_dir = os.path.join(os.path.dirname(__file__), "..", "camera_images")
if os.path.exists(camera_images_dir):
    app.mount("/camera_images", StaticFiles(directory=camera_images_dir), name="camera_images")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket client connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket client disconnected. Total connections: {len(self.active_connections)}")

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        logger.debug(f"Broadcasting message to {len(self.active_connections)} clients: {message[:100]}...")
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                # Connection closed, remove it
                logger.warning("Failed to send to WebSocket client, removing connection")
                self.active_connections.remove(connection)

# Video streaming connection manager
class VideoStreamManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.active_connections[client_id] = websocket
        logger.info(f"Video stream client connected: {client_id}. Total video connections: {len(self.active_connections)}")
        
        # Add client to camera streaming
        add_video_streaming_client(client_id, camera_images_folder)

    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]
            logger.info(f"Video stream client disconnected: {client_id}. Total video connections: {len(self.active_connections)}")
            
            # Remove client from camera streaming
            remove_video_streaming_client(client_id, camera_images_folder)

    async def send_frame(self, client_id: str, frame_data: str):
        if client_id in self.active_connections:
            try:
                await self.active_connections[client_id].send_text(frame_data)
            except Exception as e:
                logger.warning(f"Failed to send video frame to client {client_id}: {e}")
                # Remove disconnected client
                self.disconnect(client_id)

manager = ConnectionManager()
video_manager = VideoStreamManager()

# Data storage for Arduino status records
status_history = deque(maxlen=1000)  # Store last 1000 status updates
status_update_queue = asyncio.Queue()
video_stream_manager = VideoStreamManager()

# Data capture state
data_capture_active = False
current_capture_session = None
captured_data_points = []

def create_capture_folder() -> str:
    """Create a date-based folder for camera images"""
    now = datetime.now()
    date_folder = now.strftime("%d_%b_%Y")  # e.g., "03_Apr_2026"
    time_folder = now.strftime("%H_%M")     # e.g., "14_30"
    
    # Create folder structure: camera_images/DD_MMM_YYYY/HH_MM
    base_folder = os.path.join("camera_images", date_folder, time_folder)
    
    try:
        os.makedirs(base_folder, exist_ok=True)
        logger.info(f"Created capture folder: {base_folder}")
        return base_folder
    except Exception as e:
        logger.error(f"Failed to create capture folder: {e}")
        return "camera_images"  # Fallback to base folder

def capture_and_save_image(capture_folder: str) -> Optional[str]:
    """Capture and save a camera image with timestamp"""
    try:
        logger.debug(f"Attempting to capture and save image to: {capture_folder}")
        
        # Get camera instance
        camera = get_camera_instance(camera_images_folder)
        
        # Capture image with the correct folder path
        image = camera.capture_image()
        
        if image is not None:
            logger.debug(f"Image captured successfully, shape: {image.shape}")
            
            # Generate filename with timestamp
            timestamp = datetime.now()
            filename = f"camera_{timestamp.strftime('%Y%m%d_%H%M%S_%f')[:-3]}.png"
            filepath = os.path.join(capture_folder, filename)
            
            logger.debug(f"Saving image to: {filepath}")
            
            # Save image to the session-specific folder
            success = cv2.imwrite(filepath, image)
            
            if success:
                logger.info(f"Image saved successfully: {filepath}")
                return filename
            else:
                logger.error(f"Failed to save image: {filepath}")
                return None
        else:
            logger.warning("Failed to capture image - capture_image returned None")
            return None
            
    except Exception as e:
        logger.error(f"Error capturing and saving image: {e}")
        import traceback
        traceback.print_exc()
        return None

# Global variables for background polling
polling_interval = 3.0  # Default polling interval in seconds
background_task = None
video_streaming_task = None
last_broadcast_time = 0
historical_data_sent = False  # Track if full historical data has been sent

# CN² calculation function
def calculate_cn2(temperatures, bme_temperatures, bme_pressure, r=0.5):
    """
    Calculate CN² (structure function parameter) for turbulence
    
    Formula: (7.9*10^-5 * (P/T^2))*((dt^2)/r^(2/3))
    
    Args:
        temperatures: List of temperature readings from DS18B20 sensors
        bme_temperatures: List of temperature readings from BME280 sensors
        pressure: Pressure in hPa (default 1010 hPa)
        r: Radial distance (default 0.5)
    
    Returns:
        CN² value
    """
    try:
        # Get the minimum temperature from BME280 sensors (ambient temperature)
        if(len(bme_temperatures) > 0):
            ambient_temp = min(bme_temperatures)
            ambient_temp = ambient_temp if ambient_temp > 0.0 else max(bme_temperatures)
        else:
            ambient_temp = 25.0  # Default to room temperature

        # Get the minimum peressure from BME senesor
        if(len(bme_pressure) > 0):
            pressure = min(bme_pressure)
            pressure = pressure if pressure > 0.0 else max(bme_pressure)
        else:
            pressure = 1010.0  # Default to standard pressure
        
        if ambient_temp <= 0:
            logger.warning(f"Invalid ambient temperature for CN²: {ambient_temp}")
            ambient_temp = 25.0  # Default to room temperature
        
        if pressure <= 0:
            logger.warning(f"Invalid pressure for CN²: {pressure}")
            pressure = 1010.0  # Default to standard pressure

        ambient_temp_kelvin = ambient_temp + 273.15
        
        # Calculate dt^2 (difference between min and max temperatures)
        if not temperatures or len(temperatures) < 2:
            return 0.0
        
        valid_temps = [temp for temp in temperatures if temp > -100]  # Filter out error values
        if len(valid_temps) < 2:
            return 0.0
        
        temp_min = min(valid_temps)
        temp_max = max(valid_temps)
        dt_squared = (temp_max - temp_min) ** 2
        
        # Calculate CN² using the formula
        cn2 = (7.9e-5 * (pressure / (ambient_temp_kelvin ** 2)))**2 * (dt_squared / (r ** (2/3)))
        
        logger.debug(f"CN² calculation: P={pressure}hPa, T={ambient_temp}°C, dt²={dt_squared:.2f}, CN²={cn2:.2e}")
        
        return cn2
        
    except Exception as e:
        logger.error(f"Error calculating CN²: {e}")
        return 0.0

# Background polling task
async def background_status_polling():
    """Background task to poll Arduino for status and broadcast to WebSocket clients"""
    global last_broadcast_time, historical_data_sent, last_system_status
    
    # Initialize last_system_status
    last_system_status = None
    
    while True:
        try:
            # Get status from Arduino
            response = await arduino_comm.get_status()
            
            if response.status == "ok":
                status_data = response.data.dict()
                status_data["device_status"] = "online"
                status_data["arduino_port"] = arduino_comm.port if arduino_comm.is_connected else None
                status_data["system_ready"] = True  # System is ready when Arduino responds successfully
                status_data["timestamp"] = datetime.now().isoformat()
                
                # Calculate CN² and add to status data
                try:
                    cn2_value = calculate_cn2(
                        status_data.get("temperatures", []),
                        status_data.get("temperature_bme", []),
                        status_data.get("pressure", [])
                    )
                    status_data["cn2"] = cn2_value
                except Exception as e:
                    logger.warning(f"Error calculating CN²: {e}")
                    status_data["cn2"] = None
                
                # Calculate optical CN² if we have temperature differences
                try:
                    cn2_optical = calculate_cn2_optical(camera_images_folder)
                    status_data["cn2_optical"] = cn2_optical
                except Exception as e:
                    logger.warning(f"Error calculating optical CN²: {e}")
                    status_data["cn2_optical"] = None
                
                # Capture camera image if data capture is active
                image_filename = None
                global data_capture_active, current_capture_session, captured_data_points
                
                if data_capture_active and current_capture_session:
                    try:
                        logger.debug(f"Data capture active, session: {current_capture_session['id']}")
                        logger.debug(f"Capture folder: {current_capture_session['folder']}")
                        
                        image_filename = capture_and_save_image(current_capture_session["folder"])
                        
                        if image_filename:
                            logger.info(f"Successfully captured image: {image_filename}")
                        else:
                            logger.warning("Image capture returned None")
                    except Exception as e:
                        logger.warning(f"Failed to capture image during data capture: {e}")
                        import traceback
                        traceback.print_exc()
                else:
                    logger.debug("Data capture not active or no session")
                
                # Add image filename to status data
                status_data["image_filename"] = image_filename
                
                # Store in history
                status_history.append(status_data.copy())
                
                # Store in captured data points if capture is active
                if data_capture_active and current_capture_session:
                    data_point = status_data.copy()
                    data_point["session_id"] = current_capture_session["id"]
                    captured_data_points.append(data_point)
                    logger.debug(f"Captured data point {len(captured_data_points)} with image: {image_filename}")
                
                # Broadcast to all connected clients
                if manager.active_connections:
                    logger.debug(f"Broadcasting data to {len(manager.active_connections)} clients")
                    
                    # Always send current data as current_data message
                    current_data_message = {
                        "type": "current_data",
                        "data": [{
                            "temperatures": status_data.get("temperatures", []),
                            "target_temperatures": status_data.get("target_temperatures", []),
                            "fan_speeds": status_data.get("fan_speeds", []),
                            "hot_plate_states": status_data.get("hot_plate_states", []),
                            "temperature_bme": status_data.get("temperature_bme", []),
                            "humidity": status_data.get("humidity", []),
                            "pressure": status_data.get("pressure", []),
                            "cn2": status_data.get("cn2", 0.0),
                            "cn2_optical": status_data.get("cn2_optical"),
                            "cn2_status": status_data.get("cn2_status"),
                            "camera_image": status_data.get("camera_image"),
                            "camera_status": status_data.get("camera_status"),
                            "image_filename": status_data.get("image_filename"),
                            "timestamp": status_data.get("timestamp")
                        }],
                        "count": 1,
                        "latest_only": True
                    }
                    
                    await manager.broadcast(json.dumps(current_data_message))
                    logger.debug("Sent current data to WebSocket clients")
                    
                    # Also send system status if it changed
                    current_system_status = {
                        "device_status": status_data.get("device_status", "unknown"),
                        "system_ready": status_data.get("system_ready", False),
                        "arduino_port": status_data.get("arduino_port"),
                        "polling_interval": polling_interval,
                        "timestamp": status_data.get("timestamp")
                    }
                    
                    system_status_changed = (
                        not last_system_status or
                        current_system_status["device_status"] != last_system_status.get("device_status") or
                        current_system_status["system_ready"] != last_system_status.get("system_ready") or
                        current_system_status["arduino_port"] != last_system_status.get("arduino_port")
                    )
                    
                    if system_status_changed or last_broadcast_time == 0:
                        await manager.broadcast(json.dumps({
                            "type": "system_status",
                            **current_system_status
                        }))
                        last_system_status = current_system_status.copy()
                        logger.debug(f"System status changed: {current_system_status['device_status']} | Ready: {current_system_status['system_ready']}")
                else:
                    logger.debug("No WebSocket clients connected, skipping broadcast")
                
            else:
                # Send error status
                error_status = {
                    "device_status": "offline",
                    "error": response.msg if response.msg else "Arduino not connected",
                    "arduino_port": arduino_comm.port if arduino_comm.is_connected else None,
                    "temperatures": [0.0] * 5,  # 5 sensors
                    "target_temperatures": [80.0, 80.0],
                    "fan_speeds": [0, 0, 0, 0],
                    "hot_plate_states": [False, False],
                    "system_ready": False,
                    "timestamp": datetime.now().isoformat()
                }
                
                # Store error in history
                status_history.append(error_status.copy())
                
                if manager.active_connections:
                    # Check if error status changed
                    current_error_status = {
                        "device_status": "offline",
                        "system_ready": False,
                        "arduino_port": error_status.get("arduino_port"),
                        "polling_interval": polling_interval,
                        "timestamp": error_status.get("timestamp"),
                        "error": error_status.get("error")
                    }
                    
                    error_status_changed = (
                        not last_system_status or
                        current_error_status["device_status"] != last_system_status.get("device_status") or
                        current_error_status["error"] != last_system_status.get("error", "")
                    )
                    
                    if error_status_changed:
                        await manager.broadcast(json.dumps({
                            "type": "system_status",
                            **current_error_status
                        }))
                        last_system_status = current_error_status.copy()
                        logger.warning(f"Error status changed: {error_status['error']}")
                        
                        # Reset historical data flag when error status changes
                        historical_data_sent = False
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
            
            if manager.active_connections:
                await manager.broadcast(json.dumps(error_status))
        
        # Wait for next polling interval
        await asyncio.sleep(polling_interval)

# Video streaming background task
async def video_streaming_worker():
    """Background task to handle video streaming to connected clients"""
    logger.debug("Starting video streaming worker")
    
    while True:
        try:
            # Check if there are active video streaming clients
            if video_manager.active_connections:
                logger.debug(f"Active video clients: {len(video_manager.active_connections)}")
                
                # Get latest frame from camera
                frame_data = get_latest_video_frame(camera_images_folder)
                
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
                    for client_id in list(video_manager.active_connections.keys()):
                        try:
                            await video_manager.send_frame(client_id, message)
                            logger.debug(f"Sent frame to client {client_id}")
                        except Exception as e:
                            logger.warning(f"Failed to send frame to client {client_id}: {e}")
                            clients_to_remove.append(client_id)
                    
                    # Remove disconnected clients
                    for client_id in clients_to_remove:
                        video_manager.disconnect(client_id)
                else:
                    logger.debug("No video frame available")
                
                # Small delay to control frame rate
                await asyncio.sleep(0.033)  # ~30 FPS
            else:
                # No video clients, wait longer
                await asyncio.sleep(1.0)
                
        except Exception as e:
            logger.error(f"Error in video streaming worker: {e}")
            await asyncio.sleep(1.0)  # Brief delay on error
    
    logger.debug("Video streaming worker stopped")

@app.on_event("startup")
async def startup_event():
    """Initialize Arduino connection and start background polling"""
    global background_task, video_streaming_task
    
    logger.info("Starting Temperature Control System server...")
    
    # Connect to Arduino
    logger.debug(f"Attempting to connect to Arduino on {arduino_comm.port}...")
    success = await arduino_comm.connect()
    if success:
        logger.debug("Arduino connected successfully")
        
        # Get initial status and store it
        try:
            response = await arduino_comm.get_status()
            if response.status == "ok" and response.data:
                status_data = response.data.dict()
                status_data["device_status"] = "online"
                status_data["arduino_port"] = arduino_comm.port
                status_data["system_ready"] = True  # System is ready when Arduino responds successfully
                status_data["timestamp"] = datetime.now().isoformat()
                status_history.append(status_data.copy())
                logger.debug("Initial Arduino status stored in history")
            else:
                logger.warning("Failed to get initial Arduino status")
        except Exception as e:
            logger.error(f"Error getting initial Arduino status: {e}")
        
        # Start background polling task
        background_task = asyncio.create_task(background_status_polling())
        
        # Start video streaming worker
        video_streaming_task = asyncio.create_task(video_streaming_worker())
        
        # Auto-start video streaming
        logger.info("Auto-starting video streaming...")
        start_camera_video_stream(camera_images_folder)
        
    else:
        logger.warning("Failed to connect to Arduino - server will run without Arduino")
        logger.info("Please check:")
        logger.info("1. Arduino is connected via USB")
        logger.info("2. Correct COM port is being used")
        logger.info("3. Arduino sketch is uploaded and running")
        logger.info("4. No other program is using the serial port")
        
        # Start background polling anyway (will show offline status)
        background_task = asyncio.create_task(background_status_polling())
        
        # Start video streaming worker anyway
        video_streaming_task = asyncio.create_task(video_streaming_worker())
        
        # Auto-start video streaming
        logger.info("Auto-starting video streaming...")
        start_camera_video_stream(camera_images_folder)

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    await arduino_comm.disconnect()
    cleanup_camera_system()

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
    web_file = os.path.join(os.path.dirname(__file__), "..", "web", "index.html")
    if os.path.exists(web_file):
        return FileResponse(web_file)
    else:
        raise HTTPException(status_code=404, detail="Main page not found")

@app.get("/video-test", response_class=HTMLResponse)
async def video_test():
    """Serve the video test page"""
    web_file = os.path.join(os.path.dirname(__file__), "..", "web", "video_test.html")
    if os.path.exists(web_file):
        return FileResponse(web_file)
    else:
        raise HTTPException(status_code=404, detail="Video test page not found")

@app.get("/main")
async def main():
    """Serve the main visualization interface"""
    web_file = os.path.join(os.path.dirname(__file__), "..", "web", "dashboard.html")
    if os.path.exists(web_file):
        return FileResponse(web_file)
    else:
        return {"message": "Main interface not found", "version": "1.0.0"}

@app.get("/api/status")
async def get_system_status():
    """Get current system status"""
    try:
        response = await arduino_comm.get_status()
        if response.status == "ok":
            return response.data
        else:
            raise HTTPException(status_code=500, detail=response.msg)
    except Exception as e:
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

@app.get("/api/sensors")
async def get_sensor_data():
    """Get all sensor data"""
    try:
        response = await arduino_comm.get_status()
        if response.status == "ok":
            return {
                "temperatures": response.data.temperatures,
                "target_temperatures": response.data.target_temperatures,
                "system_ready": response.data.system_ready
            }
        else:
            raise HTTPException(status_code=500, detail=response.msg)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/test")
async def test_endpoint():
    """Simple test endpoint to verify server is working"""
    return {
        "status": "ok",
        "message": "Server is working",
        "arduino_port": arduino_comm.port,
        "connected": arduino_comm.is_connected,
        "camera_status": get_camera_status(camera_images_folder),
        "cn2_optical_status": get_cn2_status(camera_images_folder)
    }

@app.get("/api/camera/status")
async def get_camera_status_endpoint():
    """Get camera system status"""
    try:
        return get_camera_status(camera_images_folder)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/camera/capture")
async def capture_camera_image_endpoint():
    """Manually trigger camera image capture"""
    try:
        filename = capture_camera_image(camera_images_folder)
        if filename:
            return {
                "status": "success",
                "message": "Image captured successfully",
                "filename": filename
            }
        else:
            return {
                "status": "error",
                "message": "Failed to capture image"
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/cn2/optical/status")
async def get_cn2_optical_status():
    """Get CN² optical calculation status"""
    try:
        return get_cn2_status(camera_images_folder)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/cn2/optical/calculate")
async def calculate_cn2_optical_endpoint():
    """Manually trigger CN² optical calculation"""
    try:
        cn2_value = calculate_cn2_optical(camera_images_folder)
        if cn2_value is not None:
            return {
                "status": "success",
                "message": "CN² optical calculated successfully",
                "cn2_optical": cn2_value,
                "cn2_optical_scientific": f"{cn2_value:.2e} m^(-2/3)"
            }
        else:
            return {
                "status": "info",
                "message": "CN² optical calculation not ready - insufficient images",
                "cn2_optical": None
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/camera/video/start")
async def start_video_stream():
    """Start video streaming from camera"""
    try:
        success = start_camera_video_stream(camera_images_folder)
        if success:
            return {
                "status": "success",
                "message": "Video streaming started successfully"
            }
        else:
            return {
                "status": "error",
                "message": "Failed to start video streaming"
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/camera/video/stop")
async def stop_video_stream():
    """Stop video streaming from camera"""
    try:
        stop_camera_video_stream(camera_images_folder)
        return {
            "status": "success",
            "message": "Video streaming stopped successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/camera/video/status")
async def get_video_stream_status():
    """Get video streaming status"""
    try:
        return get_camera_streaming_status(camera_images_folder)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/camera/diagnose")
async def diagnose_camera():
    """Diagnose camera connection issues"""
    try:
        success = diagnose_camera_connection()
        return {
            "status": "success" if success else "error",
            "message": "Camera diagnosis completed" if success else "Camera connection issues found"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/data-capture")
async def toggle_data_capture(request: DataCaptureRequest):
    """Start or stop data capture with camera images"""
    global data_capture_active, current_capture_session, captured_data_points
    
    try:
        if request.start:
            # Start data capture
            if data_capture_active:
                return {"status": "error", "message": "Data capture already active"}
            
            # Create new capture session
            capture_folder = create_capture_folder()
            current_capture_session = {
                "id": request.capture_id or f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "start_time": datetime.now().isoformat(),
                "folder": capture_folder,
                "data_points": []
            }
            
            data_capture_active = True
            captured_data_points = []
            
            logger.info(f"Started data capture session: {current_capture_session['id']}")
            return {
                "status": "success",
                "message": "Data capture started",
                "session_id": current_capture_session["id"],
                "folder": capture_folder
            }
            
        else:
            # Stop data capture
            if not data_capture_active:
                return {"status": "error", "message": "No active data capture session"}
            
            session_info = current_capture_session.copy()
            session_info["end_time"] = datetime.now().isoformat()
            session_info["total_data_points"] = len(captured_data_points)
            
            # Reset capture state
            data_capture_active = False
            current_capture_session = None
            
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
    global captured_data_points
    
    if not captured_data_points:
        raise HTTPException(status_code=404, detail="No captured data available")
    
    try:
        # Create CSV content
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        header = [
            'timestamp', 'session_id',
            'temp_sensor_1', 'temp_sensor_2', 'temp_sensor_3', 'temp_sensor_4', 'temp_sensor_5',
            'target_temp_1', 'target_temp_2',
            'fan_speed_1', 'fan_speed_2', 'fan_speed_3', 'fan_speed_4',
            'hot_plate_1', 'hot_plate_2',
            'cn2_thermal', 'cn2_optical',
            'bme_temp_1', 'bme_temp_2', 'bme_temp_3', 'bme_temp_4', 'bme_temp_5',
            'humidity_1', 'humidity_2', 'humidity_3', 'humidity_4', 'humidity_5',
            'pressure_1', 'pressure_2', 'pressure_3', 'pressure_4', 'pressure_5',
            'image_filename'
        ]
        writer.writerow(header)
        
        # Write data points
        for point in captured_data_points:
            row = [
                point['timestamp'],
                point.get('session_id', ''),
                *(point.get('temperatures', [])),
                *(point.get('target_temperatures', [])),
                *(point.get('fan_speeds', [])),
                *(point.get('hot_plate_states', [])),
                point.get('cn2', ''),
                point.get('cn2_optical', ''),
                *(point.get('temperature_bme', [])),
                *(point.get('humidity', [])),
                *(point.get('pressure', [])),
                point.get('image_filename', '')
            ]
            writer.writerow(row)
        
        # Create response
        csv_content = output.getvalue()
        output.close()
        
        filename = f"turbulence_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        return StreamingResponse(
            io.StringIO(csv_content),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except Exception as e:
        logger.error(f"Error creating CSV download: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/camera/test-image")
async def get_test_image():
    """Get a test image for video display debugging"""
    try:
        # Create a simple test image using PIL
        import numpy as np
        from io import BytesIO
        import base64
        
        # Create a colorful test pattern
        width, height = 640, 480
        image = np.zeros((height, width, 3), dtype=np.uint8)
        
        # Create a test pattern
        for y in range(height):
            for x in range(width):
                # Create a gradient pattern
                image[y, x, 0] = int((x / width) * 255)  # Red gradient
                image[y, x, 1] = int((y / height) * 255)  # Green gradient
                image[y, x, 2] = int(((x + y) / (width + height)) * 255)  # Blue gradient
        
        # Add some text or pattern
        center_x, center_y = width // 2, height // 2
        cv2.circle(image, (center_x, center_y), 100, (255, 255, 255), 2)
        cv2.putText(image, "TEST IMAGE", (center_x - 80, center_y), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        
        # Convert to JPEG and base64
        pil_image = Image.fromarray(image)
        buffer = BytesIO()
        pil_image.save(buffer, format='JPEG', quality=90)
        img_str = base64.b64encode(buffer.getvalue()).decode()
        
        return {
            "status": "success",
            "image_data": img_str,
            "timestamp": datetime.now().isoformat(),
            "message": "Test image generated successfully"
        }
        
    except Exception as e:
        # If OpenCV is not available, create a simple pattern with PIL
        try:
            from PIL import Image, ImageDraw
            import base64
            from io import BytesIO
            
            # Create a simple test image
            image = Image.new('RGB', (640, 480), color='black')
            draw = ImageDraw.Draw(image)
            
            # Draw some test patterns
            draw.rectangle([50, 50, 590, 430], outline='white', width=2)
            draw.ellipse([270, 190, 370, 290], fill='red', outline='white')
            draw.text([250, 240], "TEST", fill='white')
            
            # Convert to JPEG and base64
            buffer = BytesIO()
            image.save(buffer, format='JPEG', quality=90)
            img_str = base64.b64encode(buffer.getvalue()).decode()
            
            return {
                "status": "success",
                "image_data": img_str,
                "timestamp": datetime.now().isoformat(),
                "message": "Test image generated successfully (PIL only)"
            }
        except Exception as e2:
            raise HTTPException(status_code=500, detail=f"Failed to generate test image: {str(e)}")

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

def generate_csv(data: list, filename_prefix: str = "arduino_status"):
    """Generate CSV content from status data"""
    output = io.StringIO()
    
    if not data:
        # Create empty CSV with headers
        writer = csv.writer(output)
        writer.writerow([
            "timestamp", "device_status", "arduino_port", "system_ready",
            "temp_sensor_1", "temp_sensor_2", "temp_sensor_3", "temp_sensor_4", "temp_sensor_5",
            "target_temp_1", "target_temp_2",
            "fan_speed_1", "fan_speed_2", "fan_speed_3", "fan_speed_4",
            "hot_plate_1", "hot_plate_2",
            "bme_temp_1", "bme_temp_2", "bme_temp_3", "bme_temp_4",
            "bme_humidity_1", "bme_humidity_2", "bme_humidity_3", "bme_humidity_4",
            "bme_pressure_1", "bme_pressure_2", "bme_pressure_3", "bme_pressure_4",
            "error"
        ])
        return output.getvalue(), filename_prefix
    
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        "timestamp", "device_status", "arduino_port", "system_ready",
        "temp_sensor_1", "temp_sensor_2", "temp_sensor_3", "temp_sensor_4", "temp_sensor_5",
        "target_temp_1", "target_temp_2",
        "fan_speed_1", "fan_speed_2", "fan_speed_3", "fan_speed_4",
        "hot_plate_1", "hot_plate_2",
        "bme_temp_1", "bme_temp_2", "bme_temp_3", "bme_temp_4",
        "bme_humidity_1", "bme_humidity_2", "bme_humidity_3", "bme_humidity_4",
        "bme_pressure_1", "bme_pressure_2", "bme_pressure_3", "bme_pressure_4",
        "error"
    ])
    
    # Write data rows
    for record in data:
        row = [
            record.get("timestamp", ""),
            record.get("device_status", ""),
            record.get("arduino_port", ""),
            record.get("system_ready", ""),
        ]
        
        # Temperature sensors
        temps = record.get("temperatures", [])
        for i in range(5):
            row.append(temps[i] if i < len(temps) else "")
        
        # Target temperatures
        target_temps = record.get("target_temperatures", [])
        for i in range(2):
            row.append(target_temps[i] if i < len(target_temps) else "")
        
        # Fan speeds
        fan_speeds = record.get("fan_speeds", [])
        for i in range(4):
            row.append(fan_speeds[i] if i < len(fan_speeds) else "")
        
        # Hot plate states
        hot_plates = record.get("hot_plate_states", [])
        for i in range(2):
            row.append(hot_plates[i] if i < len(hot_plates) else "")
        
        # BME280 temperatures
        bme_temps = record.get("temperature_bme", [])
        for i in range(4):
            row.append(bme_temps[i] if i < len(bme_temps) else "")
        
        # BME280 humidity
        bme_humidity = record.get("humidity", [])
        for i in range(4):
            row.append(bme_humidity[i] if i < len(bme_humidity) else "")
        
        # BME280 pressure
        bme_pressure = record.get("pressure", [])
        for i in range(4):
            row.append(bme_pressure[i] if i < len(bme_pressure) else "")
        
        # Error message
        row.append(record.get("error", ""))
        
        writer.writerow(row)
    
    return output.getvalue(), filename_prefix

@app.get("/api/download/csv")
async def download_csv():
    """Download all available historical data as CSV"""
    try:
        csv_content, filename = generate_csv(list(status_history))
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"arduino_status_{timestamp}.csv"
        
        # Create streaming response
        return StreamingResponse(
            io.StringIO(csv_content),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        logger.error(f"Error generating CSV: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate CSV: {str(e)}")

@app.get("/api/download/csv/{limit:int}")
async def download_csv_limit(limit: int):
    """Download limited number of recent records as CSV"""
    try:
        if limit <= 0:
            raise HTTPException(status_code=400, detail="Limit must be greater than 0")
        
        # Get the most recent records
        recent_data = list(status_history)[-limit:] if limit < len(status_history) else list(status_history)
        
        csv_content, filename = generate_csv(recent_data, f"arduino_status_recent_{limit}")
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"arduino_status_recent_{limit}_{timestamp}.csv"
        
        # Create streaming response
        return StreamingResponse(
            io.StringIO(csv_content),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating limited CSV: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate CSV: {str(e)}")

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
    await manager.connect(websocket)
    
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
                    await websocket.send_text('{"type":"pong"}')
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
    
    manager.disconnect(websocket)

@app.websocket("/ws/video/{client_id}")
async def video_streaming_websocket(websocket: WebSocket, client_id: str):
    """WebSocket endpoint for video streaming"""
    logger.info(f"New video streaming connection attempt from client: {client_id}")
    
    await video_manager.connect(websocket, client_id)
    
    # Ensure video streaming is started
    streaming_status = get_camera_streaming_status(camera_images_folder)
    if not streaming_status.get("is_streaming", False):
        logger.info("Starting video streaming for new client connection")
        start_camera_video_stream(camera_images_folder)
        # Wait a moment for streaming to start
        await asyncio.sleep(1.0)
        streaming_status = get_camera_streaming_status(camera_images_folder)
    
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
                        success = start_camera_video_stream(camera_images_folder)
                        await websocket.send_text(json.dumps({
                            "type": "stream_response",
                            "action": "start",
                            "success": success,
                            "message": "Video streaming started" if success else "Failed to start video streaming",
                            "timestamp": datetime.now().isoformat()
                        }))
                elif data.get("type") == "stop_stream":
                    # Stop video streaming
                    stop_camera_video_stream(camera_images_folder)
                    await websocket.send_text(json.dumps({
                        "type": "stream_response",
                        "action": "stop",
                        "success": True,
                        "message": "Video streaming stopped successfully",
                        "timestamp": datetime.now().isoformat()
                    }))
                elif data.get("type") == "test_frame":
                    # Send a test frame
                    test_frame = get_latest_video_frame(camera_images_folder)
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
    
    video_manager.disconnect(client_id)

# Initialize camera system
camera_images_folder = os.path.join(os.path.dirname(__file__), "..", "camera_images")
pfs_file_path = os.path.join(os.path.dirname(__file__), "..", "camera_settings.pfs")  # Default PFS file path

# Check if PFS file exists
if os.path.exists(pfs_file_path):
    logger.info(f"Found PFS file: {pfs_file_path}")
    camera_initialized = initialize_camera_system(camera_images_folder, pfs_file_path)
else:
    logger.info(f"No PFS file found at {pfs_file_path}, using default camera settings")
    camera_initialized = initialize_camera_system(camera_images_folder)
if camera_initialized:
    logger.info(f"Camera system initialized successfully")
else:
    logger.warning("Camera system initialization failed - will run in simulation mode")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
