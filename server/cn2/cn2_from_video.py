# -*- coding: utf-8 -*-
"""
Created on Tue Apr 21 15:44:53 2026

@author: ufoph
"""

import cv2
import numpy as np
import matplotlib.pyplot as plt

# ================= USER INPUT =================
video_path = "E:/TURBULENCE CHAMBER/17_04_2026_Data/Image/part4.mp4"
wavelength = 1064e-9   # meters
L = 1              # propagation distance (m)
window_size = 10      # pixels (centroid sampling window)

# =============================================


from scipy.optimize import curve_fit

# 2D Gaussian model
def gaussian_2d(coords, I0, x0, y0, wx, wy, offset):
    x, y = coords
    return (
        I0 * np.exp(-2 * (((x - x0)**2) / wx**2 + ((y - y0)**2) / wy**2))
        + offset
    ).ravel()


def fit_gaussian_2d(image):
    h, w = image.shape
    y, x = np.indices((h, w))

    xdata = np.vstack((x.ravel(), y.ravel()))
    zdata = image.ravel()

    # initial guesses
    I0_guess = np.max(image)
    x0_guess = w / 2
    y0_guess = h / 2
    wx_guess = w / 4
    wy_guess = h / 4
    offset_guess = np.min(image)

    p0 = [I0_guess, x0_guess, y0_guess, wx_guess, wy_guess, offset_guess]

    try:
        popt, _ = curve_fit(
            gaussian_2d,
            xdata,
            zdata,
            p0=p0,
            maxfev=5000
        )

        I0, x0, y0, wx, wy, offset = popt
        return x0, y0, wx, wy, I0

    except RuntimeError:
        return None  # fit failed


k = 2 * np.pi / wavelength

cap = cv2.VideoCapture(video_path)

centroids = []
intensity_series = []

frame_count = 0

while True:
    ret, frame = cap.read()
    if not ret:
        break

    frame_count += 1

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float64)
    gray /= 255.0

    # --- Threshold (adaptive is more robust) ---
    thresh = cv2.adaptiveThreshold(
        (gray * 255).astype(np.uint8),
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        11, 2
    )
    mask = thresh / 255.0

    beam = gray * mask

    # --- Coordinate grid ---
    h, w = beam.shape
    y, x = np.indices((h, w))

    total_intensity = np.sum(beam) + 1e-16

    # --- Centroid ---
    x_c = np.sum(x * beam) / total_intensity
    y_c = np.sum(y * beam) / total_intensity

    centroids.append((x_c, y_c))
    x_i, y_i = int(x_c), int(y_c)

    half_w = window_size // 2

    x_min = max(0, x_i - half_w)
    x_max = min(w, x_i + half_w)
    y_min = max(0, y_i - half_w)
    y_max = min(h, y_i + half_w)

    window = gray[y_min:y_max, x_min:x_max]

    if window.size > 0:
        intensity_series.append(np.mean(window))

cap.release()


"""
    
beam_radii = []
centroids = []
intensity_series = []

roi_size = 60  # important: Gaussian fit needs good ROI

while True:
    ret, frame = cap.read()
    if not ret:
        break
    frame_count += 1
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float64)
    gray /= 255.0

    h, w = gray.shape

    # --- rough centroid first (fast pre-estimate) ---
    y, x = np.indices((h, w))
    I_sum = np.sum(gray) + 1e-12

    x_c = np.sum(x * gray) / I_sum
    y_c = np.sum(y * gray) / I_sum

    centroids.append([x_c, y_c])

    # --- extract ROI around centroid ---
    x_c, y_c = int(x_c), int(y_c)

    x_min = max(0, x_c - roi_size)
    x_max = min(w, x_c + roi_size)
    y_min = max(0, y_c - roi_size)
    y_max = min(h, y_c + roi_size)

    roi = gray[y_min:y_max, x_min:x_max]

    if roi.size < 100:
        continue

    # --- Gaussian fit ---
    result = fit_gaussian_2d(roi)

    if result is not None:
        x0, y0, wx, wy, I0 = result

        # 1/e² beam radius (true physical parameter)
        w_avg = (wx + wy) / 2.0
        beam_radii.append(w_avg)

        intensity_series.append(I0)
    else:
        beam_radii.append(np.nan)
        intensity_series.append(np.nan)

cap.release()

"""
    # --- Stable intensity (centroid window) ---
    

centroids = np.array(centroids)
intensity_series = np.array(intensity_series)

# ================= ANALYSIS =================

# --- Scintillation Index ---
I_mean = np.mean(intensity_series)
I2_mean = np.mean(intensity_series**2)
scint_index = (I2_mean / (I_mean**2)) - 1

# --- Log-intensity (better for Rytov) ---
log_I = np.log(intensity_series + 1e-10)
rytov_variance = np.var(log_I)

# --- Cn^2 estimation (weak turbulence only) ---
Cn2 = rytov_variance / (0.5 * (k**(7/6)) * (L**(11/6)))

# --- Beam wander ---
x_var = np.var(centroids[:, 0])
y_var = np.var(centroids[:, 1])

# ================= OUTPUT =================

print("\n===== RESULTS =====")
print(f"Frames processed: {frame_count}")
print(f"Scintillation Index: {scint_index:.6f}")
print(f"Rytov Variance: {rytov_variance:.6f}")
print(f"Estimated Cn^2: {Cn2:.3e} m^(-2/3)")
print(f"Beam wander variance (x): {x_var:.4f}")
print(f"Beam wander variance (y): {y_var:.4f}")
print(video_path)

# ================= PLOTS =================

plt.figure(figsize=(12, 8))

# Centroid motion
plt.subplot(2,2,1)
plt.plot(centroids[:,0], label='x')
plt.plot(centroids[:,1], label='y')
plt.title("Centroid Motion")
plt.legend()

# Beam trajectory
plt.subplot(2,2,2)
plt.plot(centroids[:,0], centroids[:,1])
plt.title("Beam Trajectory")
plt.xlabel("x")
plt.ylabel("y")

# Intensity fluctuations
plt.subplot(2,2,3)
plt.plot(intensity_series)
plt.title("Intensity (Centroid Window)")

# Histogram
plt.subplot(2,2,4)
plt.hist(intensity_series, bins=50)
plt.title("Intensity Distribution")

plt.tight_layout()
plt.show()