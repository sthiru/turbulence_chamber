# -*- coding: utf-8 -*-
"""
CN² Optical Calculation Module
Calculates turbulence strength from camera images using beam wander analysis
Integrated with turbulence controller WebSocket system
"""

import cv2
import numpy as np
import os
import logging
from typing import List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

class CN2OpticalCalculator:
    """CN² calculation from optical beam wander measurements"""
    
    def __init__(self, camera_images_folder: str = "camera_images"):
        """
        Initialize CN² calculator
        
        Args:
            camera_images_folder: Directory containing captured camera images
        """
        self.camera_images_folder = camera_images_folder
        self.required_images = 30  # Calculate CN² after 30 images
        
        # Optical parameters (from original cn2_measure.py)
        self.pixel_size = 5.5e-6  # meters (5.5 micrometers)
        self.path_length = 0.6     # meters (60 cm path length)
        self.beam_diameter = 0.007  # meters (7 mm beam diameter)
        
        # CN² calculation constants
        self.cn2_coefficient = 2.84  # Beam wander coefficient
        self.threshold_value = 20    # Image threshold for noise removal
        
        # Tracking variables
        self.last_calculation_count = 0
        self.last_cn2_value = 0.0
        self.last_calculation_time = None
        
    def get_available_images(self) -> List[str]:
        """
        Get list of available image files sorted by name
        
        Returns:
            List of image filenames
        """
        try:
            if not os.path.exists(self.camera_images_folder):
                logger.warning(f"Camera images folder not found: {self.camera_images_folder}")
                return []
                
            images = sorted([
                f for f in os.listdir(self.camera_images_folder)
                if f.lower().endswith(('.png', '.jpg', '.bmp'))
            ])
            
            return images
            
        except Exception as e:
            logger.error(f"Error getting image list: {e}")
            return []
    
    def calculate_beam_centroid(self, image_path: str) -> Optional[Tuple[float, float]]:
        """
        Calculate beam centroid from a single image
        
        Args:
            image_path: Path to the image file
            
        Returns:
            Tuple of (centroid_x, centroid_y) or None if calculation fails
        """
        try:
            # Load image in grayscale
            img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
            if img is None:
                logger.warning(f"Could not load image: {image_path}")
                return None
                
            # Apply thresholding to remove noise
            _, thresh = cv2.threshold(img, self.threshold_value, 255, cv2.THRESH_TOZERO)
            
            # Calculate moments for centroid
            M = cv2.moments(thresh)
            
            if M["m00"] == 0:
                logger.warning(f"No valid pixels found in image: {image_path}")
                return None
                
            # Calculate centroid coordinates
            cx = M["m10"] / M["m00"]
            cy = M["m01"] / M["m00"]
            
            return (cx, cy)
            
        except Exception as e:
            logger.error(f"Error calculating centroid for {image_path}: {e}")
            return None
    
    def calculate_cn2_from_images(self, image_paths: List[str]) -> Optional[float]:
        """
        Calculate CN² from a list of image paths
        
        Args:
            image_paths: List of image file paths
            
        Returns:
            CN² value or None if calculation fails
        """
        try:
            if len(image_paths) < 2:
                logger.warning(f"Insufficient images for CN² calculation: {len(image_paths)}")
                return None
                
            centroids_x = []
            centroids_y = []
            valid_images = 0
            
            # Process each image
            for img_path in image_paths:
                full_path = os.path.join(self.camera_images_folder, img_path)
                centroid = self.calculate_beam_centroid(full_path)
                
                if centroid is not None:
                    cx, cy = centroid
                    centroids_x.append(cx)
                    centroids_y.append(cy)
                    valid_images += 1
                else:
                    logger.debug(f"Skipping invalid image: {img_path}")
            
            if len(centroids_x) < 2:
                logger.warning(f"Insufficient valid centroids: {len(centroids_x)}")
                return None
                
            # Calculate spatial variance
            variance_x = np.var(centroids_x) * (self.pixel_size ** 2)
            variance_y = np.var(centroids_y) * (self.pixel_size ** 2)
            total_variance = (variance_x + variance_y) / 2
            
            # CN² Formula for Beam Wander (Spherical Wave Approximation)
            # σ² = 2.84 * Cn² * L³ * D^(-1/3)
            # Rearranged: Cn² = σ² / (2.84 * L³ * D^(-1/3))
            
            cn2 = total_variance / (self.cn2_coefficient * (self.path_length ** 3) * (self.beam_diameter ** (-1/3)))
            
            logger.info(f"CN² calculated from {valid_images} images: {cn2:.2e} m^(-2/3)")
            logger.debug(f"Variance X: {variance_x:.2e}, Variance Y: {variance_y:.2e}")
            
            return cn2
            
        except Exception as e:
            logger.error(f"Error calculating CN²: {e}")
            return None
    
    def should_calculate_cn2(self) -> bool:
        """
        Check if CN² calculation should be performed
        
        Returns:
            True if calculation should be performed
        """
        images = self.get_available_images()
        return len(images) >= self.required_images and len(images) > self.last_calculation_count
    
    def calculate_cn2_if_ready(self) -> Optional[float]:
        """
        Calculate CN² if enough images are available
        
        Returns:
            CN² value if calculated, None otherwise
        """
        try:
            if not self.should_calculate_cn2():
                return None
                
            # Get the latest images for calculation
            images = self.get_available_images()
            latest_images = images[-self.required_images:]  # Use the most recent images
            
            # Calculate CN²
            cn2_value = self.calculate_cn2_from_images(latest_images)
            
            if cn2_value is not None:
                self.last_cn2_value = cn2_value
                self.last_calculation_count = len(images)
                self.last_calculation_time = datetime.now()
                
                logger.info(f"CN² optical calculation completed: {cn2_value:.2e} m^(-2/3)")
                return cn2_value
            else:
                logger.warning("CN² calculation failed")
                return None
                
        except Exception as e:
            logger.error(f"Error in CN² calculation workflow: {e}")
            return None
    
    def get_calculation_status(self) -> dict:
        """
        Get current calculation status
        
        Returns:
            Dictionary with calculation status information
        """
        images = self.get_available_images()
        
        return {
            "available_images": len(images),
            "required_images": self.required_images,
            "ready_for_calculation": len(images) >= self.required_images,
            "last_calculation_count": self.last_calculation_count,
            "last_cn2_value": self.last_cn2_value,
            "last_calculation_time": self.last_calculation_time.isoformat() if self.last_calculation_time else None,
            "parameters": {
                "pixel_size": self.pixel_size,
                "path_length": self.path_length,
                "beam_diameter": self.beam_diameter,
                "threshold_value": self.threshold_value
            }
        }

