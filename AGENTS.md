# AGENTS.md - Turbulence Chamber System Architecture

This document describes the autonomous agents and components in the turbulence chamber control system for generating Cn² values on demand.

## System Overview

The turbulence chamber system is a distributed instrumentation control platform running on Raspberry Pi 5, consisting of hardware control, data acquisition, optical measurement, and user interface agents working together to generate and maintain desired Cn² (refractive index structure parameter) values.

## Agent Architecture

### 1. Arduino Hardware Control Agent

**Location:** `arduino/temperature_control/temperature_control.ino`

**Hardware Platform:** Arduino Mega 2560

**Responsibilities:**
- Real-time sensor data acquisition from multiple sensor types
- Hardware actuator control (hot plates, fans)
- PID-based temperature regulation
- Serial communication with Python server

**Sensors Managed:**
- **DS18B20 Temperature Sensors:** 12 sensors on OneWire bus (Pin 2)
  - Hardcoded addresses for consistent sensor identification
  - Update interval: 1 second
- **BME280 Pressure/Temperature Sensors:** 2 sensors via SPI (Pins 26, 28)
  - Pressure and ambient temperature measurements
  - SPI communication on hardware SPI pins (50, 51, 52)
- **DHT22 Humidity Sensors:** 2 sensors (Pins 22, 24)
  - Temperature and humidity measurements
  - Update interval: 10 seconds
- **Air Flow Sensors:** 4 analog sensors (Pins A0-A3)
  - Flow rate measurement using 6th-order polynomial conversion
  - Polynomial coefficients per sensor for voltage-to-flow conversion

**Actuators Controlled:**
- **Hot Plates:** 2 SSR-relay controlled (Pins 8, 9)
  - On/off control via SSR-40DA relays
  - Target temperature: 0-120°C
- **DC Fans:** 4 MOSFET PWM controlled (Pins 3, 4, 5, 6)
  - PWM speed control: 0-255
  - 24V power supply
  - Default speed: 255 (max)

**Communication Protocol:**
- Baud rate: 250000
- JSON command/response format
- Commands: `get_status`, `set_temp`, `set_fan`, `toggle_hotplate`, `ping`
- Status includes all sensor readings, actuator states, and system flags

**Safety Features:**
- Maximum temperature limit: 120°C
- Status LED on Pin 13 for visual indication
- Safe initialization (all outputs off, fans max)

---

### 2. Arduino Communication Agent

**Location:** `server/arduino_comm.py`

**Responsibilities:**
- Serial port management and connection handling
- Command encoding/decoding (JSON)
- Automatic reconnection on connection loss
- Connection health monitoring
- Thread-safe communication with async lock

**Configuration:**
- Default baud rate: 250000 (configurable)
- Port auto-detection: COM4-9 (Windows), /dev/ttyACM0 (Linux)
- Config file support: `arduino_config.py`
- Connection timeout: 2 seconds
- Read timeout: 10 seconds

**Key Methods:**
- `connect()`: Establish serial connection
- `disconnect()`: Clean connection termination
- `send_command()`: Send JSON command, await response
- `get_status()`: Query current system state
- `set_temperature()`: Set hot plate target temperature
- `set_fan_speed()`: Set fan PWM value
- `toggle_hot_plate()`: Enable/disable hot plate
- `monitor_connection()`: Background health check with auto-reconnect

**Error Handling:**
- JSON decode error detection
- Connection instability detection
- Automatic disconnect on communication errors
- Consecutive failure tracking (max 3 before forced reconnect)

---

### 3. Python Server Agent (Central Coordinator)

**Location:** `server/main.py`

**Framework:** FastAPI with WebSocket support

**Responsibilities:**
- RESTful API endpoints for external control
- WebSocket server for real-time data streaming
- Background polling of Arduino status
- Data capture session management
- Camera integration coordination
- CN² calculation coordination
- Static file serving (web interface, camera images)

**API Endpoints:**
- `GET /` - Main dashboard
- `GET /main` - Control panel interface
- `GET /health` - System health check
- `GET /api/status` - Current system status
- `POST /api/temperature/set` - Set target temperature
- `POST /api/fan/set` - Set fan speed
- `POST /api/hotplate/{id}/toggle` - Toggle hot plate
- `GET /api/sensors` - Get all sensor data
- `GET /api/camera/status` - Camera system status
- `POST /api/camera/capture` - Manual image capture
- `GET /api/cn2/optical/status` - Optical CN² status
- `POST /api/cn2/optical/calculate` - Trigger optical CN² calculation

