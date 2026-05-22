"""
CN² Thermal Calculation Module

This module contains functions for calculating the CN² (structure function parameter)
for turbulence based on temperature measurements from thermal sensors.

The calculation uses the formula:
CN² = (7.9*10^-5 * (P/T^2))^2 * (dt^2/r^(2/3))

Where:
- P = ambient pressure in hPa
- T = ambient temperature in Kelvin
- dt^2 = squared temperature difference between specific sensor pairs
- r = radial distance in meters (varies by sensor pair)

This module calculates CN² for 4 specific temperature sensor pairs:
1. T1 & T2 - r=0.5m
2. T3 & T4 - r=0.3m  
3. T6 & T7 - r=0.5m
4. T8 & T9 - r=0.3m
"""

import logging

logger = logging.getLogger(__name__)


def calculate_cn2(temperatures, bme_temperatures, bme_pressure):
    """
    Calculate CN² (structure function parameter) for turbulence using multiple temperature pairs
    
    Formula: (7.9*10^-5 * (P/T^2))^2 * (dt^2/r^(2/3))
    
    Calculates CN² for 4 different temperature pairs with different distances:
    1. t1 & t2 - r=0.5
    2. t3 & t4 - r=0.3
    3. t6 & t7 - r=0.5
    4. t8 & t9 - r=0.3
    
    Args:
        temperatures: List of temperature readings from DS18B20 sensors (indexed 0-11)
        bme_temperatures: List of temperature readings from BME280 sensors
        bme_pressure: List of pressure readings from BME280 sensors in hPa
    
    Returns:
        List of CN² values [cn2_1, cn2_2, cn2_3, cn2_4] corresponding to the 4 temperature pairs
    """
    try:
        # Get the minimum temperature from BME280 sensors (ambient temperature)
        if len(bme_temperatures) > 0:
            ambient_temp = min(bme_temperatures)
            ambient_temp = ambient_temp if ambient_temp > 0.0 else max(bme_temperatures)
        else:
            ambient_temp = 25.0  # Default to room temperature

        # Get the minimum pressure from BME sensor
        if len(bme_pressure) > 0:
            pressure = min(bme_pressure)
            pressure = pressure if pressure > 0.0 else max(bme_pressure)
        else:
            pressure = 1010.0  # Default to standard pressure
        
        if ambient_temp <= 0:
            logger.warning(f"Invalid ambient temperature for CN²: {ambient_temp}")
            ambient_temp = 25.0  # Default to room temperature
        
        if pressure <= 0:
            logger.warning(f"Invalid pressure for CN²: {pressure}")
            pressure = 1010.0  # Default to standard pressure

        ambient_temp_kelvin = ambient_temp + 273.15
        
        # Define temperature pairs with their corresponding distances
        temp_pairs = [
            (0, 1, 0.5),  # t1 & t2 - r=0.5
            (2, 3, 0.3),  # t3 & t4 - r=0.3
            (5, 6, 0.5),  # t6 & t7 - r=0.5
            (7, 8, 0.3)   # t8 & t9 - r=0.3
        ]
        
        cn2_results = []
        
        for idx1, idx2, r in temp_pairs:
            # Check if we have enough temperature data
            if not temperatures or len(temperatures) <= max(idx1, idx2):
                cn2_results.append(0.0)
                continue
            
            temp1 = temperatures[idx1]
            temp2 = temperatures[idx2]
            
            # Filter out error values
            if temp1 <= 0 or temp2 <= 0:
                cn2_results.append(0.0)
                continue
            
            # Calculate dt^2 (difference between temperatures)
            dt_squared = (temp2 - temp1) ** 2
            
            # Calculate CN² using the formula
            cn2 = (7.9e-5 * (pressure / (ambient_temp_kelvin ** 2)))**2 * (dt_squared / (r ** (2/3)))
            
            cn2_results.append(cn2)
            
            logger.debug(f"CN² calculation pair {len(cn2_results)}: T{idx1+1}={temp1:.2f}°C, T{idx2+1}={temp2:.2f}°C, r={r}m, dt²={dt_squared:.2f}, CN²={cn2:.2e}")
        
        return cn2_results
        
    except Exception as e:
        logger.error(f"Error calculating CN²: {e}")
        return [0.0, 0.0, 0.0, 0.0]
