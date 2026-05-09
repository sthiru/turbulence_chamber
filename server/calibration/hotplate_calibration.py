# -*- coding: utf-8 -*-
"""
Hot Plate Calibration
Establishes exponential saturation relationship between hot plate temperature and chamber temperature
"""

import numpy as np
import logging
import json
import os
from typing import List, Tuple, Optional, Dict
from datetime import datetime
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)

class HotplateStatus(str, Enum):
    """Hot plate calibration status"""
    IDLE = "idle"
    HEATING = "heating"
    STABILIZING = "stabilizing"
    RECORDING = "recording"
    SATURATED = "saturated"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass
class HotplateCalibrationConfig:
    """Configuration for hot plate calibration"""
    temp_min: float = 80.0  # Minimum temperature in °C
    temp_max: float = 120.0  # Maximum temperature in °C
    temp_step: float = 2.0  # Temperature step in °C
    fan_speed: int = 255  # Fan speed (PWM)
    recording_duration: int = 900  # Recording duration in seconds (15 minutes)
    sampling_interval: int = 10  # Sampling interval in seconds
    saturation_tolerance: float = 0.2  # Saturation tolerance in °C
    saturation_duration: int = 120  # Time to maintain saturation in seconds (2 minutes)
    sensor_1_distance: float = 15.0  # Distance in cm for sensor 1
    sensor_3_distance: float = 25.0  # Distance in cm for sensor 3
    sensor_5_distance: float = 15.0  # Distance in cm for sensor 5
    sensor_7_distance: float = 25.0  # Distance in cm for sensor 7

@dataclass
class SaturationCurve:
    """Exponential saturation curve parameters"""
    hotplate_id: int
    target_temp: float
    asymptote: float  # Steady-state temperature
    time_constant: float  # Time constant (tau)
    r_squared: float  # Goodness of fit
    saturation_time: float  # Time to reach saturation (seconds)
    data_points: List[Tuple[float, float]]  # (time, temperature) pairs

@dataclass
class HotplateCalibrationResult:
    """Result of hot plate calibration"""
    calibration_id: str
    timestamp: datetime
    config: HotplateCalibrationConfig
    hotplate_curves: List[SaturationCurve]
    ambient_temperature: Optional[float] = None
    ambient_pressure: Optional[float] = None
    ambient_humidity: Optional[float] = None

