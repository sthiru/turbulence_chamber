# -*- coding: utf-8 -*-
"""
Created on Fri Mar 20 11:02:23 2026

@author: ufoph
"""

import numpy as np
import cv2
import os
import glob

def calculate_scintillation(image_folder):
    # Load all image paths (adjust extension if using .tiff or .bmp)
    image_files = sorted(glob.glob(os.path.join(image_folder, "*.jpg")))
    
    if not image_files:
        print("No images found!")
        return None

    intensities = []

    for img_path in image_files:
        # Load image in grayscale
        img = cv2.imread(img_path, cv2.IMREAD_UNCHANGED)
        # img=cv2.imshow("IMAGE",img)
        
        # Method 1: On-axis Scintillation (Intensity at the beam peak/center)
        # We use a small ROI to average out camera noise
        h, w = img.shape[:2]
        center_roi = img[h//2-200:h//2+200, w//2-1:w//2+1]
        intensities.append(np.mean(center_roi))

    intensities = np.array(intensities)

    # Calculate Scintillation Index
    mean_I = np.mean(intensities)
    mean_I2 = np.mean(intensities**2)
    
    scintillation_index = (mean_I2 / (mean_I**2)) - 1
    
    return scintillation_index

# Usage
folder_path = 'E:\TURBULENCE CHAMBER\Turbulence_chamber_190326\With_turbulence\input_images'
si = calculate_scintillation(folder_path)
print(f"Estimated Scintillation Index: {si:.4f}")



def calculate_rytov_parameters(L_mm, wavelength_nm, Cn2=None, scintillation_index=None):
    # Convert to SI units
    L = L_mm / 1000.0
    lam = wavelength_nm * 1e-9
    k = 2 * np.pi / lam
    
    # Calculate constant part: k^(7/6) * L^(11/6)
    factor = (k**(7/6)) * (L**(11/6))
    
    coeff_plane = 1.23 * factor
    coeff_spherical = 0.5 * factor
    
    print(f"--- Turbulence parameters for L={L_mm}mm, λ={wavelength_nm}nm ---")
    
    if Cn2 is not None:
        sigma_r2_p = coeff_plane * Cn2
        sigma_r2_s = coeff_spherical * Cn2
        print(f"Given Cn^2 = {Cn2:.2e} m^-2/3:")
        print(f"  Rytov Variance (Plane):     {sigma_r2_p:.4f}")
        print(f"  Rytov Variance (Spherical): {sigma_r2_s:.4f}")
        
    if scintillation_index is not None:
        # In weak turbulence (sigma_I^2 < 0.3), sigma_I^2 approx sigma_R^2
        estimated_Cn2 = scintillation_index / coeff_plane
        print(f"Given Scintillation Index (sigma_I^2) = {scintillation_index}:")
        print(f"  Estimated Cn^2 (Plane Model): {estimated_Cn2:.2e} m^-2/3")

# Example: If you measured a scintillation index of 0.05 from your images
calculate_rytov_parameters(L_mm=500, wavelength_nm=532, scintillation_index=0.017)