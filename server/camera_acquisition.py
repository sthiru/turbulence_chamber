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
from typing import Optional, Tuple, Dict, Any, Iterator, Generator
import cv2
import numpy as np
import threading
import queue
import base64
from io import BytesIO
from PIL import Image

# Try to import pylon, provide fallback if not available
try:
    from pypylon import pylon
    PYLON_AVAILABLE = True
    # Debug: Print Pylon version info
    try:
        print(f"Pylon version: {pylon.pylon.Version}")
        print(f"Pylon build: {pylon.pylon.Build}")
    except:
        print("Could not get Pylon version info")
except ImportError:
    PYLON_AVAILABLE = False
    print("Pylon SDK not available. Camera acquisition will be simulated.")

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
        self.camera_settings = {}  # Store loaded pfs settings
        
        # Video streaming variables
        self.is_streaming = False
        self.streaming_thread = None
        self.frame_queue = queue.Queue(maxsize=10)  # Buffer for video frames
        self.streaming_clients = []  # List of connected streaming clients
        
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
            
            # Debug: Print transport layer factory info
            logger.debug("Available transport layers:")
            for tl in tlFactory.EnumerateTls():
                tl_name = tl.GetFriendlyName() if tl.IsFriendlyNameAvailable() else "Unknown"
                tl_type = tl.GetTLType() if tl.IsTLTypeAvailable() else "Unknown"
                logger.debug(f"  - {tl_name}: {tl_type}")
            
            # Enumerate all devices with detailed info
            devices = tlFactory.EnumerateDevices()
            logger.info(f"Found {len(devices)} Basler devices")
            
            if len(devices) == 0:
                # Try alternative enumeration methods
                logger.warning("No devices found with standard enumeration, trying alternative methods...")
                
                # Try to get device info from transport layers
                for tl in tlFactory.EnumerateTls():
                    try:
                        tl_devices = tl.EnumerateDevices()
                        tl_name = tl.GetFriendlyName() if tl.IsFriendlyNameAvailable() else "Unknown"
                        logger.info(f"Transport layer {tl_name} has {len(tl_devices)} devices")
                        for device in tl_devices:
                            logger.info(f"  Device: {device.GetModelName()} ({device.GetSerialNumber()})")
                    except Exception as e:
                        tl_name = tl.GetFriendlyName() if tl.IsFriendlyNameAvailable() else "Unknown"
                        logger.debug(f"Could not enumerate devices for TL {tl_name}: {e}")
                
                # Try to force GigE transport layer
                try:
                    gige_tl = tlFactory.CreateTl(pylon.TLTypeGigE)
                    if gige_tl:
                        logger.info("GigE transport layer found")
                        gige_devices = gige_tl.EnumerateDevices()
                        logger.info(f"GigE devices: {len(gige_devices)}")
                        for device in gige_devices:
                            logger.info(f"  GigE Device: {device.GetModelName()} ({device.GetSerialNumber()})")
                except Exception as e:
                    logger.debug(f"GigE transport layer not available: {e}")
                
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
                
            # Check if camera object is valid
            if not self.camera or not hasattr(self.camera, 'RetrieveResult'):
                logger.error("Camera object is not valid for image capture")
                return None
                
            # Grab image
            try:
                grabResult = self.camera.RetrieveResult(5000, pylon.TimeoutHandling_ThrowException)
            except Exception as e:
                logger.error(f"Error calling RetrieveResult: {e}")
                # Fall back to simulation mode
                logger.debug("Falling back to simulation mode")
                simulated_image = np.random.randint(0, 255, (480, 640), dtype=np.uint8)
                cv2.circle(simulated_image, (320, 240), 50, 200, -1)
                cv2.rectangle(simulated_image, (200, 150), (440, 330), 150, -1)
                return simulated_image
            
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
                logger.error(f"Failed to grab image: {grabResult.ErrorCode} {grabResult.ErrorDescription}")
                grabResult.Release()
                return None
                
        except Exception as e:
            logger.error(f"Error capturing image: {e}")
            import traceback
            traceback.print_exc()
            # Fall back to simulation mode on error
            try:
                simulated_image = np.random.randint(0, 255, (480, 640), dtype=np.uint8)
                cv2.circle(simulated_image, (320, 240), 50, 200, -1)
                cv2.rectangle(simulated_image, (200, 150), (440, 330), 150, -1)
                return simulated_image
            except:
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
    
    def start_video_stream(self) -> bool:
        """
        Start video streaming from the camera
        
        Returns:
            bool: True if streaming started successfully, False otherwise
        """
        try:
            if self.is_streaming:
                logger.warning("Video streaming is already active")
                return True
                
            if not self.is_connected:
                if not self.connect_camera():
                    logger.error("Failed to connect camera for video streaming")
                    return False
            
            self.is_streaming = True
            self.streaming_thread = threading.Thread(target=self._video_stream_worker, daemon=True)
            self.streaming_thread.start()
            
            logger.info("Video streaming started successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start video streaming: {e}")
            self.is_streaming = False
            return False
    
    def stop_video_stream(self):
        """Stop video streaming"""
        try:
            self.is_streaming = False
            
            if self.streaming_thread and self.streaming_thread.is_alive():
                self.streaming_thread.join(timeout=2.0)
            
            # Clear frame queue
            while not self.frame_queue.empty():
                try:
                    self.frame_queue.get_nowait()
                except queue.Empty:
                    break
            
            logger.info("Video streaming stopped")
            
        except Exception as e:
            logger.error(f"Error stopping video streaming: {e}")
    
    def _video_stream_worker(self):
        """Worker thread for continuous video capture"""
        logger.info("Video streaming worker started")
        
        while self.is_streaming:
            try:
                # Capture frame
                image = self.capture_image()
                
                if image is not None:
                    # Convert frame to JPEG for streaming
                    frame_data = self._encode_frame_for_streaming(image)
                    
                    if frame_data:
                        # Add frame to queue (non-blocking, drop if full)
                        try:
                            self.frame_queue.put_nowait(frame_data)
                            logger.debug(f"Added frame to queue, size: {len(frame_data)}")
                        except queue.Full:
                            # Drop oldest frame and add new one
                            try:
                                self.frame_queue.get_nowait()
                                self.frame_queue.put_nowait(frame_data)
                                logger.debug("Replaced oldest frame in queue")
                            except queue.Empty:
                                pass
                    else:
                        logger.warning("Failed to encode frame for streaming")
                else:
                    logger.warning("Failed to capture image for streaming")
                
                # Small delay to control frame rate
                time.sleep(0.033)  # ~30 FPS
                
            except Exception as e:
                logger.error(f"Error in video streaming worker: {e}")
                time.sleep(0.1)  # Brief delay on error
        
        logger.info("Video streaming worker stopped")
    
    def _encode_frame_for_streaming(self, image: np.ndarray) -> Optional[str]:
        """
        Encode frame for streaming as base64 JPEG
        
        Args:
            image: numpy array image
            
        Returns:
            str: Base64 encoded JPEG image, or None if failed
        """
        try:
            # Convert grayscale to RGB for better JPEG compression
            if len(image.shape) == 2:
                image_rgb = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
            else:
                image_rgb = image
            
            # Encode to JPEG
            _, buffer = cv2.imencode('.jpg', image_rgb, [cv2.IMWRITE_JPEG_QUALITY, 85])
            
            # Convert to base64
            frame_b64 = base64.b64encode(buffer).decode('utf-8')
            
            return frame_b64
            
        except Exception as e:
            logger.error(f"Error encoding frame for streaming: {e}")
            return None
    
    def get_latest_frame(self) -> Optional[str]:
        """
        Get the latest frame from the video stream
        
        Returns:
            str: Base64 encoded JPEG image, or None if no frame available
        """
        try:
            return self.frame_queue.get_nowait()
        except queue.Empty:
            return None
    
    def add_streaming_client(self, client_id: str):
        """Add a client to the streaming clients list"""
        if client_id not in self.streaming_clients:
            self.streaming_clients.append(client_id)
            logger.info(f"Added streaming client: {client_id}")
    
    def remove_streaming_client(self, client_id: str):
        """Remove a client from the streaming clients list"""
        if client_id in self.streaming_clients:
            self.streaming_clients.remove(client_id)
            logger.info(f"Removed streaming client: {client_id}")
    
    def get_streaming_status(self) -> dict:
        """Get current streaming status"""
        return {
            "is_streaming": self.is_streaming,
            "connected_clients": len(self.streaming_clients),
            "frame_queue_size": self.frame_queue.qsize(),
            "camera_connected": self.is_connected
        }
    
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
            # Stop video streaming first
            self.stop_video_stream()
            
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

