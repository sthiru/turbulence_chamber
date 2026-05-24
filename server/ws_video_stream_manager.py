"""
Video streaming connection manager for camera video feeds
"""
import logging
from typing import Dict
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class VideoStreamManager:
    """Manages WebSocket connections for video streaming"""
    
    def __init__(self, camera):
        """
        Initialize video stream manager
        
        Args:
            camera: BaslerCamera instance for accessing camera
        """
        self.camera = camera
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, client_id: str):
        """Accept and store new video stream connection"""
        await websocket.accept()
        self.active_connections[client_id] = websocket
        logger.info(f"Video stream client connected: {client_id}. Total video connections: {len(self.active_connections)}")
        
        # Add client to camera streaming
        self.camera.add_streaming_client(client_id)

    def disconnect(self, client_id: str):
        """Remove video stream connection"""
        if client_id in self.active_connections:
            del self.active_connections[client_id]
            logger.info(f"Video stream client disconnected: {client_id}. Total video connections: {len(self.active_connections)}")
            
            # Remove client from camera streaming
            self.camera.remove_streaming_client(client_id)

    async def send_frame(self, client_id: str, frame_data: str):
        """Send video frame to specific client"""
        if client_id in self.active_connections:
            try:
                await self.active_connections[client_id].send_text(frame_data)
            except Exception as e:
                logger.warning(f"Failed to send video frame to client {client_id}: {e}")
                # Remove disconnected client
                self.disconnect(client_id)
