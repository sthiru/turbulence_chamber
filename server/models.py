from pydantic import BaseModel
from typing import List, Optional
from enum import Enum

class DeviceStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    ERROR = "error"

class TemperatureData(BaseModel):
    sensor_id: int
    temperature: float
    timestamp: float

class FanData(BaseModel):
    fan_id: int
    speed: int  # 0-255
    state: bool

class HotPlateData(BaseModel):
    plate_id: int
    target_temperature: float
    current_temperature: float
    state: bool

class CameraStatus(BaseModel):
    connected: bool
    initialized: bool
    is_streaming: bool = False
    error: Optional[str] = None

class SystemStatus(BaseModel):
    temperatures: List[float]
    temp_hotplate1: Optional[float] = None
    temp_hotplate2: Optional[float] = None
    bmpTemperature_internal: Optional[float] = None
    bmpTemperature_external: Optional[float] = None
    bmpPressure_internal: Optional[float] = None
    bmpPressure_external: Optional[float] = None
    dhtTemperature_internal: Optional[float] = None
    dhtTemperature_external: Optional[float] = None
    dhtHumidity_internal: Optional[float] = None
    dhtHumidity_external: Optional[float] = None
    target_temperatures: List[float]
    fan_speeds: List[int]
    hot_plate_states: List[bool]
    flow_rates: List[float]
    camera_status: Optional[CameraStatus] = None
    system_ready: bool
    device_status: Optional[DeviceStatus] = None

class TemperatureCommand(BaseModel):
    sensor: int
    target: float

class FanCommand(BaseModel):
    fan: int
    speed: int

class HotPlateCommand(BaseModel):
    plate: int
    state: bool

class ArduinoCommand(BaseModel):
    cmd: str
    sensor: Optional[int] = None
    target: Optional[float] = None
    fan: Optional[int] = None
    speed: Optional[int] = None
    plate: Optional[int] = None
    state: Optional[bool] = None

class ArduinoResponse(BaseModel):
    status: str
    data: Optional[SystemStatus] = None
    msg: Optional[str] = None

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
    calibration_type: Optional[str] = None

# Pydantic model for data point with image
class DataPointWithImage(BaseModel):
    timestamp: str
    temperatures: List[float]
    temperature_bmp: List[float]
    temperature_dht: List[float]
    target_temperatures: List[float]
    fan_speeds: List[int]
    hot_plate_states: List[bool]  
    pressure: List[float]
    humidity: List[float]
    cn2: Optional[float] = None
    cn2_optical: Optional[float] = None
    image_filename: Optional[str] = None
