from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import json
import logging
from typing import List
import uvicorn
import os

from models import (
    TemperatureCommand, FanCommand, HotPlateCommand, 
    SystemStatus, ArduinoResponse, DeviceStatus
)
from arduino_comm import arduino_comm

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

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                # Connection closed, remove it
                self.active_connections.remove(connection)

manager = ConnectionManager()

# Global variables
current_status: SystemStatus = None
status_broadcast_task = None

@app.on_event("startup")
async def startup_event():
    """Initialize Arduino connection and start status monitoring"""
    # Connect to Arduino
    success = await arduino_comm.connect()
    if success:
        logger.info("Arduino connected successfully")
        # Start connection monitoring
        asyncio.create_task(arduino_comm.monitor_connection())
        # Start status broadcasting
        asyncio.create_task(broadcast_status())
    else:
        logger.warning("Failed to connect to Arduino")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    await arduino_comm.disconnect()

async def broadcast_status():
    """Broadcast system status to all WebSocket clients"""
    while True:
        try:
            # Get status from Arduino
            response = await arduino_comm.get_status()
            
            if response.status == "ok" and response.data:
                status_data = response.data.dict()
                status_data["device_status"] = "online"
                
                # Broadcast to all connected clients
                await manager.broadcast(json.dumps(status_data))
                
            else:
                # Send error status
                error_status = {
                    "device_status": "offline",
                    "error": response.msg if response.msg else "Unknown error"
                }
                await manager.broadcast(json.dumps(error_status))
                
        except Exception as e:
            logger.error(f"Error broadcasting status: {e}")
            error_status = {
                "device_status": "error",
                "error": str(e)
            }
            await manager.broadcast(json.dumps(error_status))
        
        await asyncio.sleep(2)  # Update every 2 seconds

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
async def toggle_hot_plate(plate_id: int, state: bool):
    """Toggle hot plate on/off"""
    if plate_id < 0 or plate_id > 1:
        raise HTTPException(status_code=400, detail="Invalid hot plate ID")
    
    try:
        response = await arduino_comm.toggle_hot_plate(plate_id, state)
        if response.status == "ok":
            return {"status": "success", "message": f"Hot plate {plate_id + 1} {'enabled' if state else 'disabled'}"}
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

@app.websocket("/ws/status")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time status updates"""
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # Keep connection alive
    except WebSocketDisconnect:
        manager.disconnect(websocket)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