**WebSocket Endpoints:**
- `/ws/status` - Real-time status updates
- `/ws/video` - Video streaming

**Background Tasks:**
- `background_status_polling()`: Poll Arduino at configurable interval (default 3s)
  - Calculates thermal CN² from temperature differences
  - Triggers camera image capture during data capture sessions
  - Broadcasts status to all WebSocket clients
- `video_streaming_worker()`: Stream camera frames to video clients (~30 FPS)

**Data Management:**
- Status history: deque with max 1000 records
- Data capture sessions: Timestamped folders with synchronized images
- CSV export capability for captured data

**CN² Thermal Calculation:**
- Formula: `(7.9e-5 * (P / T²))² * (dt² / r^(2/3))`
- Uses BME280 ambient temperature and pressure
- Calculates temperature difference (dt²) from DS18B20 sensors
- Default radial distance (r): 0.5 meters

---

### 4. Camera Acquisition Agent

**Location:** `server/camera_acquisition.py`

**Hardware:** Basler GigE camera with Pylon SDK

**Responsibilities:**
- Camera initialization and connection management
- Image capture and saving
- Video streaming to web clients
- PFS (Pylon Feature Set) settings management
- Frame encoding for web transmission

**Camera Configuration:**
- Default exposure: 10000 μs
- Default gain: 1.0
- Pixel format: Mono8
- Settings file: `camera_settings.pfs`

**Key Methods:**
- `initialize_camera()`: Detect and open Basler camera
- `connect_camera()`: Start image grabbing
- `capture_image()`: Capture single frame (numpy array)
- `capture_and_save()`: Capture and save with timestamp
- `start_video_stream()`: Start background streaming thread
- `stop_video_stream()`: Stop streaming and cleanup
- `load_pfs_settings()`: Load camera parameters from .pfs file
- `apply_pfs_settings_to_camera()`: Apply loaded settings

**Video Streaming:**
- Frame queue: 10 frame buffer
- Encoding: JPEG at 85% quality
- Transmission: Base64 encoded via WebSocket
- Frame rate: ~30 FPS
- Client management: Add/remove streaming clients

**Fallback Mode:**
- Simulation mode when Pylon SDK unavailable
- Generates random grayscale images with geometric shapes
- Allows system testing without camera hardware

---

### 5. CN² Optical Calculation Agent

**Location:** `server/cn2/cn2_optical.py`

**Method:** Beam wander variance analysis

**Responsibilities:**
- Process camera images to calculate beam centroid positions
- Compute spatial variance of beam wander
- Calculate CN² from optical measurements
- Manage image queue for batch processing

**Optical Parameters:**
- Pixel size: 5.5 μm
- Path length: 0.6 meters (60 cm)
- Beam diameter: 7 mm
- CN² coefficient: 2.84 (beam wander)
- Image threshold: 20 (noise removal)

**Calculation Process:**
1. Load grayscale images from camera_images folder
2. Apply thresholding to remove noise
3. Calculate image moments for centroid (cx, cy)
4. Collect centroids from multiple images (minimum 30)
5. Compute variance in x and y directions
6. Apply beam wander formula: `Cn² = σ² / (2.84 * L³ * D^(-1/3))`

**Key Methods:**
- `get_available_images()`: List sorted image files
- `calculate_beam_centroid()`: Compute single image centroid
- `calculate_cn2_from_images()`: Batch process images for CN²
- `get_status()`: Return calculation status and last result

**Integration:**
- Called by main server during background polling
- Requires minimum 30 images for calculation
- Returns None if insufficient data
- Tracks last calculation time and value

---

### 6. Web Interface Agent

**Location:** `web/` directory

**Components:**
- `index.html` - Main dashboard with Chart.js visualization
- `control-panel.html` - SVG-based interactive control panel
- `main.js` - Dashboard JavaScript (Chart.js, WebSocket client)
- `script.js` - Control panel JavaScript (SVG manipulation, WebSocket)
- `camera.js` - Camera-specific functionality
- `main.svg` - Interactive SVG diagram of chamber layout

**Responsibilities:**
- Real-time data visualization (temperature charts, sensor displays)
- Interactive controls (fan sliders, hot plate toggles)
- WebSocket client for live updates
- Data capture session management UI
- Camera video streaming display
- CSV data download

