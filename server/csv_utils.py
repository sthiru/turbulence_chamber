"""
CSV utility functions for calibration data management
"""
import csv
import os
from typing import Dict, List
import logging

logger = logging.getLogger(__name__)


def init_csv_file(session_folder: str, calibration_type: str) -> str:
    """Initialize CSV file for data capture"""
    csv_filename = f"{calibration_type}_data.csv"
    csv_filepath = os.path.join(session_folder, csv_filename)
    
    try:
        # Create CSV file with headers based on calibration type
        headers = [
            'timestamp', 'session_id',
            'temp_sensor_1', 'temp_sensor_2', 'temp_sensor_3', 'temp_sensor_4', 'temp_sensor_5','temp_sensor_6', 'temp_sensor_7', 'temp_sensor_8', 'temp_sensor_9', 'temp_sensor_10','temp_sensor_11','temp_sensor_12',
            'temp_hotplate1', 'temp_hotplate2',
            'bmpTemperature_internal', 'bmpTemperature_external',
            'bmpPressure_internal', 'bmpPressure_external',
            'dhtTemperature_internal', 'dhtTemperature_external',
            'dhtHumidity_internal', 'dhtHumidity_external',
            'target_temp_1', 'target_temp_2',
            'fan_speed_1', 'fan_speed_2', 'fan_speed_3', 'fan_speed_4',
            'hot_plate_1', 'hot_plate_2',
            'flow_rate_1', 'flow_rate_2', 'flow_rate_3', 'flow_rate_4',
            'cn2_row1_500', 'cn2_row1_300', 'cn2_row2_500', 'cn2_row2_300',
            'cn2_optical',
            'image_filename'
        ]
        
        with open(csv_filepath, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(headers)
        
        logger.info(f"CSV file initialized: {csv_filepath}")
        return csv_filepath
        
    except Exception as e:
        logger.error(f"Failed to initialize CSV file: {e}")
        return None


def append_to_csv(csv_filepath: str, data: Dict):
    """Append data row to CSV file"""
    try:
        with open(csv_filepath, 'a', newline='') as csvfile:
            writer = csv.writer(csvfile)
            
            # Prepare row data based on available keys
            row = []
            for key in get_csv_keys(csv_filepath):
                value = data.get(key, '')
                # Convert numpy types to Python native types
                if hasattr(value, 'item'):
                    value = value.item()
                row.append(value)
            
            writer.writerow(row)
            
    except Exception as e:
        logger.error(f"Failed to append to CSV file: {e}")


def get_csv_keys(csv_filepath: str) -> List[str]:
    """Get CSV column keys from file header"""
    try:
        with open(csv_filepath, 'r') as csvfile:
            reader = csv.reader(csvfile)
            headers = next(reader)
            return headers
    except Exception as e:
        logger.error(f"Failed to read CSV headers: {e}")
        return []
