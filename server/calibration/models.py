# Calibration data models

from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime
from enum import Enum
from typing import Tuple

class CalibrationStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"

class CalibrationStepType(str, Enum):
    FAN_CALIBRATION = "fan_calibration"
    HOTPLATE_CALIBRATION = "hotplate_calibration"
    COMBINED_CALIBRATION = "combined_calibration"
    FAN_WINDFLOW_CALIBRATION = "fan_windflow_calibration"

class CalibrationDataPoint(BaseModel):
    """Single data point recorded during calibration"""
    timestamp: datetime
    fan_speeds: List[int]
    hot_plate_states: List[bool]
    target_temperatures: List[float]
    temperatures: List[float]
    temperature_bmp: List[float]
    pressure: List[float]
    temperature_dht: List[float]
    humidity: List[float]
    flow_rates: List[float]
    cn2: Optional[float] = None
    
class CalibrationStep(BaseModel):
    """Single calibration step configuration and results"""
    step_type: CalibrationStepType
    step_number: int
    fan_speed: Optional[int] = None
    hotplate_id: Optional[int] = None
    target_temperature: Optional[float] = None
    hotplate_state: Optional[bool] = None
    
    # Timing
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    stabilization_time: Optional[float] = None  # Time to reach stable temperature
    
    # Results
    data_points: List[CalibrationDataPoint] = []
    avg_temperatures: List[float] = []
    temperature_std: List[float] = []
    avg_flow_rates: List[float] = []
    avg_cn2: Optional[float] = None
    
    # Status
    status: CalibrationStatus = CalibrationStatus.IDLE
    error_message: Optional[str] = None

class CalibrationSession(BaseModel):
    """Complete calibration session"""
    session_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    status: CalibrationStatus = CalibrationStatus.IDLE
    
    # Configuration
    total_steps: int
    current_step: int = 0
    config: Dict = {}
    
    # Results
    steps: List[CalibrationStep] = []
    lookup_table: Optional[Dict] = None
    
    # Metadata
    notes: Optional[str] = None
    error_message: Optional[str] = None
    
    def get_progress(self) -> float:
        """Get calibration progress as percentage"""
        if self.total_steps == 0:
            return 0.0
        return (self.current_step / self.total_steps) * 100
    
    def get_estimated_remaining_time(self) -> Optional[float]:
        """Estimate remaining time in seconds"""
        if self.start_time is None or self.current_step == 0:
            return None
        
        if self.status == CalibrationStatus.COMPLETED:
            return 0.0
        
        elapsed = (datetime.now() - self.start_time).total_seconds()
        if self.current_step > 0:
            avg_time_per_step = elapsed / self.current_step
            remaining_steps = self.total_steps - self.current_step
            return avg_time_per_step * remaining_steps
        return None

class CalibrationRequest(BaseModel):
    """Request to start calibration"""
    calibrate_fans: bool = True
    calibrate_hotplates: bool = True
    calibrate_combined: bool = False
    run_pre_calibration: bool = True
    fan_speed_min: Optional[int] = None
    fan_speed_max: Optional[int] = None
    fan_speed_step: Optional[int] = None
    hotplate_temp_min: Optional[float] = None
    hotplate_temp_max: Optional[float] = None
    hotplate_temp_step: Optional[float] = None
    stabilization_time: Optional[int] = None
    measurement_duration: Optional[int] = None
    notes: Optional[str] = None

class CalibrationControl(BaseModel):
    """Control command for running calibration"""
    action: str = Field(..., description="Action: start, pause, resume, stop")

class FanWindflowPolynomial(BaseModel):
    """Polynomial coefficients for fan-to-windflow sensor relationship"""
    fan_id: int
    windflow_sensor_id: int
    coefficients: List[float]  # Polynomial coefficients [a0, a1, a2, ...]
    degree: int
    r_squared: float  # Goodness of fit
    data_points: List[Tuple[int, float]]  # (fan_speed, flow_rate) pairs

class WindflowCalibrationResult(BaseModel):
    """Result of fan-to-windflow pre-calibration"""
    calibration_id: str
    timestamp: datetime
    polynomials: List[FanWindflowPolynomial]