def diagnose_camera_connection():
    """Diagnose camera connection issues"""
    logger.info("=== Camera Connection Diagnosis ===")
    
    if not PYLON_AVAILABLE:
        logger.error("Pylon SDK not available - install pypylon package")
        return False
    
    try:
        tlFactory = pylon.TlFactory.GetInstance()
        
        # Check transport layers
        logger.info("Available transport layers:")
        gige_found = False
        for tl in tlFactory.EnumerateTls():
            tl_name = tl.GetFriendlyName() if tl.IsFriendlyNameAvailable() else "Unknown"
            tl_type = tl.GetTLType() if tl.IsTLTypeAvailable() else "Unknown"
            logger.info(f"  - {tl_name} ({tl_type})")
            if "GigE" in tl_name or "GigE" in tl_type:
                gige_found = True
        
        if not gige_found:
            logger.error("GigE transport layer not found - check Pylon installation")
            return False
        
        # Enumerate devices
        devices = tlFactory.EnumerateDevices()
        logger.info(f"Found {len(devices)} Basler devices")
        
        if len(devices) == 0:
            logger.warning("=== TROUBLESHOOTING STEPS ===")
            logger.warning("1. Check if camera is powered on and connected")
            logger.warning("2. Verify network cable connection")
            logger.warning("3. Check camera IP configuration")
            logger.warning("4. Ensure camera and PC are on same network subnet")
            logger.warning("5. Check Windows Firewall settings")
            logger.warning("6. Verify Basler GigE Vision Filter Driver is installed")
            logger.warning("7. Try restarting Basler Service")
            logger.warning("8. Check if camera IP is in the same range as PC")
            
            # Try to get network interface info
            try:
                import socket
                hostname = socket.gethostname()
                local_ip = socket.gethostbyname(hostname)
                logger.info(f"PC IP Address: {local_ip}")
                logger.info("Camera should be in the same subnet (e.g., 169.254.x.x for link-local)")
            except:
                pass
            
            return False
        else:
            logger.info("=== CAMERA FOUND ===")
            for device in devices:
                logger.info(f"Device: {device.GetModelName()}")
                logger.info(f"  Serial: {device.GetSerialNumber()}")
                logger.info(f"  Friendly Name: {device.GetFriendlyName()}")
                logger.info(f"  Device Class: {device.GetDeviceClass()}")
            return True
        
    except Exception as e:
        logger.error(f"Diagnosis failed: {e}")
        return False

