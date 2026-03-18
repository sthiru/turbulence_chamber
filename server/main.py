import sys
import os

# Add current directory to Python path for module imports
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Body
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio
import json
import logging
from typing import List
import uvicorn

from models import (
    TemperatureCommand, FanCommand, HotPlateCommand, 
    SystemStatus, ArduinoResponse, DeviceStatus, ManualControlCommand
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

# Global variables
current_status: SystemStatus = None
status_broadcast_task = None
polling_interval = 10.0  # Default 10 seconds

@app.on_event("startup")
async def startup_event():
    """Initialize Arduino connection and start status monitoring"""
    logger.info("Starting Temperature Control System server...")
    
    # Connect to Arduino
    logger.info(f"Attempting to connect to Arduino on {arduino_comm.port}...")
    success = await arduino_comm.connect()
    if success:
        logger.info("Arduino connected successfully")
        # Start connection monitoring
        asyncio.create_task(arduino_comm.monitor_connection())
        # Start status broadcasting
        asyncio.create_task(broadcast_status())
    else:
        logger.warning("Failed to connect to Arduino - server will run without Arduino")
        logger.info("Please check:")
        logger.info("1. Arduino is connected via USB")
        logger.info("2. Correct COM port is being used")
        logger.info("3. Arduino sketch is uploaded and running")
        logger.info("4. No other program is using the serial port")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    await arduino_comm.disconnect()

async def broadcast_status():
    """Broadcast system status to all WebSocket clients"""
    logger.info("Starting status broadcasting task...")
    
    while True:
        try:
            logger.debug(f"Polling Arduino... Active connections: {len(manager.active_connections)}")
            
            # Get status from Arduino
            response = await arduino_comm.get_status()
            
            if response.status == "ok" and response.data:
                status_data = response.data.dict()
                status_data["device_status"] = "online"
                status_data["arduino_port"] = arduino_comm.port if arduino_comm.is_connected else None
                
                # Broadcast to all connected clients
                if manager.active_connections:
                    await manager.broadcast(json.dumps(status_data))
                    logger.info(f"Broadcasted status to {len(manager.active_connections)} clients: {status_data.get('device_status', 'unknown')}")
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
                    "system_ready": False
                }
                if manager.active_connections:
                    await manager.broadcast(json.dumps(error_status))
                    logger.warning(f"Broadcasted error status: {error_status['error']}")
                else:
                    logger.debug("No WebSocket clients connected, skipping error broadcast")
                
        except Exception as e:
            logger.error(f"Error broadcasting status: {e}")
            error_status = {
                "device_status": "error",
                "error": str(e),
                "arduino_port": arduino_comm.port if arduino_comm.is_connected else None,
                "temperatures": [0.0] * 5,  # 5 sensors
                "target_temperatures": [80.0, 80.0],
                "fan_speeds": [0, 0, 0, 0],
                "hot_plate_states": [False, False],
                "system_ready": False
            }
            if manager.active_connections:
                await manager.broadcast(json.dumps(error_status))
        
        logger.debug(f"Sleeping for {polling_interval} seconds...")
        await asyncio.sleep(polling_interval)  # Use configurable polling interval

# API Routes
@app.get("/")
async def root():
    """Serve the main web interface"""
    web_file = os.path.join(os.path.dirname(__file__), "..", "web", "index.html")
    if os.path.exists(web_file):
        return FileResponse(web_file)
    else:
        return {"message": "Temperature Control System API", "version": "1.0.0"}

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

@app.post("/api/manual/hotplate/{plate_id}")
async def set_manual_hotplate_control(plate_id: int, manual: bool):
    """Set manual control for hot plate"""
    if plate_id < 0 or plate_id > 1:
        raise HTTPException(status_code=400, detail="Invalid hot plate ID")
    
    try:
        response = await arduino_comm.set_manual_hotplate_control(plate_id, manual)
        if response.status == "ok":
            return {"status": "success", "message": f"Hot plate {plate_id + 1} manual control {'enabled' if manual else 'disabled'}"}
        else:
            raise HTTPException(status_code=400, detail=response.msg)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/manual/fan/{fan_id}")
async def set_manual_fan_control(fan_id: int, manual: bool):
    """Set manual control for fan"""
    if fan_id < 0 or fan_id > 3:
        raise HTTPException(status_code=400, detail="Invalid fan ID")
    
    try:
        response = await arduino_comm.set_manual_fan_control(fan_id, manual)
        if response.status == "ok":
            return {"status": "success", "message": f"Fan {fan_id + 1} manual control {'enabled' if manual else 'disabled'}"}
        else:
            raise HTTPException(status_code=400, detail=response.msg)
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

@app.websocket("/ws/status")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time status updates"""
    logger.info("New WebSocket connection attempt...")
    await manager.connect(websocket)
    try:
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
