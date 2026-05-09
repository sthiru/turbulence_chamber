# -*- coding: utf-8 -*-
"""
Combined Calibration
Establishes 4D lookup table for hot plate temperature × fan speed → chamber temperature/Cn²
"""

import numpy as np
import logging
import json
import os
from typing import List, Tuple, Optional, Dict
from datetime import datetime
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

@dataclass
class CombinedCalibrationConfig:
    """Configuration for combined calibration"""
    temp_min: float = 80.0  # Minimum temperature in °C
    temp_max: float = 120.0  # Maximum temperature in °C
    temp_step: float = 2.0  # Temperature step in °C
    fan_speeds: List[int] = None  # Fan speeds to test [255, 191, 128, 64]
    recording_duration: int = 900  # Recording duration in seconds (15 minutes)
    sampling_interval: int = 10  # Sampling interval in seconds

    def __post_init__(self):
        if self.fan_speeds is None:
            self.fan_speeds = [255, 191, 128, 64]  # 100%, 75%, 50%, 25%

@dataclass
class CombinedDataPoint:
    """Single data point from combined calibration"""
    hotplate_temp: float
    fan_speed: int
    chamber_temp_avg: float
    cn2_value: float
    sensor_temps: Dict[str, float]  # sensor_1, sensor_3, sensor_5, sensor_7
    timestamp: float

@dataclass
class CombinedLookupTable:
    """4D lookup table in interpolation-friendly array format (Option C)"""
    hotplate_temps: List[float]
    fan_speeds: List[int]
    cn2_matrix: List[List[float]]  # rows: temps, cols: fan speeds
    chamber_temp_matrix: List[List[float]]
    sensor_temp_matrices: Dict[str, List[List[float]]]  # sensor_1, sensor_3, sensor_5, sensor_7
    metadata: Dict

@dataclass
class CombinedCalibrationResult:
    """Result of combined calibration"""
    calibration_id: str
    timestamp: datetime
    config: CombinedCalibrationConfig
    lookup_table: CombinedLookupTable
    ambient_temperature: Optional[float] = None
    ambient_pressure: Optional[float] = None
    ambient_humidity: Optional[float] = None

