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

class SystemStatus(BaseModel):
    temperatures: List[float]
    target_temperatures: List[float]
    fan_speeds: List[int]
    hot_plate_states: List[bool]
    system_ready: bool
    device_status: DeviceStatus

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
