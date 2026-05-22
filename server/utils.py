"""
Server utility functions for configuration and path management
"""
import os
import json
import logging
import datetime

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
    date_folder = now.strftime("%d_%b_%Y")  # e.g., "03_Apr_2026"
    time_folder = now.strftime("%H_%M")     # e.g., "14_30"
    
    # Create folder structure: camera_images/DD_MMM_YYYY/HH_MM
    base_folder = os.path.join(workspace_root, "camera_images", date_folder, time_folder)
    
    try:
        os.makedirs(base_folder, exist_ok=True)
        logger.info(f"Created capture folder: {base_folder}")
        return base_folder
    except Exception as e:
        logger.error(f"Failed to create capture folder: {e}")
        return os.path.join(workspace_root, "camera_images")  # Fallback to base folder