# Global CN² calculator instance
cn2_calculator = None

def get_cn2_calculator(camera_images_folder: str = "camera_images") -> CN2OpticalCalculator:
    """Get or create global CN² calculator instance"""
    global cn2_calculator
    if cn2_calculator is None:
        cn2_calculator = CN2OpticalCalculator(camera_images_folder)
    return cn2_calculator

def calculate_cn2_optical(camera_images_folder: str = "camera_images") -> Optional[float]:
    """
    Calculate CN² from optical measurements if ready
    
    Args:
        camera_images_folder: Directory containing camera images
        
    Returns:
        CN² value if calculated, None otherwise
    """
    calculator = get_cn2_calculator(camera_images_folder)
    return calculator.calculate_cn2_if_ready()

def get_cn2_status(camera_images_folder: str = "camera_images") -> dict:
    """
    Get CN² calculation status
    
    Args:
        camera_images_folder: Directory containing camera images
        
    Returns:
        Dictionary with calculation status
    """
    calculator = get_cn2_calculator(camera_images_folder)
    return calculator.get_calculation_status()

def reset_cn2_calculation(camera_images_folder: str = "camera_images"):
    """
    Reset CN² calculation tracking
    
    Args:
        camera_images_folder: Directory containing camera images
    """
    global cn2_calculator
    cn2_calculator = CN2OpticalCalculator(camera_images_folder)
    logger.info("CN² calculation tracking reset")
