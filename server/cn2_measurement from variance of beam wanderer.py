# -*- coding: utf-8 -*-
"""
Created on Fri Feb 27 14:59:03 2026

@author: prase
"""


import cv2
import numpy as np
import os



def get_sorted_images(image_folder):
    """
    Returns a sorted list of image filenames from the given folder.
    Supports .png, .jpg, and .bmp formats.
    """
    try:
        # Ensure the folder exists
        if not os.path.isdir(image_folder):
            print(f"Error: '{image_folder}' is not a valid directory.")
            return None

        # Get and sort image files
        images = sorted(
            [f for f in os.listdir(image_folder)
             if f.lower().endswith(('.png', '.jpg', '.bmp'))]
        )

        if not images:
            print("No images found!")
            return None

        return images

    except Exception as e:
        print(f"An error occurred: {e}")
        return None


def calculate_cn2(image_folder, pixel_size, path_length, beam_diameter):
    """
    Estimates Cn^2 based on beam wander variance.
    
    Args:
        image_folder (str): Path to the folder containing beam images.
        pixel_size (float): Size of one pixel in meters (e.g., 5.5e-6 for 5.5um).
        path_length (float): Propagation distance in meters (L).
        beam_diameter (float): Beam diameter at the aperture in meters (W).
    """
    centroids_x = []
    centroids_y = []

    folder_path = "E:\TURBULENCE CHAMBER\Turbulence_chamber_190326\with_turbulence"
    images = get_sorted_images(folder_path)
   

    for img_name in images:
        path = os.path.join(folder_path, img_name)
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        
        # Thresholding to remove noise
        _, thresh = cv2.threshold(img, 20, 255, cv2.THRESH_TOZERO)
        
        # Calculate Moments for Centroid
        M = cv2.moments(thresh)
        if M["m00"] != 0:
            cx = M["m10"] / M["m00"]
            cy = M["m01"] / M["m00"]
            centroids_x.append(cx)
            centroids_y.append(cy)

    # Convert pixel variance to spatial variance (meters squared)
    variance_x = np.var(centroids_x) * (pixel_size**2)
    variance_y = np.var(centroids_y) * (pixel_size**2)
    total_variance = (variance_x + variance_y) / 2

    # Cn^2 Formula for Beam Wander (Spherical Wave Approximation)
    # sigma^2 = 2.84 * Cn^2 * L^3 * D^(-1/3)
    # Rearranged: Cn^2 = sigma^2 / (2.84 * L^3 * D^(-1/3))
    
    cn2 = total_variance / (2.84 * (path_length**3) * (beam_diameter**(-1/3)))
    
    return cn2

image_folder="E:\TURBULENCE CHAMBER\Turbulence_chamber_190326\with_turbulence"
# --- Configuration ---
# Gentec Beamage-4M pixel size is 5.5 micrometers
PIXEL_SIZE = 5.5e-6 
L = 0.6 # 100 meters path
D = 0.007  # 2 cm beam diameter

results = calculate_cn2("E:\TURBULENCE CHAMBER\Turbulence_chamber_190326\with_turbulence", PIXEL_SIZE, L, D)
print(f"Estimated Cn^2: {results:.2e} m^(-2/3)")
