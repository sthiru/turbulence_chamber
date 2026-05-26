"""
State Manager for turbulence controller system
Encapsulates global state to avoid global variables and provide thread-safe access
"""
import asyncio
import threading
from datetime import datetime
from typing import Optional, Dict, List, Any
from collections import deque


class StateManager:
    """
    Manages application state in a thread-safe manner
    Replaces global variables with encapsulated state
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize state manager (singleton)"""
        if hasattr(self, '_initialized'):
            return
        
        # Background task state
        self._background_task: Optional[asyncio.Task] = None
        self._video_streaming_task: Optional[asyncio.Task] = None
        self._last_broadcast_time: float = 0
        self._polling_interval: float = 1.0
        
        # Data capture state
        self._data_capture_active: bool = False
        self._current_capture_session: Optional[Dict[str, Any]] = None
        self._captured_data_points: List[Dict[str, Any]] = []
        self._centroid_history: List[Dict[str, Any]] = []
        
        # Status history
        self._max_history_size: int = 1000
        self._status_history: deque = deque(maxlen=self._max_history_size)
        
        # Status update queue
        self._status_update_queue: Optional[asyncio.Queue] = None
        
        # Async lock for thread-safe operations
        self._async_lock = asyncio.Lock()
        
        self._initialized = True
    
    # Background task state methods
    @property
    def background_task(self) -> Optional[asyncio.Task]:
        return self._background_task
    
    @background_task.setter
    def background_task(self, task: Optional[asyncio.Task]):
        self._background_task = task
    
    @property
    def video_streaming_task(self) -> Optional[asyncio.Task]:
        return self._video_streaming_task
    
    @video_streaming_task.setter
    def video_streaming_task(self, task: Optional[asyncio.Task]):
        self._video_streaming_task = task
    
    @property
    def last_broadcast_time(self) -> float:
        return self._last_broadcast_time
    
    @last_broadcast_time.setter
    def last_broadcast_time(self, value: float):
        self._last_broadcast_time = value
    
    @property
    def polling_interval(self) -> float:
        return self._polling_interval
    
    @polling_interval.setter
    def polling_interval(self, value: float):
        self._polling_interval = value
    
    # Data capture state methods
    @property
    def data_capture_active(self) -> bool:
        return self._data_capture_active
    
    @data_capture_active.setter
    def data_capture_active(self, value: bool):
        self._data_capture_active = value
    
    @property
    def current_capture_session(self) -> Optional[Dict[str, Any]]:
        return self._current_capture_session
    
    @current_capture_session.setter
    def current_capture_session(self, session: Optional[Dict[str, Any]]):
        self._current_capture_session = session
    
    @property
    def captured_data_points(self) -> List[Dict[str, Any]]:
        return self._captured_data_points
    
    def add_captured_data_point(self, data_point: Dict[str, Any]):
        """Add a data point to captured data"""
        self._captured_data_points.append(data_point)
    
    def clear_captured_data_points(self):
        """Clear all captured data points"""
        self._captured_data_points = []
    
    @property
    def centroid_history(self) -> List[Dict[str, Any]]:
        return self._centroid_history
    
    def add_centroid_to_history(self, centroid_data: Dict[str, Any]):
        """Add centroid data to history"""
        self._centroid_history.append(centroid_data)
    
    def clear_centroid_history(self):
        """Clear centroid history"""
        self._centroid_history = []
    
    def get_centroid_history_length(self) -> int:
        """Get length of centroid history"""
        return len(self._centroid_history)
    
    # Status history methods
    @property
    def status_history(self) -> deque:
        return self._status_history
    
    def add_to_status_history(self, status_data: Dict[str, Any]):
        """Add status data to history"""
        self._status_history.append(status_data.copy())
    
    def get_status_history_length(self) -> int:
        """Get length of status history"""
        return len(self._status_history)
    
    @property
    def max_history_size(self) -> int:
        return self._max_history_size
    
    @max_history_size.setter
    def max_history_size(self, value: int):
        self._max_history_size = value
        self._status_history = deque(maxlen=value)
    
    # Status update queue methods
    @property
    def status_update_queue(self) -> Optional[asyncio.Queue]:
        return self._status_update_queue
    
    @status_update_queue.setter
    def status_update_queue(self, queue: Optional[asyncio.Queue]):
        self._status_update_queue = queue
    
    # Async lock access
    async def get_lock(self):
        """Get the async lock for thread-safe operations"""
        return self._async_lock
    
    # Reset method for testing
    def reset(self):
        """Reset all state (for testing)"""
        self._background_task = None
        self._video_streaming_task = None
        self._last_broadcast_time = 0
        self._polling_interval = 1.0
        self._data_capture_active = False
        self._current_capture_session = None
        self._captured_data_points = []
        self._centroid_history = []
        self._status_history.clear()
        self._status_update_queue = None


# Global state manager instance
state_manager = StateManager()