def cleanup_camera_system():
    """Cleanup camera system"""
    global camera_instance
    if camera_instance:
        camera_instance.cleanup()
        camera_instance = None

def start_camera_video_stream(camera_images_folder: str = "camera_images") -> bool:
    """Start video streaming from camera
    
    Args:
        camera_images_folder: Folder path for camera operations
        
    Returns:
        bool: True if streaming started successfully, False otherwise
    """
    global camera_instance
    
    try:
        # Get camera instance (will use simulation if real camera fails)
        camera = get_camera_instance(camera_images_folder)
        
        if not camera:
            logger.error("Failed to get camera instance for video streaming")
            return False
        
        # Start video streaming on the camera
        success = camera.start_video_stream()
        
        if success:
            logger.info("Camera video streaming started successfully")
            return True
        else:
            logger.error("Failed to start camera video streaming")
            return False
            
    except Exception as e:
        logger.error(f"Error starting camera video stream: {e}")
        return False

def stop_camera_video_stream(camera_images_folder: str = "camera_images"):
    """Stop video streaming from camera
    
    Args:
        camera_images_folder: Directory for camera operations
    """
    camera = get_camera_instance(camera_images_folder)
    camera.stop_video_stream()

def get_latest_video_frame(camera_images_folder: str = "camera_images") -> Optional[str]:
    """Get latest frame from video stream
    
    Args:
        camera_images_folder: Directory for camera operations
        
    Returns:
        str: Base64 encoded JPEG frame, or None if no frame available
    """
    try:
        camera = get_camera_instance(camera_images_folder)
        
        # Check if streaming is active
        if not camera.is_streaming:
            logger.warning("Video streaming is not active, attempting to start...")
            camera.start_video_stream()
        
        frame = camera.get_latest_frame()
        if frame:
            logger.debug(f"Got video frame, length: {len(frame)}")
        else:
            logger.debug("No video frame available")
        
        return frame
    except Exception as e:
        logger.error(f"Error getting latest video frame: {e}")
        return None

def get_camera_streaming_status(camera_images_folder: str = "camera_images") -> dict:
    """Get camera streaming status
    
    Args:
        camera_images_folder: Directory for camera operations
        
    Returns:
        dict: Streaming status information
    """
    camera = get_camera_instance(camera_images_folder)
    return camera.get_streaming_status()

def add_video_streaming_client(client_id: str, camera_images_folder: str = "camera_images"):
    """Add a client to the video streaming
    
    Args:
        client_id: Unique identifier for the client
        camera_images_folder: Directory for camera operations
    """
    camera = get_camera_instance(camera_images_folder)
    camera.add_streaming_client(client_id)

def remove_video_streaming_client(client_id: str, camera_images_folder: str = "camera_images"):
    """Remove a client from the video streaming
    
    Args:
        client_id: Unique identifier for the client
        camera_images_folder: Directory for camera operations
    """
    camera = get_camera_instance(camera_images_folder)
    camera.remove_streaming_client(client_id)
