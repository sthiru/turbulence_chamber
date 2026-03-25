# Camera Integration Installation Guide

## Overview
This guide explains how to set up the GigE Basler camera integration for the turbulence controller system.

## Prerequisites

### Hardware Requirements
- GigE Basler camera (ace/acA series recommended)
- Ethernet connection (GigE preferred)
- Sufficient lighting for beam visualization

### Software Requirements
- Basler Pylon SDK (must be installed separately)
- Python 3.8+
- Required Python packages (see requirements.txt)

## Installation Steps

### 1. Install Basler Pylon SDK
1. Download Pylon SDK from Basler website: https://www.baslerweb.com/en/support/downloads/software/pylon/
2. Install Pylon SDK with Python bindings
3. Verify installation: `python -c "from pypylon import pylon; print('Pylon installed successfully')"`

### 2. Install Python Dependencies
```bash
pip install -r requirements.txt
```

### 3. Camera Configuration
The camera system will automatically:
- Detect the first available Basler camera
- Configure for grayscale capture (Mono8)
- Set exposure time to 10000 microseconds
- Set gain to 1.0

### 4. Folder Structure
The system creates a `camera_images` folder in the project root:
```
turbulence_controller/
├── camera_images/          # Captured images stored here
├── server/
│   ├── camera_acquisition.py
│   └── main.py
└── web/
```

## Usage

### Automatic Image Capture
Images are automatically captured during background polling:
- Frequency: Same as polling interval (default 1 second)
- Filename format: `camera_YYYYMMDD_HHMMSS_mmm.png`
- Storage: `camera_images/` folder

### Manual Image Capture
```bash
# Trigger manual capture via API
curl -X POST http://localhost:8000/api/camera/capture
```

### Camera Status
```bash
# Check camera status
curl http://localhost:8000/api/camera/status
```

## Integration with CN² Measurement

The captured images are used by the CN² measurement system:

1. **Image Acquisition**: Camera captures beam images
2. **Image Processing**: `cn2_measure.py` processes images to find beam centroids
3. **CN² Calculation**: Centroid variance used to calculate turbulence strength

### CN² Measurement Process
```python
# Images are automatically processed by cn2_measure.py
# Process:
# 1. Load images from camera_images folder
# 2. Apply thresholding to remove noise
# 3. Calculate beam centroids using image moments
# 4. Compute spatial variance
# 5. Apply CN² formula: Cn² = σ² / (2.84 * L³ * D^(-1/3))
```

## Configuration

### Camera Settings
Edit `camera_acquisition.py` to modify:
- `exposure_time`: Camera exposure (microseconds)
- `gain`: Camera gain
- `image_format`: Image format (Mono8 recommended)

### Image Storage
- Default folder: `camera_images`
- Format: PNG grayscale
- Naming: Timestamp-based

## Troubleshooting

### Camera Not Found
1. Verify Pylon SDK installation
2. Check camera connection
3. Ensure camera is powered and connected via Ethernet

### Simulation Mode
If Pylon SDK is not available, system runs in simulation mode:
- Generates synthetic images for testing
- Logs warning: "Pylon SDK not available - using simulation mode"

### Image Quality Issues
1. Adjust exposure time in camera settings
2. Improve lighting conditions
3. Check camera focus
4. Verify beam visibility

## API Endpoints

### Camera Status
- **GET** `/api/camera/status` - Get camera system status
- **POST** `/api/camera/capture` - Manual image capture

### Response Format
```json
{
  "initialized": true,
  "connected": true,
  "available": true,
  "camera_info": {
    "model": "acA1920-40uc",
    "serial": "12345678",
    "vendor": "Basler"
  },
  "image_folder": "camera_images"
}
```

## Integration Notes

### Background Polling
Camera capture is integrated into the background status polling loop:
- Captures image after CN² calculation
- Adds camera data to status messages
- Includes camera status in WebSocket broadcasts

### Data Flow
```
Arduino Status → Background Polling → Camera Capture → Status History → WebSocket Broadcast
```

### Error Handling
- Camera errors don't interrupt Arduino polling
- Failed captures logged but system continues
- Camera status included in error reports

## Performance Considerations

### Capture Rate
- Default: 1 image per second (same as polling)
- Adjustable via polling interval endpoint
- Consider storage requirements for long runs

### Storage Management
- Images accumulate in `camera_images` folder
- Implement cleanup for long-term operation
- Monitor disk space usage

### Network Bandwidth
- GigE cameras require sufficient network bandwidth
- Use dedicated network if possible
- Consider image compression if needed
