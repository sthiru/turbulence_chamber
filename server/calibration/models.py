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
    
    # Current state (for real-time status updates)
    current_fan_id: Optional[int] = None
    current_fan_speed: Optional[int] = None
    current_temperature: Optional[float] = None
    phase: Optional[str] = None
    phase_details: Optional[str] = None
    current_flow_rates: List[float] = []
    
    # Granular progress tracking (for accurate time estimation)
    total_speed_steps: int = 0  # Total number of speed levels across all fans
    current_speed_step: int = 0  # Current speed level being calibrated
    
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
        if self.start_time is None:
            return None

        if self.status == CalibrationStatus.COMPLETED:
            return 0.0

        elapsed = (datetime.now() - self.start_time).total_seconds()

        # Calculate initial estimate based on configuration
        # settling_time_ms + time for samples (assume 0.2s per sample)
        config = self.config if hasattr(self, 'config') else {}
        settling_time = config.get('settling_time_ms', 1000) / 1000.0  # Convert to seconds
        num_samples = config.get('num_samples', 3)
        sample_time = num_samples * 0.2  # ~0.2s per sample
        initial_estimate_per_step = settling_time + sample_time

        # Use granular speed step tracking if available for more accurate estimation
        # Start using actual data after just 3 steps to avoid jumps
        if self.total_speed_steps > 0 and self.current_speed_step >= 3:
            actual_avg_time_per_step = elapsed / self.current_speed_step
            remaining_speed_steps = self.total_speed_steps - self.current_speed_step

            # Use weighted average to smooth transition (70% actual, 30% estimate)
            # This prevents sudden jumps when switching to actual data
            if self.current_speed_step < 10:
                weight = 0.3 + (self.current_speed_step - 3) * 0.1  # Gradually increase weight
                weight = min(weight, 1.0)
                avg_time = (weight * actual_avg_time_per_step) + ((1 - weight) * initial_estimate_per_step)
            else:
                avg_time = actual_avg_time_per_step

            return avg_time * remaining_speed_steps
        # Use fan-level tracking if available (fallback)
        elif self.current_step > 0:
            avg_time_per_fan = elapsed / self.current_step
            remaining_fans = self.total_steps - self.current_step
            return avg_time_per_fan * remaining_fans

        # Use configuration-based estimate before any steps complete
        if self.total_speed_steps > 0:
            remaining_speed_steps = self.total_speed_steps - self.current_speed_step
            return remaining_speed_steps * initial_estimate_per_step

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
    ambient_temperature: Optional[float] = None  # °C
    ambient_pressure: Optional[float] = None  # hPa or mbar
    ambient_humidity: Optional[float] = None  # %
