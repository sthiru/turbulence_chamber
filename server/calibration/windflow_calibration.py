# -*- coding: utf-8 -*-
"""
Fan-to-Windflow Sensor Polynomial Calibration
Establishes polynomial relationship between fan PWM and windflow sensor readings
"""

import numpy as np
import logging
from typing import List, Tuple, Optional
from datetime import datetime
from .models import FanWindflowPolynomial, WindflowCalibrationResult

logger = logging.getLogger(__name__)

class WindflowCalibrator:
    """Calibrates fan-to-windflow sensor relationships"""
    
    def __init__(self, polynomial_degree: int = 3):
        """
        Initialize windflow calibrator
        
        Args:
            polynomial_degree: Degree of polynomial to fit (default: 3)
        """
        self.polynomial_degree = polynomial_degree
        self.calibration_results: Optional[WindflowCalibrationResult] = None
    
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
        
        # Fit polynomial
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
    
    def predict_flow_rate(self, fan_speed: int, polynomial: FanWindflowPolynomial) -> float:
        """
        Predict flow rate for a given fan speed using fitted polynomial
        
        Args:
            fan_speed: Fan PWM value
            polynomial: Fitted polynomial coefficients
            
        Returns:
            Predicted flow rate
        """
        coefficients = np.array(polynomial.coefficients)
        flow_rate = np.polyval(coefficients, fan_speed)
        return float(flow_rate)
    
    def calibrate_all_fans(self, calibration_data: List[Tuple[int, List[Tuple[int, float]]]]) -> WindflowCalibrationResult:
        """
        Calibrate all fan-to-windflow sensor pairs
        
        Args:
            calibration_data: List of (fan_id, [(fan_speed, flow_rate), ...]) tuples
            
        Returns:
            WindflowCalibrationResult with all fitted polynomials
        """
        polynomials = []
        
        for fan_id, data_points in calibration_data:
            windflow_sensor_id = fan_id  # Assume 1:1 mapping (Fan N → Windflow Sensor N)
            
            fan_speeds = [dp[0] for dp in data_points]
            flow_rates = [dp[1] for dp in data_points]
            
            try:
                polynomial = self.fit_polynomial(fan_speeds, flow_rates, fan_id, windflow_sensor_id)
                polynomials.append(polynomial)
                logger.info(f"Fan {fan_id} → Windflow {windflow_sensor_id}: R² = {polynomial.r_squared:.4f}")
            except Exception as e:
                logger.error(f"Failed to calibrate Fan {fan_id}: {e}")
        
        calibration_result = WindflowCalibrationResult(
            calibration_id=f"windflow_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            timestamp=datetime.now(),
            polynomials=polynomials
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
        import json
        
        if not self.calibration_results:
            raise ValueError("No calibration results to export")
        
        data = self.calibration_results.dict()
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Polynomials exported to {filepath}")
    
    def import_polynomials(self, filepath: str):
        """Import polynomials from JSON file"""
        import json
        
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        self.calibration_results = WindflowCalibrationResult(**data)
        logger.info(f"Polynomials imported from {filepath}")
