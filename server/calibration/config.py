# Calibration configuration for turbulence chamber
import os
from typing import List, Tuple
from dataclasses import dataclass

@dataclass
class CalibrationConfig:
    """Configuration for chamber calibration routine"""
    
    # Fan speed calibration ranges
    fan_speed_min: int = 0
    fan_speed_max: int = 255
    fan_speed_step: int = 25  # Step size for fan speed variation
    
    # Hot plate temperature ranges
    hotplate_temp_min: float = 25.0  # °C
    hotplate_temp_max: float = 80.0  # °C
    hotplate_temp_step: float = 5.0  # °C step size
    
    # Timing parameters
    stabilization_time: int = 60  # seconds to wait for temperature stabilization
    measurement_duration: int = 30  # seconds to record data at each step
    sampling_interval: float = 1.0  # seconds between measurements
    
    # Sensor selection for calibration
    calibration_sensors: List[int] = None  # Indices of DS18B20 sensors to use (None = all)
    
    # Calibration modes
    calibrate_fans: bool = True
    calibrate_hotplates: bool = True
    calibrate_combined: bool = False  # If True, calibrate fans and hotplates together
    run_pre_calibration: bool = True  # Run fan-to-windflow pre-calibration first
    
    # Pre-calibration (fan-to-windflow polynomial) settings
    pre_calibration_fan_steps: int = 20  # Number of fan speed steps for pre-calibration
    pre_calibration_polynomial_degree: int = 3  # Degree of polynomial to fit
    
    # Safety limits
    max_chamber_temp: float = 100.0  # Maximum allowed chamber temperature
    max_surface_temp: float = 120.0  # Maximum allowed hot plate surface temperature
    
    # Data storage
    calibration_data_folder: str = "calibration_data"
    
    def __post_init__(self):
        if self.calibration_sensors is None:
            self.calibration_sensors = list(range(12))  # All 12 DS18B20 sensors
    
    def get_calibration_data_folder(self) -> str:
        """Get absolute path to calibration data folder from workspace root"""
        workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(workspace_root, self.calibration_data_folder)
    
    def get_fan_speed_steps(self) -> List[int]:
        """Generate list of fan speed steps for calibration"""
        return list(range(self.fan_speed_min, self.fan_speed_max + 1, self.fan_speed_step))
    
    def get_hotplate_temp_steps(self) -> List[float]:
        """Generate list of hot plate temperature steps for calibration"""
        steps = []
        temp = self.hotplate_temp_min
        while temp <= self.hotplate_temp_max:
            steps.append(round(temp, 1))
            temp += self.hotplate_temp_step
        return steps
    
    def get_total_calibration_steps(self) -> int:
        """Calculate total number of calibration steps"""
        fan_steps = len(self.get_fan_speed_steps())
        hotplate_steps = len(self.get_hotplate_temp_steps())
        
        if self.calibrate_combined:
            return fan_steps * hotplate_steps
        elif self.calibrate_fans and self.calibrate_hotplates:
            return fan_steps + hotplate_steps
        elif self.calibrate_fans:
            return fan_steps
        elif self.calibrate_hotplates:
            return hotplate_steps
        else:
            return 0
    
    def get_estimated_duration(self) -> int:
        """Estimate total calibration duration in seconds"""
        steps = self.get_total_calibration_steps()
        return steps

# Helper function to get settings file path
def get_settings_file_path() -> str:
    """Get absolute path to settings file from workspace root"""
    workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(workspace_root, "arduino", "temperature_control", "settings.json")

# Default configuration instance
DEFAULT_CONFIG = CalibrationConfig()
