# -*- coding: utf-8 -*-
"""
Fan-to-Windflow Sensor Calibration
Establishes linear relationship between fan PWM and windflow sensor readings
Each windflow sensor is placed 40cm directly in front of its corresponding fan
"""

import numpy as np
import logging
import json
import os
from typing import List, Tuple, Optional, Dict
from datetime import datetime
from .models import FanWindflowPolynomial, WindflowCalibrationResult

logger = logging.getLogger(__name__)

class WindflowCalibrator:
    """Calibrates fan-to-windflow sensor relationships"""

    def __init__(self, polynomial_degree: int = 1):
        """
        Initialize windflow calibrator

        Args:
            polynomial_degree: Degree of polynomial to fit (default: 1 for linear)
        """
        self.polynomial_degree = polynomial_degree
        self.calibration_results: Optional[WindflowCalibrationResult] = None
        self.sensor_distance_cm = 40.0  # Distance from fan to windflow sensor
    
    def fit_polynomial(self, fan_speeds: List[int], flow_rates: List[float], 
                       fan_id: int, windflow_sensor_id: int) -> FanWindflowPolynomial:
        """
        Fit polynomial to fan speed vs flow rate data
        
        Args:
            fan_speeds: List of fan PWM values
            flow_rates: List of corresponding flow rate readings
            fan_id: Fan identifier (0-3)
            windflow_sensor_id: Windflow sensor identifier (0-3)
            
        Returns:
            FanWindflowPolynomial with fitted coefficients
        """
        if len(fan_speeds) != len(flow_rates):
            raise ValueError("fan_speeds and flow_rates must have same length")
        
        if len(fan_speeds) < self.polynomial_degree + 1:
            raise ValueError(f"Need at least {self.polynomial_degree + 1} data points for degree {self.polynomial_degree} polynomial")
        
        # Convert to numpy arrays
        x = np.array(fan_speeds, dtype=float)
        y = np.array(flow_rates, dtype=float)
        
        # Fit polynomial: flow_rate = f(fan_speed)
        coefficients = np.polyfit(x, y, self.polynomial_degree)
        coefficients_list = coefficients.tolist()
        
        # Calculate R-squared (goodness of fit)
        y_pred = np.polyval(coefficients, x)
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0
        
        # Create data points list
        data_points = list(zip(fan_speeds, flow_rates))
        
        return FanWindflowPolynomial(
            fan_id=fan_id,
            windflow_sensor_id=windflow_sensor_id,
            coefficients=coefficients_list,
            degree=self.polynomial_degree,
            r_squared=r_squared,
            data_points=data_points
        )
    
    def predict_flow_rate(self, fan_speed: float, polynomial: FanWindflowPolynomial) -> float:
        """
        Predict flow rate for a given fan speed using fitted polynomial
        
        Args:
            fan_speed: Fan PWM value (0-255)
            polynomial: Fitted polynomial coefficients
            
        Returns:
            Predicted flow rate
        """
        coefficients = np.array(polynomial.coefficients)
        flow_rate = np.polyval(coefficients, fan_speed)
        return float(max(0, flow_rate))  # Ensure non-negative
    
    def predict_fan_speed(self, target_flow_rate: float, polynomial: FanWindflowPolynomial) -> float:
        """
        Predict fan speed for a given target flow rate (inverse mapping)
        
        Args:
            target_flow_rate: Desired flow rate
            polynomial: Fitted polynomial coefficients
            
        Returns:
            Required fan PWM value (0-255)
        """
        coefficients = np.array(polynomial.coefficients)
        
        # Create polynomial equation: flow_rate - target = 0
        poly_coeffs = coefficients.copy()
        poly_coeffs[-1] -= target_flow_rate  # Subtract target from constant term
        
        # Find roots
        roots = np.roots(poly_coeffs)
        
        # Filter for real, positive roots in valid PWM range [0, 255]
        valid_roots = [r.real for r in roots if abs(r.imag) < 1e-6 and 0 <= r.real <= 255]
        
        if valid_roots:
            return float(min(valid_roots))  # Return lowest valid root
        else:
            # If no valid root, return closest boundary
            return 255.0 if target_flow_rate > self.predict_flow_rate(255, polynomial) else 0.0
    
    def calibrate_all_fans(self, calibration_data: List[Tuple[int, List[Tuple[int, float]]]], 
                           ambient_temperature: Optional[float] = None,
                           ambient_pressure: Optional[float] = None,
                           ambient_humidity: Optional[float] = None) -> WindflowCalibrationResult:
        """
        Calibrate all fan-to-windflow sensor pairs
        
        Args:
            calibration_data: List of (fan_id, [(fan_speed, flow_rate), ...]) tuples
            ambient_temperature: Ambient temperature in °C
            ambient_pressure: Ambient pressure in hPa or mbar
            ambient_humidity: Ambient humidity in %
            
        Returns:
            WindflowCalibrationResult with all fitted polynomials
        """
        polynomials = []
        
        for fan_id, data_points in calibration_data:
            windflow_sensor_id = fan_id  # 1:1 mapping (Fan N → Windflow Sensor N)
            
            fan_speeds = [dp[0] for dp in data_points]
            flow_rates = [dp[1] for dp in data_points]
            
            try:
                polynomial = self.fit_polynomial(fan_speeds, flow_rates, fan_id, windflow_sensor_id)
                polynomials.append(polynomial)
                logger.info(f"Fan {fan_id} → Windflow {windflow_sensor_id} @ {self.sensor_distance_cm}cm: R² = {polynomial.r_squared:.4f}")
            except Exception as e:
                logger.error(f"Failed to calibrate Fan {fan_id}: {e}")
        
        calibration_result = WindflowCalibrationResult(
            calibration_id=f"windflow_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            timestamp=datetime.now(),
            polynomials=polynomials,
            ambient_temperature=ambient_temperature,
            ambient_pressure=ambient_pressure,
            ambient_humidity=ambient_humidity
        )
        
        self.calibration_results = calibration_result
        return calibration_result
    
    def get_polynomial_for_fan(self, fan_id: int) -> Optional[FanWindflowPolynomial]:
        """Get polynomial for specific fan"""
        if not self.calibration_results:
            return None
        
        for poly in self.calibration_results.polynomials:
            if poly.fan_id == fan_id:
                return poly
        return None
    
    def export_polynomials(self, filepath: str):
        """Export polynomials to JSON file"""
        if not self.calibration_results:
            raise ValueError("No calibration results to export")
        
        data = self.calibration_results.model_dump(mode='json')
        data['sensor_distance_cm'] = self.sensor_distance_cm
        
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Windflow polynomials exported to {filepath}")
    
    def import_polynomials(self, filepath: str):
        """Import polynomials from JSON file"""
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        # Extract sensor distance if available
        if 'sensor_distance_cm' in data:
            self.sensor_distance_cm = data.pop('sensor_distance_cm')
        
        self.calibration_results = WindflowCalibrationResult(**data)
        logger.info(f"Windflow polynomials imported from {filepath}")
