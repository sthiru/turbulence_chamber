# Temperature Control System

A comprehensive Arduino-based temperature control system with 6 DS18B20 sensors, 4 DC fans, 2 hot plates, FastAPI server, and web interface for remote monitoring and control.

## System Overview

This system provides precise temperature control for multiple heating elements with real-time monitoring and control capabilities through a web interface. It's designed for laboratory or industrial applications requiring accurate temperature regulation.

## Hardware Requirements

### Components
- **Arduino Mega 2560** (recommended for sufficient I/O pins)
- **DS18B20 Temperature Sensors** (6 units) with 4.7kΩ pull-up resistor
- **SSR-40DA Solid State Relays** (2 units) for hot plate control
- **IRF540 MOSFETs** (4 units) for fan speed control
- **24V DC Fans** (4 units) - PGSA2Z brushless cooling fans
- **Hot Plates** (2 units) compatible with SSR relays
- **Power Supply**: 24V for fans, appropriate voltage for hot plates
- **Raspberry Pi** (or similar) for running the FastAPI server

### Wiring Diagram
```
Arduino Mega Pin Assignments:
- Pin 2: DS18B20 OneWire Data Bus (all sensors in parallel)
- Pin 3: MOSFET Fan 1 PWM
- Pin 5: MOSFET Fan 2 PWM  
- Pin 6: MOSFET Fan 3 PWM
- Pin 10: MOSFET Fan 4 PWM
- Pin 8: SSR Relay 1 (Hot Plate 1)
- Pin 9: SSR Relay 2 (Hot Plate 2)
- Pin 13: Status LED
- GND: Common ground
- VIN: Power input (7-12V)

DS18B20 Sensors (all in parallel):
- VDD: 3.3V or 5V
- GND: Ground
- Data: Pin 2 (with 4.7kΩ pull-up to VDD)

MOSFET Fan Control:
- Gate: Arduino PWM pin
- Drain: Fan negative terminal
- Source: Ground
- Fan positive: 24V power supply

SSR Relay Control:
- Control+: Arduino digital pin
- Control-: Ground
- Load+: Hot plate power
- Load-: Hot plate
```

## Software Requirements

### Arduino IDE
- Version 1.8.0 or later
- Required libraries:
  - OneWire (by Jim Studt)
  - DallasTemperature (by Miles Burton)
  - ArduinoJson (by Benoit Blanchon)

### Python Server
- Python 3.8 or higher
- Requirements listed in `server/requirements.txt`

## Installation

### 1. Arduino Setup
1. Install Arduino IDE
2. Install required libraries through Library Manager
3. Open `arduino/temperature_control.ino`
4. Select Arduino Mega 2560 as board
5. Upload the sketch

### 2. Server Setup
```bash
# Navigate to server directory
cd temperature_control/server

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the server
python main.py
```

### 3. Hardware Configuration
1. Connect all components according to wiring diagram
2. Power on the system
3. Verify Arduino status LED blinks
4. Access web interface at `http://localhost:8000`

## Usage

### Web Interface
- **Dashboard**: Real-time temperature monitoring for all 6 sensors
- **Control Panel**: Set target temperatures and control fans/hot plates
- **Temperature Trends**: Live chart showing temperature history
- **System Status**: Connection status and error monitoring

### API Endpoints
- `GET /api/status` - Get current system status
- `POST /api/temperature/set` - Set target temperature
- `POST /api/fan/set` - Set fan speed (0-255)
- `POST /api/hotplate/{id}/toggle` - Toggle hot plate on/off
- `GET /api/sensors` - Get all sensor data
- `WebSocket /ws/status` - Real-time status updates

### Control Examples
```python
# Set hot plate 1 target temperature to 75°C
import requests
requests.post('http://localhost:8000/api/temperature/set', 
              json={'sensor': 0, 'target': 75.0})

# Set fan 2 speed to 128 (50%)
requests.post('http://localhost:8000/api/fan/set', 
              json={'fan': 1, 'speed': 128})

# Turn on hot plate 2
requests.post('http://localhost:8000/api/hotplate/1/toggle', 
              json=True)
```

## Configuration

### Arduino Settings
- **Temperature Range**: 0-80°C (configurable in code)
- **Update Interval**: 2 seconds (configurable)
- **PID Parameters**: kp=2.0, ki=0.5, kd=1.0 (tunable)

### Server Settings
- **Serial Port**: `/dev/ttyUSB0` (Linux) or `COM3` (Windows)
- **Baud Rate**: 115200
- **Web Server Port**: 8000

## Safety Features

### Built-in Protections
- **Over-temperature Protection**: Automatic shutdown at 80°C
- **Watchdog Timer**: System reset on unresponsive state
- **Connection Monitoring**: Automatic reconnection to Arduino
- **Error Handling**: Graceful degradation on sensor failures

### Recommended Safety Practices
1. Always monitor system during operation
2. Install physical emergency stop button
3. Use temperature-rated wiring for hot plates
4. Provide adequate ventilation for hot plates
5. Regularly inspect connections and components

## Troubleshooting

### Common Issues

**Arduino not responding:**
- Check serial port configuration in `arduino_comm.py`
- Verify Arduino is powered and connected
- Check baud rate matches Arduino sketch (115200)

**Temperature sensors showing -999:**
- Check DS18B20 wiring and pull-up resistor
- Verify OneWire bus connections
- Check for address conflicts

**Fans not responding:**
- Verify MOSFET connections
- Check 24V power supply
- Verify PWM pin assignments

**Hot plates not working:**
- Check SSR relay connections
- Verify hot plate power supply
- Check control pin assignments

**Web interface not loading:**
- Verify FastAPI server is running
- Check firewall settings
- Verify port 8000 is accessible

### Debug Mode
Enable debug logging by modifying `main.py`:
```python
logging.basicConfig(level=logging.DEBUG)
```

## Development

### Adding New Features
1. **New Sensors**: Update `NUM_SENSORS` and pin assignments
2. **Additional Outputs**: Modify pin definitions and control logic
3. **Custom Control**: Implement in `updateControl()` function
4. **Web Interface**: Modify HTML in `main.py` or create separate frontend

### Testing
- Use Arduino Serial Monitor for basic testing
- Test API endpoints with curl or Postman
- Verify WebSocket connection with browser dev tools

## License

This project is provided as-is for educational and research purposes. Use at your own risk and ensure proper safety measures are in place.

## Support

For technical support or questions:
1. Check the troubleshooting section
2. Review the Arduino serial output for errors
3. Verify all hardware connections
4. Test individual components separately

---

**Version**: 1.0.0  
**Last Updated**: 2025-02-25  
**Compatible Hardware**: Arduino Mega 2560, DS18B20, SSR-40DA, IRF540
