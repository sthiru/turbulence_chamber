# -*- coding: utf-8 -*-
"""
Camera acquisition module for GigE Basler camera using Pylon SDK
Created for turbulence controller system
"""

import os
import time
import logging
import re
from datetime import datetime
from typing import Optional, Tuple, Dict, Any
import cv2
import numpy as np

# Try to import pylon, provide fallback if not available
try:
    from pypylon import pylon
    PYLON_AVAILABLE = True
except ImportError:
    PYLON_AVAILABLE = False
    logging.warning("Pylon SDK not available. Camera acquisition will be simulated.")

logger = logging.getLogger(__name__)

class BaslerCamera:
    """GigE Basler camera acquisition using Pylon SDK"""
    
    def __init__(self, camera_images_folder: str = "camera_images"):
        """
        Initialize camera acquisition
        
        Args:
            camera_images_folder: Directory to save captured images
        """
        self.camera_images_folder = camera_images_folder
        self.camera = None
        self.is_initialized = False
        self.is_connected = False
        
        # Camera settings

        self.camera_settings = {}  # Store loaded pfs settings
        
        # Ensure camera images folder exists
        os.makedirs(self.camera_images_folder, exist_ok=True)
        
        # Camera info
        self.camera_info = {}
        
    def load_pfs_settings(self, pfs_file_path: str) -> bool:
        """
        Load camera settings from a PFS (Pylon Feature Set) file
        
        Args:
            pfs_file_path: Path to the .pfs file
            
        Returns:
            bool: True if settings loaded successfully, False otherwise
        """
        try:
            if not os.path.exists(pfs_file_path):
                logger.error(f"PFS file not found: {pfs_file_path}")
                return False
                
            if not PYLON_AVAILABLE:
                logger.warning("Pylon SDK not available - cannot load PFS file")
                return False
                
            logger.info(f"Loading camera settings from PFS file: {pfs_file_path}")
            
            # Load and parse PFS file
            self.camera_settings = self._parse_pfs_file(pfs_file_path)
            
            # Update camera settings with loaded values
            if 'ExposureTime' in self.camera_settings:
                self.exposure_time = float(self.camera_settings['ExposureTime'])
                logger.info(f"Loaded exposure time: {self.exposure_time} μs")
                
            if 'Gain' in self.camera_settings:
                self.gain = float(self.camera_settings['Gain'])
                logger.info(f"Loaded gain: {self.gain}")
                
            if 'PixelFormat' in self.camera_settings:
                self.image_format = self.camera_settings['PixelFormat']
                logger.info(f"Loaded pixel format: {self.image_format}")
                
            # Log all loaded settings
            logger.info(f"Successfully loaded {len(self.camera_settings)} camera settings from PFS file")
            for key, value in list(self.camera_settings.items())[:10]:  # Show first 10 settings
                logger.debug(f"  {key}: {value}")
                
            return True
            
        except Exception as e:
            logger.error(f"Failed to load PFS file {pfs_file_path}: {e}")
            return False
    
    def _parse_pfs_file(self, pfs_file_path: str) -> Dict[str, Any]:
        """
        Parse PFS file and extract camera settings
        
        Args:
            pfs_file_path: Path to the PFS file
            
        Returns:
            Dict containing camera parameter names and values
        """
        settings = {}
        
        try:
            with open(pfs_file_path, 'r') as f:
                lines = f.readlines()
                
            # Parse each line for parameter=value pairs
            for line in lines:
                line = line.strip()
                
                # Skip comments and empty lines
                if line.startswith('#') or not line or '\t' not in line:
                    continue
                    
                # Split parameter and value
                parts = line.split('\t')
                if len(parts) >= 2:
                    param_name = parts[0].strip()
                    param_value = parts[1].strip()
                    
                    # Convert value to appropriate type
                    if param_value.replace('.', '').isdigit():
                        # Numeric value
                        if '.' in param_value:
                            settings[param_name] = float(param_value)
                        else:
                            settings[param_name] = int(param_value)
                    else:
                        # String value
                        settings[param_name] = param_value
                        
        except Exception as e:
            logger.warning(f"Error parsing PFS file: {e}")
            
        return settings
    
    def apply_pfs_settings_to_camera(self) -> bool:
        """
        Apply loaded PFS settings to the camera
        
        Returns:
            bool: True if settings applied successfully, False otherwise
        """
        try:
            if not self.camera or not self.camera.IsOpen():
                logger.error("Camera not available for applying settings")
                return False
                
            if not self.camera_settings:
                logger.warning("No PFS settings loaded to apply")
                return False
                
            logger.info("Applying PFS settings to camera...")
            
            # Key settings to apply with proper mapping
            key_settings = {
                'ExposureTime': 'ExposureTime',
                'Gain': 'Gain',
                'PixelFormat': 'PixelFormat',
                'Width': 'Width',
                'Height': 'Height',
                'OffsetX': 'OffsetX',
                'OffsetY': 'OffsetY',
                'AcquisitionFrameRate': 'AcquisitionFrameRate',
                'GainAuto': 'GainAuto',
                'ExposureAuto': 'ExposureAuto',
                'TriggerMode': 'TriggerMode',
                'TriggerSource': 'TriggerSource'
            }
            
            # Apply key settings
            for pfs_param, camera_param in key_settings.items():
                if pfs_param in self.camera_settings:
                    value = self.camera_settings[pfs_param]
                    try:
                        if hasattr(self.camera, camera_param):
                            param = getattr(self.camera, camera_param)
                            if hasattr(param, 'SetValue'):
                                param.SetValue(value)
                                logger.info(f"Applied {camera_param}: {value}")
                            elif hasattr(param, 'FromString'):
                                param.FromString(value)
                                logger.info(f"Applied {camera_param}: {value}")
                    except Exception as e:
                        logger.warning(f"Could not set {camera_param} to {value}: {e}")
            
            # Apply stream parameters
            self._apply_stream_parameters()
            
            # Apply white balance settings
            self._apply_white_balance_settings()
            
            logger.info("PFS settings applied successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to apply PFS settings: {e}")
            return False
    
    def _apply_stream_parameters(self):
        """Apply stream-related parameters"""
        try:
            # Stream packet size
            if 'DeviceStreamChannelPacketSize' in self.camera_settings:
                packet_size = self.camera_settings['DeviceStreamChannelPacketSize']
                if hasattr(self.camera, 'DeviceStreamChannelPacketSize'):
                    self.camera.DeviceStreamChannelPacketSize.SetValue(packet_size)
                    logger.info(f"Applied packet size: {packet_size}")
            
            # Stream parameters
            stream_params = [
                'DeviceStreamChannelBufferCount',
                'DeviceStreamChannelTimeout',
                'DeviceStreamChannelThroughputLimit'
            ]
            
            for param in stream_params:
                if param in self.camera_settings and hasattr(self.camera, param):
                    value = self.camera_settings[param]
                    try:
                        getattr(self.camera, param).SetValue(value)
                        logger.debug(f"Applied {param}: {value}")
                    except Exception as e:
                        logger.debug(f"Could not set {param}: {e}")
                        
        except Exception as e:
            logger.warning(f"Error applying stream parameters: {e}")
    
    def _apply_white_balance_settings(self):
        """Apply white balance settings"""
        try:
            # White balance auto
            if 'BalanceWhiteAuto' in self.camera_settings:
                value = self.camera_settings['BalanceWhiteAuto']
                if hasattr(self.camera, 'BalanceWhiteAuto'):
                    self.camera.BalanceWhiteAuto.SetValue(value)
                    logger.info(f"Applied white balance auto: {value}")
            
            # White balance ratios
            wb_params = ['BalanceRatioRaw', 'BalanceRatioSelector']
            for param in wb_params:
                if param in self.camera_settings and hasattr(self.camera, param):
                    value = self.camera_settings[param]
                    try:
                        getattr(self.camera, param).SetValue(value)
                        logger.debug(f"Applied {param}: {value}")
                    except Exception as e:
                        logger.debug(f"Could not set {param}: {e}")
                        
        except Exception as e:
            logger.warning(f"Error applying white balance settings: {e}")
        
    def initialize_camera(self) -> bool:
        """Initialize the camera"""
        try:
            if not PYLON_AVAILABLE:
                logger.warning("Pylon SDK not available - using simulation mode")
                self.is_initialized = True
                return True
                
            # Create an instant camera object
            tlFactory = pylon.TlFactory.GetInstance()
            devices = tlFactory.EnumerateDevices()
            
            if len(devices) == 0:
                logger.error("No Basler cameras found")
                return False
                
            # Create camera object
            self.camera = pylon.InstantCamera(tlFactory.CreateDevice(devices[0]))
            
            # Open camera
            self.camera.Open()
            
            # Apply PFS settings if loaded, otherwise use default settings
            if self.camera_settings:
                logger.info("Applying loaded PFS settings to camera...")
                if not self.apply_pfs_settings_to_camera():
                    logger.warning("Failed to apply PFS settings, using defaults")
                    # Fall back to default settings
                    self.camera.ExposureTime.SetValue(self.exposure_time)
                    self.camera.Gain.SetValue(self.gain)
            else:
                # Use default settings
                logger.info("Using default camera settings")
                self.camera.ExposureTime.SetValue(self.exposure_time)
                self.camera.Gain.SetValue(self.gain)
            
            # Get camera info
            # Get camera info with compatibility handling
            device_info = self.camera.GetDeviceInfo()
            self.camera_info = {
                "model": device_info.GetModelName(),
                "serial": device_info.GetSerialNumber(),
                "vendor": device_info.GetVendorName(),
                "firmware": getattr(device_info, 'GetFirmwareVersion', lambda: 'Unknown')()
            }
            
            self.is_initialized = True
            logger.info(f"Camera initialized: {self.camera_info['model']} (S/N: {self.camera_info['serial']})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize camera: {e}")
            return False
    
    def connect_camera(self) -> bool:
        """Connect to the camera"""
        try:
            logger.info(f"Attempting to connect camera - Initialized: {self.is_initialized}")
            
            if not self.is_initialized:
                logger.info("Camera not initialized, attempting initialization...")
                if not self.initialize_camera():
                    logger.error("Failed to initialize camera during connection attempt")
                    return False
                    
            if not PYLON_AVAILABLE:
                self.is_connected = True
                logger.info("Camera connected (simulation mode)")
                return True
                
            logger.info(f"Camera object exists: {self.camera is not None}")
            logger.info(f"Camera is open: {self.camera.IsOpen() if self.camera else 'N/A'}")
            
            if self.camera and not self.camera.IsOpen():
                logger.info("Opening camera...")
                self.camera.Open()
                logger.info("Camera opened successfully")
                
            # Start grabbing
            logger.info("Starting image grabbing...")
            self.camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
            logger.info("Image grabbing started successfully")
            
            self.is_connected = True
            logger.info("Camera connected and ready for acquisition")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect camera: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def disconnect_camera(self):
        """Disconnect from the camera"""
        try:
            if self.camera and self.camera.IsOpen():
                if self.camera.IsGrabbing():
                    self.camera.StopGrabbing()
                self.camera.Close()
                
            self.is_connected = False
            logger.info("Camera disconnected")
            
        except Exception as e:
            logger.error(f"Error disconnecting camera: {e}")
    
    def capture_image(self) -> Optional[np.ndarray]:
        """
        Capture a single image from the camera
        
        Returns:
            numpy.ndarray: Captured image in OpenCV format, or None if failed
        """
        try:
            if not self.is_connected:
                if not self.connect_camera():
                    return None
                    
            if not PYLON_AVAILABLE:
                # Simulate image capture for testing
                logger.debug("Simulating camera capture")
                # Create a random grayscale image
                simulated_image = np.random.randint(0, 255, (480, 640), dtype=np.uint8)
                # Add some structure to make it look more realistic
                cv2.circle(simulated_image, (320, 240), 50, 200, -1)
                cv2.rectangle(simulated_image, (200, 150), (440, 330), 150, -1)
                return simulated_image
                
            # Grab image
            grabResult = self.camera.RetrieveResult(5000, pylon.TimeoutHandling_ThrowException)
            
            if grabResult.GrabSucceeded():
                # Convert to OpenCV format
                image = grabResult.GetArray()
                
                # Convert to uint8 if needed
                if image.dtype != np.uint8:
                    image = image.astype(np.uint8)
                
                # Ensure image is 2D (grayscale)
                if len(image.shape) == 3:
                    image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                    
                grabResult.Release()
                logger.debug(f"Captured image: {image.shape}")
                return image
            else:
                logger.error(f"Failed to grab image: {grabResult.ErrorCode()} {grabResult.ErrorDescription()}")
                grabResult.Release()
                return None
                
        except Exception as e:
            logger.error(f"Error capturing image: {e}")
            return None
    
    def save_image(self, image: np.ndarray, timestamp: Optional[datetime] = None) -> Optional[str]:
        """
        Save captured image to file
        
        Args:
            image: Image to save (numpy array)
            timestamp: Timestamp for filename (defaults to current time)
            
        Returns:
            str: Filename of saved image, or None if failed
        """
        try:
            if timestamp is None:
                timestamp = datetime.now()
                
            # Generate filename with timestamp
            filename = f"camera_{timestamp.strftime('%Y%m%d_%H%M%S_%f')[:-3]}.png"
            filepath = os.path.join(self.camera_images_folder, filename)
            
            # Save image
            success = cv2.imwrite(filepath, image)
            
            if success:
                logger.info(f"Image saved: {filename}")
                return filename
            else:
                logger.error(f"Failed to save image: {filepath}")
                return None
                
        except Exception as e:
            logger.error(f"Error saving image: {e}")
            return None
    
    def capture_and_save(self) -> Optional[str]:
        """
        Capture and save an image in one operation
        
        Returns:
            str: Filename of saved image, or None if failed
        """
        try:
            logger.info(f"Attempting to capture image - Initialized: {self.is_initialized}, Connected: {self.is_connected}")
            timestamp = datetime.now()
            image = self.capture_image()
            
            if image is not None:
                filename = self.save_image(image, timestamp)
                logger.info(f"Image captured and saved: {filename}")
                return filename
            else:
                logger.warning("Failed to capture image - capture_image returned None")
                return None
                
        except Exception as e:
            logger.error(f"Error in capture_and_save: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_camera_status(self) -> dict:
        """Get current camera status"""
        status = {
            "initialized": self.is_initialized,
            "connected": self.is_connected,
            "available": PYLON_AVAILABLE,
            "camera_info": self.camera_info,
            "image_folder": self.camera_images_folder
        }
        
        # Add camera-specific status if connected
        if self.is_connected and self.camera and PYLON_AVAILABLE:
            try:
                status.update({
                    "exposure_time": self.camera.ExposureTime.GetValue(),
                    "gain": self.camera.Gain.GetValue(),
                    "temperature": self.camera.DeviceTemperature.GetValue() if hasattr(self.camera, 'DeviceTemperature') else None
                })
            except Exception as e:
                logger.warning(f"Could not read camera parameters: {e}")
                
        return status
    
    def cleanup(self):
        """Cleanup camera resources"""
        try:
            self.disconnect_camera()
            if self.camera:
                self.camera.Close()
                self.camera = None
            self.is_initialized = False
            logger.info("Camera cleanup completed")
            
        except Exception as e:
            logger.error(f"Error during camera cleanup: {e}")

# Global camera instance
camera_instance = None

def get_camera_instance(camera_images_folder: str = "camera_images") -> BaslerCamera:
    """Get or create global camera instance"""
    global camera_instance
    if camera_instance is None:
        camera_instance = BaslerCamera(camera_images_folder)
    return camera_instance

def initialize_camera_system(camera_images_folder: str = "camera_images", pfs_file_path: Optional[str] = None) -> bool:
    """Initialize the camera system with optional PFS settings
    
    Args:
        camera_images_folder: Directory to save captured images
        pfs_file_path: Optional path to PFS file for camera settings
        
    Returns:
        bool: True if initialization successful, False otherwise
    """
    camera = get_camera_instance(camera_images_folder)
    
    # Load PFS settings if provided
    if pfs_file_path:
        logger.info(f"Initializing camera system with PFS file: {pfs_file_path}")
        if not camera.load_pfs_settings(pfs_file_path):
            logger.warning("Failed to load PFS settings, proceeding with defaults")
    
    return camera.initialize_camera()

def load_camera_pfs_settings(pfs_file_path: str, camera_images_folder: str = "camera_images") -> bool:
    """Load PFS settings for camera
    
    Args:
        pfs_file_path: Path to the PFS file
        camera_images_folder: Directory to save captured images
        
    Returns:
        bool: True if settings loaded successfully, False otherwise
    """
    camera = get_camera_instance(camera_images_folder)
    return camera.load_pfs_settings(pfs_file_path)

def capture_camera_image(camera_images_folder: str = "camera_images") -> Optional[str]:
    """Capture and save an image"""
    camera = get_camera_instance(camera_images_folder)
    return camera.capture_and_save()

def get_camera_status(camera_images_folder: str = "camera_images") -> dict:
    """Get camera system status"""
    camera = get_camera_instance(camera_images_folder)
    return camera.get_camera_status()

def cleanup_camera_system():
    """Cleanup camera system"""
    global camera_instance
    if camera_instance:
        camera_instance.cleanup()
        camera_instance = None
