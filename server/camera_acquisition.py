# -*- coding: utf-8 -*-
"""
Camera acquisition module for GigE Basler camera using Pylon SDK
Created for turbulence controller system
"""

import os
import time
import logging
from datetime import datetime
from typing import Optional, Tuple
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
        self.exposure_time = 10000  # microseconds
        self.gain = 1.0
        self.image_format = "Mono8"
        
        # Ensure camera images folder exists
        os.makedirs(self.camera_images_folder, exist_ok=True)
        
        # Camera info
        self.camera_info = {}
        
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
            
            # Configure camera
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
            if not self.is_initialized:
                if not self.initialize_camera():
                    return False
                    
            if not PYLON_AVAILABLE:
                self.is_connected = True
                logger.info("Camera connected (simulation mode)")
                return True
                
            if self.camera and not self.camera.IsOpen():
                self.camera.Open()
                
            # Start grabbing
            self.camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
            
            self.is_connected = True
            logger.info("Camera connected and ready for acquisition")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect camera: {e}")
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
            timestamp = datetime.now()
            image = self.capture_image()
            
            if image is not None:
                return self.save_image(image, timestamp)
            else:
                return None
                
        except Exception as e:
            logger.error(f"Error in capture_and_save: {e}")
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

def initialize_camera_system(camera_images_folder: str = "camera_images") -> bool:
    """Initialize the camera system"""
    camera = get_camera_instance(camera_images_folder)
    return camera.initialize_camera()

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