class CombinedCalibrator:
    """Calibrates combined hot plate and fan effects"""

    def __init__(self):
        """Initialize combined calibrator"""
        self.calibration_result: Optional[CombinedCalibrationResult] = None

    def build_lookup_table(self, data_points: List[CombinedDataPoint],
                          config: CombinedCalibrationConfig) -> CombinedLookupTable:
        """
        Build 4D lookup table from collected data points

        Args:
            data_points: List of all collected data points
            config: Calibration configuration

        Returns:
            CombinedLookupTable in interpolation-friendly array format
        """
        # Get unique temperature and fan speed values
        hotplate_temps = sorted(list(set(dp.hotplate_temp for dp in data_points)))
        fan_speeds = sorted(list(set(dp.fan_speed for dp in data_points)))

        # Initialize matrices
        cn2_matrix = [[0.0] * len(fan_speeds) for _ in range(len(hotplate_temps))]
        chamber_temp_matrix = [[0.0] * len(fan_speeds) for _ in range(len(hotplate_temps))]

        sensor_temp_matrices = {
            'sensor_1': [[0.0] * len(fan_speeds) for _ in range(len(hotplate_temps))],
            'sensor_3': [[0.0] * len(fan_speeds) for _ in range(len(hotplate_temps))],
            'sensor_5': [[0.0] * len(fan_speeds) for _ in range(len(hotplate_temps))],
            'sensor_7': [[0.0] * len(fan_speeds) for _ in range(len(hotplate_temps))]
        }

        # Group data points by hotplate temperature and fan speed
        data_grid: Dict[Tuple[float, int], List[CombinedDataPoint]] = {}
        for dp in data_points:
            key = (dp.hotplate_temp, dp.fan_speed)
            if key not in data_grid:
                data_grid[key] = []
            data_grid[key].append(dp)

        # Average values for each temperature-fan speed combination
        for temp_idx, temp in enumerate(hotplate_temps):
            for fan_idx, fan_speed in enumerate(fan_speeds):
                key = (temp, fan_speed)
                if key in data_grid:
                    points = data_grid[key]
                    # Average Cn² values (use last 30% of data points for steady state)
                    steady_state_start = int(len(points) * 0.7)
                    steady_state_points = points[steady_state_start:] if steady_state_start > 0 else points

                    avg_cn2 = np.mean([dp.cn2_value for dp in steady_state_points])
                    avg_chamber_temp = np.mean([dp.chamber_temp_avg for dp in steady_state_points])

                    cn2_matrix[temp_idx][fan_idx] = float(avg_cn2)
                    chamber_temp_matrix[temp_idx][fan_idx] = float(avg_chamber_temp)

                    # Average sensor temperatures
                    for sensor_name in ['sensor_1', 'sensor_3', 'sensor_5', 'sensor_7']:
                        avg_sensor_temp = np.mean([dp.sensor_temps.get(sensor_name, 0.0) for dp in steady_state_points])
                        sensor_temp_matrices[sensor_name][temp_idx][fan_idx] = float(avg_sensor_temp)

        return CombinedLookupTable(
            hotplate_temps=hotplate_temps,
            fan_speeds=fan_speeds,
            cn2_matrix=cn2_matrix,
            chamber_temp_matrix=chamber_temp_matrix,
            sensor_temp_matrices=sensor_temp_matrices,
            metadata={
                'calibration_type': 'combined',
                'interpolation_method': 'bilinear',
                'data_points_count': len(data_points)
            }
        )

    def interpolate_lookup_table(self, lookup_table: CombinedLookupTable,
                                 hotplate_temp: float, fan_speed: int) -> Dict:
        """
        Interpolate lookup table for given temperature and fan speed

        Args:
            lookup_table: The lookup table
            hotplate_temp: Target hot plate temperature
            fan_speed: Target fan speed

        Returns:
            Dictionary with interpolated values
        """
        temps = np.array(lookup_table.hotplate_temps)
        fans = np.array(lookup_table.fan_speeds)

        # Find indices for interpolation
        temp_idx = np.searchsorted(temps, hotplate_temp)
        fan_idx = np.searchsorted(fans, fan_speed)

        # Handle boundary cases
        temp_idx = max(0, min(temp_idx, len(temps) - 1))
        fan_idx = max(0, min(fan_idx, len(fans) - 1))

        # Simple nearest neighbor for now (can be upgraded to bilinear)
        result = {
            'hotplate_temp': hotplate_temp,
            'fan_speed': fan_speed,
            'cn2_value': lookup_table.cn2_matrix[temp_idx][fan_idx],
            'chamber_temp_avg': lookup_table.chamber_temp_matrix[temp_idx][fan_idx],
            'sensor_temps': {
                sensor: lookup_table.sensor_temp_matrices[sensor][temp_idx][fan_idx]
                for sensor in ['sensor_1', 'sensor_3', 'sensor_5', 'sensor_7']
            }
        }

        return result

    def export_calibration(self, filepath: str):
        """Export calibration results to JSON file"""
        if not self.calibration_result:
            raise ValueError("No calibration results to export")

        data = {
            "calibration_id": self.calibration_result.calibration_id,
            "timestamp": self.calibration_result.timestamp.isoformat(),
            "config": asdict(self.calibration_result.config),
            "lookup_table": asdict(self.calibration_result.lookup_table),
            "ambient_temperature": self.calibration_result.ambient_temperature,
            "ambient_pressure": self.calibration_result.ambient_pressure,
            "ambient_humidity": self.calibration_result.ambient_humidity
        }

        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)

        logger.info(f"Combined calibration exported to {filepath}")

    def import_calibration(self, filepath: str):
        """Import calibration results from JSON file"""
        with open(filepath, 'r') as f:
            data = json.load(f)

        config = CombinedCalibrationConfig(**data['config'])
        lookup_table = CombinedLookupTable(**data['lookup_table'])

        self.calibration_result = CombinedCalibrationResult(
            calibration_id=data['calibration_id'],
            timestamp=datetime.fromisoformat(data['timestamp']),
            config=config,
            lookup_table=lookup_table,
            ambient_temperature=data.get('ambient_temperature'),
            ambient_pressure=data.get('ambient_pressure'),
            ambient_humidity=data.get('ambient_humidity')
        )

        logger.info(f"Combined calibration imported from {filepath}")
