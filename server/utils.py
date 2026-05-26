"""
Server utility functions for configuration and path management
"""
import os
import json
import logging
from datetime import datetime
import cv2
from typing import Optional, Tuple
import numpy as np
from constants import (
    CAMERA_IMAGES_FOLDER,
    DATA_CAPTURE_FOLDER_DATE_FORMAT,
    DATA_CAPTURE_FOLDER_TIME_FORMAT,
    IMAGE_THRESHOLD_DEFAULT,
    IMAGE_EPSILON
)

logger = logging.getLogger(__name__)


def get_workspace_root() -> str:
    """Get workspace root directory (parent of server folder)"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load_configuration() -> dict:
    """Load configuration from configuration.json"""
    workspace_root = get_workspace_root()
    config_file = os.path.join(workspace_root, "server", "configuration.json")
    
    try:
        with open(config_file, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        return {}


def set_configuration(config: dict):
    """Save configuration to configuration.json"""
    workspace_root = get_workspace_root()
    config_file = os.path.join(workspace_root, "server", "configuration.json")
    
    try:
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        logger.error(f"Failed to save configuration: {e}")
        raise


def get_configuration(key: str, default=None):
    """Get a specific configuration value from configuration.json"""
    config = load_configuration()
    return config.get(key, default)


def get_calibration_data_folder() -> str:
    """Get absolute path to calibration data folder from workspace root"""
    workspace_root = get_workspace_root()
    return os.path.join(workspace_root, "calibration_data")

def create_capture_folder() -> str:
    """Create a date-based folder for camera images"""
    workspace_root = get_workspace_root()
    now = datetime.now()
    date_folder = now.strftime(DATA_CAPTURE_FOLDER_DATE_FORMAT)
    time_folder = now.strftime(DATA_CAPTURE_FOLDER_TIME_FORMAT)
    
    # Create folder structure: camera_images/DD_MMM_YYYY/HH_MM
    base_folder = os.path.join(workspace_root, CAMERA_IMAGES_FOLDER, date_folder, time_folder)
    
    try:
        os.makedirs(base_folder, exist_ok=True)
        logger.info(f"Created capture folder: {base_folder}")
        return base_folder
    except Exception as e:
        logger.error(f"Failed to create capture folder: {e}")
        return os.path.join(workspace_root, CAMERA_IMAGES_FOLDER)  # Fallback to base folder


def calculate_beam_centroid(image_path: str, threshold_value: int = IMAGE_THRESHOLD_DEFAULT) -> Optional[Tuple[float, float]]:
    """
    Calculate beam centroid from a single image
    
    Args:
        image_path: Path to the image file
        threshold_value: Image threshold for noise removal (default: 20)
        
    Returns:
        Tuple of (centroid_x, centroid_y) or (0,0) if calculation fails
    """
    try:
        # Load image in grayscale
        img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            logger.warning(f"Could not load image: {image_path}")
            return (0, 0)
            
        # Apply thresholding to remove noise
        #_, thresh = cv2.threshold(img, threshold_value, 255, cv2.THRESH_TOZERO)
        thresh = cv2.adaptiveThreshold(
        (img * 255).astype(np.uint8),
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        11, 2)

        mask = thresh / 255.0
        beam = img * mask
        h, w = beam.shape
        y, x = np.indices((h, w))

        total_intensity = np.sum(beam) + IMAGE_EPSILON

        # --- Centroid ---
        cx = np.sum(x * beam) / total_intensity
        cy = np.sum(y * beam) / total_intensity
        
        # Calculate moments for centroid
        # M = cv2.moments(thresh)
        
        # if M["m00"] == 0:
        #     logger.warning(f"No valid pixels found in image: {image_path}")
        #     return (0, 0)
            
        # # Calculate centroid coordinates
        # cx = M["m10"] / M["m00"]
        # cy = M["m01"] / M["m00"]
        
        return (int(cx), int(cy))
        
    except Exception as e:
        logger.error(f"Error calculating centroid for {image_path}: {e}")
        return (0, 0)