class HotplateCalibrator:
    """Calibrates hot plate to chamber temperature relationships"""

    def __init__(self):
        """Initialize hot plate calibrator"""
        self.calibration_result: Optional[HotplateCalibrationResult] = None

    def detect_saturation(self, temperatures: List[float], timestamps: List[float],
                         tolerance: float = 0.2, duration: float = 120.0) -> Tuple[bool, float]:
        """
        Detect if temperature has reached saturation

        Args:
            temperatures: List of temperature readings
            timestamps: List of corresponding timestamps (seconds from start)
            tolerance: Saturation tolerance in °C
            duration: Time to maintain saturation in seconds

        Returns:
            Tuple of (is_saturated, saturation_time)
        """
        if len(temperatures) < 2:
            return False, 0.0

        # Convert to numpy arrays
        temps = np.array(temperatures)
        times = np.array(timestamps)

        # Calculate moving average with window size for smoothing
        window_size = max(3, len(temps) // 20)  # Adaptive window size
        if len(temps) >= window_size:
            temps_smooth = np.convolve(temps, np.ones(window_size)/window_size, mode='valid')
            times_smooth = times[window_size-1:]
        else:
            temps_smooth = temps
            times_smooth = times

        # Check for saturation: temperature stays within tolerance for specified duration
        for i in range(len(temps_smooth) - 1):
            window_end = i + 1
            while window_end < len(temps_smooth):
                if times_smooth[window_end] - times_smooth[i] > duration:
                    break
                window_end += 1

            if times_smooth[window_end - 1] - times_smooth[i] >= duration:
                window_temps = temps_smooth[i:window_end]
                if np.max(window_temps) - np.min(window_temps) <= tolerance:
                    saturation_time = times_smooth[i]
                    return True, saturation_time

        return False, 0.0

    def fit_exponential_saturation(self, times: List[float], temperatures: List[float]) -> Tuple[float, float, float]:
        """
        Fit exponential saturation curve: T(t) = T_asymptote * (1 - exp(-t/tau))

        Args:
            times: List of time points (seconds)
            temperatures: List of temperature readings

        Returns:
            Tuple of (asymptote, time_constant, r_squared)
        """
        if len(times) < 5:
            raise ValueError("Need at least 5 data points for exponential fitting")

        t = np.array(times, dtype=float)
        T = np.array(temperatures, dtype=float)

        # Initial guess: asymptote is max temperature, tau is 10% of total time
        T_asym_guess = np.max(T)
        tau_guess = t[-1] * 0.1

        # Use curve fitting
        def saturation_model(t, T_asym, tau):
            return T_asym * (1 - np.exp(-t / tau))

        try:
            from scipy.optimize import curve_fit
            popt, pcov = curve_fit(saturation_model, t, T, p0=[T_asym_guess, tau_guess],
                                   bounds=([np.min(T), 1.0], [np.max(T) * 1.2, t[-1]]))
            T_asym, tau = popt

            # Calculate R-squared
            T_pred = saturation_model(t, T_asym, tau)
            ss_res = np.sum((T - T_pred) ** 2)
            ss_tot = np.sum((T - np.mean(T)) ** 2)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0

            return float(T_asym), float(tau), float(r_squared)
        except ImportError:
            logger.warning("scipy not available, using simple approximation")
            # Simple approximation: asymptote = max temp, tau = time to reach 63% of max
            T_asym = np.max(T)
            target = T_asym * 0.63
            tau_idx = np.where(T >= target)[0]
            if len(tau_idx) > 0:
                tau = t[tau_idx[0]]
            else:
                tau = t[-1] * 0.5

            # Simple R-squared calculation
            T_pred = T_asym * (1 - np.exp(-t / tau))
            ss_res = np.sum((T - T_pred) ** 2)
            ss_tot = np.sum((T - np.mean(T)) ** 2)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0

            return float(T_asym), float(tau), float(r_squared)

    def calibrate_hotplate(self, hotplate_id: int, target_temp: float,
                          temperature_data: List[Tuple[float, float, List[float]]],
                          config: HotplateCalibrationConfig) -> SaturationCurve:
        """
        Calibrate a single hot plate at a single temperature

        Args:
            hotplate_id: Hot plate identifier (0 or 1)
            target_temp: Target hot plate temperature
            temperature_data: List of (timestamp, hotplate_temp, sensor_temps) tuples
            config: Calibration configuration

        Returns:
            SaturationCurve with fitted parameters
        """
        # Extract sensor data based on hotplate_id
        if hotplate_id == 0:
            sensor_indices = [0, 2]  # Sensors 1 and 3 (0-indexed)
        else:
            sensor_indices = [4, 6]  # Sensors 5 and 7 (0-indexed)

        # Average the relevant sensor temperatures
        sensor_temps_avg = []
        timestamps = []

        for timestamp, hotplate_temp, all_sensor_temps in temperature_data:
            relevant_temps = [all_sensor_temps[i] for i in sensor_indices if i < len(all_sensor_temps)]
            if relevant_temps:
                avg_temp = np.mean(relevant_temps)
                sensor_temps_avg.append(avg_temp)
                timestamps.append(timestamp)

        if len(timestamps) < 5:
            raise ValueError(f"Insufficient data points for hotplate {hotplate_id} at {target_temp}°C")

        # Normalize timestamps to start from 0
        start_time = timestamps[0]
        times_norm = [t - start_time for t in timestamps]

        # Detect saturation
        is_saturated, saturation_time = self.detect_saturation(
            sensor_temps_avg, times_norm,
            tolerance=config.saturation_tolerance,
            duration=config.saturation_duration
        )

        # Fit exponential curve
        asymptote, time_constant, r_squared = self.fit_exponential_saturation(times_norm, sensor_temps_avg)

        # Create data points list
        data_points = list(zip(times_norm, sensor_temps_avg))

        return SaturationCurve(
            hotplate_id=hotplate_id,
            target_temp=target_temp,
            asymptote=asymptote,
            time_constant=time_constant,
            r_squared=r_squared,
            saturation_time=saturation_time if is_saturated else 0.0,
            data_points=data_points
        )

    def export_calibration(self, filepath: str):
        """Export calibration results to JSON file"""
        if not self.calibration_result:
            raise ValueError("No calibration results to export")

        data = {
            "calibration_id": self.calibration_result.calibration_id,
            "timestamp": self.calibration_result.timestamp.isoformat(),
            "config": asdict(self.calibration_result.config),
            "curves": [asdict(curve) for curve in self.calibration_result.hotplate_curves],
            "ambient_temperature": self.calibration_result.ambient_temperature,
            "ambient_pressure": self.calibration_result.ambient_pressure,
            "ambient_humidity": self.calibration_result.ambient_humidity
        }

        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)

        logger.info(f"Hot plate calibration exported to {filepath}")

    def import_calibration(self, filepath: str):
        """Import calibration results from JSON file"""
        with open(filepath, 'r') as f:
            data = json.load(f)

        config = HotplateCalibrationConfig(**data['config'])
        curves = [SaturationCurve(**curve) for curve in data['curves']]

        self.calibration_result = HotplateCalibrationResult(
            calibration_id=data['calibration_id'],
            timestamp=datetime.fromisoformat(data['timestamp']),
            config=config,
            hotplate_curves=curves,
            ambient_temperature=data.get('ambient_temperature'),
            ambient_pressure=data.get('ambient_pressure'),
            ambient_humidity=data.get('ambient_humidity')
        )

        logger.info(f"Hot plate calibration imported from {filepath}")
