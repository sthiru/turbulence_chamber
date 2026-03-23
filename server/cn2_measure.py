# -*- coding: utf-8 -*-
"""
Created on Fri Mar 20 10:46:37 2026

@author: ufoph
"""



import cv2
import numpy as np
import os


image_folder= "E:\TURBULENCE CHAMBER\Turbulence_chamber_190326\With_turbulence\input_images"

images = sorted(
[f for f in os.listdir(image_folder)
             if f.lower().endswith(('.png', '.jpg', '.bmp'))]
        )

if not images:
            print("No images found!")

centroids_x = []
centroids_y = []
pixel_size = 5.5e-6 
path_length = 0.6 # 100 meters path
beam_diameter = 0.007  # 2 cm beam diameter  
    
    
for img_name in images:
    path = os.path.join(image_folder, img_name)
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
    

#results = calculate_cn2("E:\TURBULENCE CHAMBER\Turbulence_chamber_190326\With_turbulence\output", PIXEL_SIZE, L, D)
print(f"Estimated Cn^2: {cn2:.2e} m^(-2/3)")