**Visualization Features:**
- Temperature history chart (5-minute rolling window)
- Sensor cards with color-coded status
- Fan speed progress bars with sliders
- Hot plate controls with target temperature input
- CN² display with scientific notation
- BME280 sensor readings (pressure, humidity)
- Air flow sensor displays

**Interactive Controls:**
- Fan speed sliders (0-255 PWM)
- Hot plate on/off toggles
- Target temperature inputs (auto-submit on change)
- Data capture start/stop buttons
- COM port selection and reconnection
- Polling interval adjustment

**WebSocket Integration:**
- Auto-reconnection on disconnect (3s delay)
- Message type handling: `system_status`, `current_data`, `historical_data`, `video_frame`
- Real-time SVG updates for fan animations and hot plate states
- Chart.js updates without animation for performance

---

### 7. Data Capture Agent

**Location:** Integrated in `server/main.py` and `web/main.js`

**Responsibilities:**
- Manage data capture sessions
- Synchronize sensor data with camera images
- Organize captured data by timestamp
- Export data to CSV format

**Session Structure:**
- Folder: `camera_images/DD_MMM_YYYY/HH_MM/`
- Images: `camera_YYYYMMDD_HHMMSS_mmm.png`
- Data points include: timestamp, temperatures, target temperatures, fan speeds, hot plate states, CN² values, pressure, humidity, image filename

**API Endpoints:**
- `POST /api/data-capture` - Start/stop capture session
- `GET /api/data-capture/status` - Query capture status
- `GET /api/data-capture/download` - Download CSV export

**Web UI:**
- Start/stop capture buttons
- Data counter badge
- Download button for CSV export
- Session information display

---

## Agent Communication Flow

```
┌─────────────────┐
│   Web Browser   │
│  (WebSocket UI) │
└────────┬────────┘
         │ WebSocket
         ▼
┌─────────────────────────────────┐
│   Python Server Agent           │
│  (FastAPI + WebSocket)          │
├─────────────────────────────────┤
│ - Background polling (3s)       │
│ - Video streaming worker       │
│ - Data capture coordination    │
└──────┬──────────────┬───────────┘
       │              │
       │ Serial       │ Pylon SDK
       ▼              ▼
┌─────────────┐  ┌─────────────────┐
│  Arduino    │  │  Basler Camera  │
│  Hardware   │  │  Acquisition    │
│  Agent      │  │  Agent          │
├─────────────┤  └─────────────────┘
│ - Sensors   │         │
│ - Actuators │         │
└─────────────┘         │
                        ▼
               ┌─────────────────┐
               │  CN² Optical    │
               │  Calculation    │
               │  Agent          │
               └─────────────────┘
```
---

## Configuration Files

- `server/requirements.txt` - Python dependencies
- `server/arduino_config.py` - Arduino port configuration
- `camera_settings.pfs` - Basler camera parameters
- `turbulence_chamber.service` - Systemd service file for auto-start

## Hardware Specifications

**Arduino Mega 2560:**
- 54 digital I/O pins
- 16 analog inputs
- 256 KB flash memory
- 8 KB SRAM

**Raspberry Pi 5:**
- Quad-core Cortex-A76
- 8 GB RAM (recommended)
- USB 3.0 ports for Arduino connection
- Gigabit Ethernet for camera

**Sensors:**
- DS18B20: -55°C to +125°C, ±0.5°C accuracy
- BME280: -40°C to +85°C, ±1°C accuracy, 300-1100 hPa
- DHT22: -40°C to +80°C, ±0.5°C accuracy, 0-100% RH
- Air flow sensors: Analog voltage output, polynomial conversion

**Actuators:**
- SSR-40DA: 40A solid state relay
- IRF540: 33A, 100V MOSFET
- PGSA2Z: 24V brushless cooling fans

---

## Dependencies

**Python:**
- fastapi - Web framework
- uvicorn - ASGI server
- pydantic - Data validation
- pyserial - Serial communication
- opencv-python - Image processing
- numpy - Numerical computations
- pypylon - Basler camera SDK
- websockets - WebSocket support

**Arduino:**
- OneWire - DS18B20 communication
- DallasTemperature - DS18B20 library
- ArduinoJson - JSON parsing
- Adafruit_BMP280 - BME280 sensor
- DHT22 - Humidity sensor library

**Web:**
- Chart.js - Temperature charting
- Font Awesome - Icons
- Bootstrap - UI framework (optional)
