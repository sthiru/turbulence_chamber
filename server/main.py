import sys
import os

# Add current directory to Python path for module imports
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Body
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio
import json
import time
import logging
from datetime import datetime
from collections import deque
import csv
import io
import math

from models import (
    TemperatureCommand, FanCommand, HotPlateCommand, 
    SystemStatus, ArduinoResponse, DeviceStatus
)
from arduino_comm import arduino_comm

# Pydantic model for reconnect request
class ReconnectRequest(BaseModel):
    port: str = None

# Pydantic model for hotplate toggle request
class HotPlateToggleRequest(BaseModel):
    state: bool

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

manager = ConnectionManager()

# Data storage for Arduino status records
status_history = deque(maxlen=100)  # Store last 100 records
MAX_HISTORY_SIZE = 100

# Global variables for background polling
polling_interval = 3.0  # Default polling interval in seconds
background_task = None
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
    """Continuously poll Arduino for status and store in cache"""
    global last_broadcast_time, last_system_status, historical_data_sent
    
    logger.info(f"Starting background status polling with {polling_interval}s interval")
    last_system_status = {}  # Track last system status to detect changes
    historical_data_sent = False  # Reset for new connections
    
    while True:
        try:
            current_time = time.time()
            
            # Get status from Arduino
            response = await arduino_comm.get_status()
            
            if response.status == "ok" and response.data:
                status_data = response.data.dict()
                status_data["device_status"] = "online"
                status_data["arduino_port"] = arduino_comm.port if arduino_comm.is_connected else None
                status_data["timestamp"] = datetime.now().isoformat()
                
                # Calculate CN² and add to status data
                temperatures = status_data.get("temperatures", [])
                bme_temperatures = status_data.get("temperature_bme", [])
                bme_pressure = status_data.get("pressure", [])
                
                cn2_value = calculate_cn2(temperatures, bme_temperatures, bme_pressure)
                status_data["cn2"] = cn2_value
                
                # Store in history
                status_history.append(status_data.copy())
                
                # Broadcast to all connected clients
                if manager.active_connections:
                    # Check if system status changed (for system_status messages)
                    current_system_status = {
                        "device_status": status_data.get("device_status", "unknown"),
                        "system_ready": status_data.get("system_ready", False),
                        "arduino_port": status_data.get("arduino_port"),
                        "polling_interval": polling_interval,
                        "timestamp": status_data.get("timestamp")
                    }
                    
                    # Send system status only if it changed or first broadcast
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
                        logger.info(f"System status changed: {current_system_status['device_status']} | Ready: {current_system_status['system_ready']}")
                        
                        # Reset historical data flag when system status changes (new connection)
                        if system_status_changed:
                            historical_data_sent = False
                    
                    # Send data based on whether historical data has been sent
                    if not historical_data_sent:
                        # Send complete historical data for first time (without system status fields)
                        historical_data_message = {
                            "type": "historical_data",
                            "data": [
                                {
                                    "temperatures": record.get("temperatures", []),
                                    "target_temperatures": record.get("target_temperatures", []),
                                    "fan_speeds": record.get("fan_speeds", []),
                                    "hot_plate_states": record.get("hot_plate_states", []),
                                    "temperature_bme": record.get("temperature_bme", []),
                                    "humidity": record.get("humidity", []),
                                    "pressure": record.get("pressure", []),
                                    "cn2": record.get("cn2", 0.0),
                                    "timestamp": record.get("timestamp")
                                } for record in status_history
                            ],
                            "count": len(status_history),
                            "max_size": MAX_HISTORY_SIZE
                        }
                        await manager.broadcast(json.dumps(historical_data_message))
                        historical_data_sent = True
                        logger.info(f"Sent complete historical data: {len(status_history)} records")
                    else:
                        # Send only current data (last 10 records) for subsequent updates (without system status fields)
                        recent_records = list(status_history)[-10:] if len(status_history) > 10 else list(status_history)
                        current_data_message = {
                            "type": "current_data",
                            "data": [
                                {
                                    "temperatures": record.get("temperatures", []),
                                    "target_temperatures": record.get("target_temperatures", []),
                                    "fan_speeds": record.get("fan_speeds", []),
                                    "hot_plate_states": record.get("hot_plate_states", []),
                                    "temperature_bme": record.get("temperature_bme", []),
                                    "humidity": record.get("humidity", []),
                                    "pressure": record.get("pressure", []),
                                    "cn2": record.get("cn2", 0.0),
                                    "timestamp": record.get("timestamp")
                                } for record in recent_records
                            ],
                            "count": len(recent_records),
                            "latest_only": True
                        }
                        await manager.broadcast(json.dumps(current_data_message))
                        logger.debug(f"Sent current data: {len(recent_records)} recent records")
                    
                    last_broadcast_time = current_time
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

@app.on_event("startup")
async def startup_event():
    """Initialize Arduino connection and start background polling"""
    global background_task
    
    logger.info("Starting Temperature Control System server...")
    
    # Connect to Arduino
    logger.info(f"Attempting to connect to Arduino on {arduino_comm.port}...")
    success = await arduino_comm.connect()
    if success:
        logger.info("Arduino connected successfully")
        
        # Get initial status and store it
        try:
            response = await arduino_comm.get_status()
            if response.status == "ok" and response.data:
                status_data = response.data.dict()
                status_data["device_status"] = "online"
                status_data["arduino_port"] = arduino_comm.port
                status_data["timestamp"] = datetime.now().isoformat()
                status_history.append(status_data.copy())
                logger.info("Initial Arduino status stored in history")
            else:
                logger.warning("Failed to get initial Arduino status")
        except Exception as e:
            logger.error(f"Error getting initial Arduino status: {e}")
        
        # Start background polling task
        background_task = asyncio.create_task(background_status_polling())
        
    else:
        logger.warning("Failed to connect to Arduino - server will run without Arduino")
        logger.info("Please check:")
        logger.info("1. Arduino is connected via USB")
        logger.info("2. Correct COM port is being used")
        logger.info("3. Arduino sketch is uploaded and running")
        logger.info("4. No other program is using the serial port")
        
        # Start background polling anyway (will show offline status)
        background_task = asyncio.create_task(background_status_polling())

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    await arduino_comm.disconnect()

# API Routes
@app.get("/")
async def root():
    """Serve the main web interface"""
    web_file = os.path.join(os.path.dirname(__file__), "..", "web", "index.html")
    if os.path.exists(web_file):
        return FileResponse(web_file)
    else:
        return {"message": "Temperature Control System API", "version": "1.0.0"}

@app.get("/beta")
async def beta():
    """Serve the beta visualization interface"""
    web_file = os.path.join(os.path.dirname(__file__), "..", "web", "beta.html")
    if os.path.exists(web_file):
        return FileResponse(web_file)
    else:
        return {"message": "Beta interface not found", "version": "1.0.0"}

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
        "arduino_connected": arduino_comm.is_connected,
        "polling_interval": polling_interval
    }

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
            logger.info(f"Attempting to reconnect Arduino to port: {request.port}")
        else:
            logger.info(f"Attempting to reconnect Arduino to port: {arduino_comm.port}")
        
        # Reconnect
        success = await arduino_comm.connect()
        
        if success:
            logger.info("Arduino successfully connected")
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
        logger.info("Force reconnecting Arduino...")
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
    
    try:
        # Send system status immediately for fast footer update
        current_status = {
            "type": "system_status",
            "device_status": "offline",
            "system_ready": False,
            "arduino_port": arduino_comm.port if arduino_comm.is_connected else None,
            "polling_interval": polling_interval,
            "timestamp": datetime.now().isoformat()
        }
        
        # If we have recent data, use that for system status
        if status_history:
            latest_data = status_history[-1]
            current_status.update({
                "device_status": latest_data.get("device_status", "unknown"),
                "system_ready": latest_data.get("system_ready", False),
                "arduino_port": latest_data.get("arduino_port"),
                "timestamp": latest_data.get("timestamp")
            })
        
        await websocket.send_text(json.dumps(current_status))
        logger.info("Sent system status to new WebSocket client")
        
        # Send historical data separately (this can take longer)
        if status_history:
            logger.info(f"Sending {len(status_history)} historical records to new WebSocket client")
            historical_data = {
                "type": "historical_data",
                "data": list(status_history),
                "count": len(status_history),
                "max_size": MAX_HISTORY_SIZE
            }
            await websocket.send_text(json.dumps(historical_data))
            logger.info("Sent historical data to new WebSocket client")
        else:
            logger.info("No historical data available for new WebSocket client")
        
        logger.info("WebSocket connection established, waiting for messages...")
        while True:
            # Keep connection alive and handle any incoming messages
            try:
                message = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                logger.debug(f"Received WebSocket message: {message}")
            except asyncio.TimeoutError:
                # Send a ping to keep connection alive
                await websocket.send_text('{"type":"ping"}')
                logger.debug("Sent ping to keep WebSocket alive")
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected normally")
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
