import sys
import os

# Add current directory to Python path for module imports
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

import serial
import json
import asyncio
import logging
from typing import Optional, Dict, Any
from models import ArduinoCommand, ArduinoResponse, SystemStatus, DeviceStatus
from constants import (
    ARDUINO_DEFAULT_BAUDRATE,
    ARDUINO_COM_PORT_START,
    ARDUINO_COM_PORT_END,
    ARDUINO_DEFAULT_COM_PORT,
    ARDUINO_LINUX_PORT,
    ARDUINO_TIMEOUT,
    ARDUINO_WRITE_TIMEOUT,
    ARDUINO_INIT_DELAY,
    ARDUINO_READ_TIMEOUT,
    ARDUINO_READ_SIZE_LIMIT,
    ResponseStatus
)

logger = logging.getLogger(__name__)

class ArduinoCommunicator:
    def __init__(self, port: str = None, baudrate: int = ARDUINO_DEFAULT_BAUDRATE):
        # Try to load configuration from config file first
        self.port = self._load_config_port() or port
        self.baudrate = baudrate
        self.serial_conn: Optional[serial.Serial] = None
        self.is_connected = False
        self._lock = asyncio.Lock()
        
        # Auto-detect port based on OS if still not specified
        if self.port is None:
            import platform
            if platform.system() == 'Windows':
                # Default to COM4 for Windows as requested
                for i in range(ARDUINO_COM_PORT_START, ARDUINO_COM_PORT_END):
                    port_name = f'COM{i}'
                    try:
                        serial.Serial(port=port_name, baudrate=self.baudrate).close()
                        self.port = port_name
                        break
                    except serial.SerialException:
                        pass
                else:
                    self.port = ARDUINO_DEFAULT_COM_PORT
            else:
                self.port = ARDUINO_LINUX_PORT
    
    def _load_config_port(self) -> Optional[str]:
        """Load Arduino port from configuration file"""
        try:
            config_file = os.path.join(os.path.dirname(__file__), 'arduino_config.py')
            if os.path.exists(config_file):
                # Read the config file and extract ARDUINO_PORT
                with open(config_file, 'r') as f:
                    content = f.read()
                    for line in content.split('\n'):
                        if line.strip().startswith('ARDUINO_PORT ='):
                            port_value = line.split('=')[1].strip().strip('"\'')
                            return port_value
        except Exception as e:
            logger.warning(f"Failed to load Arduino config: {e}")
        return None
        
    def _command_to_scpi(self, command) -> str:
        """Convert an ArduinoCommand or dict into an SCPI command string."""
        payload = None
        if hasattr(command, 'dict'):
            payload = command.dict(exclude_none=True)
        elif isinstance(command, dict):
            payload = command
        elif isinstance(command, str):
            return command.strip()
        else:
            return ""
        
        if not payload:
            return ""
        
        cmd = payload.get('cmd', '')
        if cmd == 'get_status':
            return "SYST:STAT?"
        if cmd == 'ping':
            return "*IDN?"
        if cmd == 'set_temp':
            return f"SOUR:TEMP {payload.get('sensor')},{payload.get('target')}"
        if cmd == 'set_fan':
            return f"SOUR:FAN {payload.get('fan')},{payload.get('speed')}"
        if cmd == 'toggle_hotplate':
            state = 1 if payload.get('state') else 0
            return f"OUTP:HOTPL {payload.get('plate')},{state}"
        if cmd == 'apply_settings':
            settings_payload = {k: v for k, v in payload.items() if k != 'cmd'}
            return f"CONF:SET '{json.dumps(settings_payload)}'"
        
        return ""
    
    async def connect(self) -> bool:
        """Connect to Arduino via serial port"""
        try:
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=ARDUINO_TIMEOUT,
                write_timeout=ARDUINO_WRITE_TIMEOUT
            )
            self.is_connected = True
            await asyncio.sleep(ARDUINO_INIT_DELAY)
            
            # Clear any initial data
            self.serial_conn.reset_input_buffer()
            self.serial_conn.reset_output_buffer()
            
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Arduino: {e}")
            self.is_connected = False
            return False
    
    async def disconnect(self):
        """Disconnect from Arduino"""
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
            self.is_connected = False
    
    async def send_command(self, command) -> ArduinoResponse:
        """Send command to Arduino and return response"""
        import time
        async with self._lock:
            total_start = time.time()
            
            # Check connection before sending
            if not self.is_connected or not self.serial_conn:
                logger.warning("Arduino not connected, attempting to reconnect...")
                reconnect_start = time.time()
                await self.connect()
                logger.info(f"Reconnect took {time.time() - reconnect_start:.3f}s")
                
                if not self.is_connected:
                    return ArduinoResponse(
                        status=ResponseStatus.ERROR,
                        msg="Not connected to Arduino"
                    )
            
            try:
                # Convert command to SCPI string and send
                cmd_start = time.time()
                cmd_str = self._command_to_scpi(command)
                
                # Clear any pending input first
                self.serial_conn.reset_input_buffer()
                
                # Send command
                self.serial_conn.write((cmd_str + '\n').encode())
                self.serial_conn.flush()
                
                # Wait for response
                response_line = await self._read_line()
                
                if response_line:
                    try:
                        response_data = json.loads(response_line)
                        
                        # Check if this is an Arduino error message (has type field)
                        if isinstance(response_data, dict) and 'type' in response_data:
                            if response_data['type'] == 'error':
                                # Arduino sensor error - log it but don't disconnect
                                logger.warning(f"Arduino sensor error: {response_data}")
                                return ArduinoResponse(
                                    status=ResponseStatus.ERROR,
                                    msg=f"Arduino error: {response_data.get('message', 'Unknown error')}"
                                )
                            elif response_data['type'] == 'safety':
                                # Arduino safety event - log it but don't disconnect
                                logger.warning(f"Arduino safety event: {response_data}")
                                return ArduinoResponse(
                                    status=ResponseStatus.OK,  # Safety events are not errors, they're notifications
                                    msg=f"Safety event: {response_data.get('event', 'Unknown event')}"
                                )
                            elif response_data['type'] == 'info':
                                # Arduino info message - log it but don't disconnect
                                logger.info(f"Arduino info: {response_data}")
                                # Return ok status for info messages (they're not errors)
                                return ArduinoResponse(
                                    status=ResponseStatus.OK,
                                    msg=f"Info: {response_data.get('message', 'Info message')}"
                                )
                        
                        # Try to parse as ArduinoResponse
                        return ArduinoResponse(**response_data)
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON decode error: {e}")
                        logger.error(f"Raw response: '{response_line}'")
                        
                        # Try reading additional lines to find valid JSON (up to 3 attempts)
                        for attempt in range(3):
                            next_line = await self._read_line(timeout=2.0)
                            if next_line:
                                try:
                                    response_data = json.loads(next_line)
                                    
                                    # Check if this is an Arduino error message
                                    if isinstance(response_data, dict) and 'type' in response_data:
                                        if response_data['type'] == 'error':
                                            logger.warning(f"Arduino sensor error: {response_data}")
                                            return ArduinoResponse(
                                                status=ResponseStatus.ERROR,
                                                msg=f"Arduino error: {response_data.get('message', 'Unknown error')}"
                                            )
                                        elif response_data['type'] == 'safety':
                                            logger.warning(f"Arduino safety event: {response_data}")
                                            return ArduinoResponse(
                                                status=ResponseStatus.OK,
                                                msg=f"Safety event: {response_data.get('event', 'Unknown event')}"
                                            )
                                        elif response_data['type'] == 'info':
                                            logger.info(f"Arduino info: {response_data}")
                                            return ArduinoResponse(
                                                status=ResponseStatus.OK,
                                                msg=f"Info: {response_data.get('message', 'Info message')}"
                                            )
                                    
                                    return ArduinoResponse(**response_data)
                                except json.JSONDecodeError:
                                    continue
                            else:
                                continue
                        
                        # Check if this is a sensor error message (not a connection issue)
                        if 'disconnected' in response_line.lower() or 'sensor' in response_line.lower():
                            # Sensor error - do not disconnect, just return error
                            logger.warning("Sensor error detected, returning error without disconnecting")
                            return ArduinoResponse(
                                status=ResponseStatus.ERROR,
                                msg=response_line
                            )
                        
                        # Connection might be unstable, mark as disconnected
                        logger.warning("Connection appears unstable, disconnecting...")
                        await self.disconnect()
                        
                        return ArduinoResponse(
                            status=ResponseStatus.ERROR,
                            msg=f"JSON decode error: {e}"
                        )
                else:
                    logger.warning("No response from Arduino")
                    # No response might mean connection lost
                    await self.disconnect()
                    return ArduinoResponse(
                        status=ResponseStatus.ERROR,
                        msg="No response from Arduino"
                    )
                    
            except Exception as e:
                logger.error(f"Error communicating with Arduino: {e}")
                # Mark as disconnected on any communication error
                await self.disconnect()
                return ArduinoResponse(
                    status=ResponseStatus.ERROR,
                    msg=f"Communication error: {str(e)}"
                )
    
    async def _read_line(self, timeout: float = ARDUINO_READ_TIMEOUT) -> Optional[str]:
        """Read a line from serial port with timeout - hybrid batch/char reading"""
        import time
        if not self.serial_conn:
            return None
            
        buffer = ""
        start_time = asyncio.get_event_loop().time()
        loop_start = time.time()
        
        while (asyncio.get_event_loop().time() - start_time) < timeout:
            # Read all available bytes at once (batch reading)
            if self.serial_conn.in_waiting > 0:
                try:
                    bytes_available = self.serial_conn.in_waiting
                    # Limit read size to avoid blocking
                    read_size = min(bytes_available, ARDUINO_READ_SIZE_LIMIT)
                    chunk = self.serial_conn.read(read_size)
                    
                    if chunk:
                        chunk_str = chunk.decode('utf-8', errors='ignore')
                        buffer += chunk_str
                        
                        # Check for newline in the buffer
                        if '\n' in buffer:
                            # Extract the first complete line
                            lines = buffer.split('\n', 1)
                            result = lines[0].strip()
                            
                            if not result:
                                logger.warning("Arduino sent empty response")
                                return None
                            
                            return result
                        else:
                            # No newline yet, buffer the data and continue waiting
                            await asyncio.sleep(0.001)
                except UnicodeDecodeError as e:
                    logger.warning(f"Unicode decode error: {e}")
                    continue
            else:
                # No data available, short sleep
                await asyncio.sleep(0.001)
        
        return None
        
    async def get_status(self) -> ArduinoResponse:
        """Get current system status from Arduino"""
        command = ArduinoCommand(cmd="get_status")
        return await self.send_command(command)
    
    async def ping(self) -> ArduinoResponse:
        """Ping Arduino to test basic connectivity"""
        command = ArduinoCommand(cmd="ping")
        return await self.send_command(command)
    
    async def set_temperature(self, sensor: int, target: float) -> ArduinoResponse:
        """Set target temperature for hot plate"""
        command = ArduinoCommand(cmd="set_temp", sensor=sensor, target=target)
        return await self.send_command(command)
    
    async def set_fan_speed(self, fan: int, speed: int) -> ArduinoResponse:
        """Set fan speed (0-255)"""
        command = ArduinoCommand(cmd="set_fan", fan=fan, speed=speed)
        return await self.send_command(command)
    
    async def toggle_hot_plate(self, plate: int, state: bool) -> ArduinoResponse:
        """Toggle hot plate on/off"""
        command = ArduinoCommand(cmd="toggle_hotplate", plate=plate, state=state)
        return await self.send_command(command)
    
    async def monitor_connection(self):
        """Monitor Arduino connection and reconnect if needed"""
        consecutive_failures = 0
        max_failures = 3
        
        while True:
            try:
                if self.is_connected and self.serial_conn:
                    # Send status command to check connection
                    response = await self.get_status()
                    
                    if response.status == "ok":
                        consecutive_failures = 0  # Reset on success
                    else:
                        consecutive_failures += 1
                        logger.warning(f"Arduino communication error {consecutive_failures}/{max_failures}: {response.msg}")
                        
                        if consecutive_failures >= max_failures:
                            logger.warning("Too many consecutive failures, forcing reconnect")
                            await self.disconnect()
                            await asyncio.sleep(2)
                            await self.connect()
                            consecutive_failures = 0
                else:
                    # Try to reconnect
                    await self.connect()
                    if self.is_connected:
                        consecutive_failures = 0
                    else:
                        consecutive_failures += 1
                        logger.warning(f"Reconnection failed {consecutive_failures}/{max_failures}")
                        
            except Exception as e:
                consecutive_failures += 1
                logger.error(f"Connection monitoring error {consecutive_failures}/{max_failures}: {e}")
                await self.disconnect()
            
            await asyncio.sleep(5)  # Check every 5 seconds (more frequent)

async def apply_settings_to_arduino(arduino_comm: ArduinoCommunicator):
    """Apply settings from configuration file to Arduino"""
    from utils import load_configuration
    settings = load_configuration()
    try:
        # Send apply_settings command to Arduino
        command = {
            "cmd": "apply_settings",
            "target_temperatures": settings.get("target_temperatures", [80, 80]),
            "safety_temperature": settings.get("safety_temperature", 120),
            "pid_parameters": settings.get("pid_parameters", {
                "hotplate_0": {"kp": 2.0, "ki": 0.5, "kd": 1.0},
                "hotplate_1": {"kp": 2.0, "ki": 0.5, "kd": 1.0}
            }),
            "fan_start_behaviour": settings.get("fan_start_behaviour", "full_speed"),
            "polling_interval": settings.get("polling_interval", 1),
            "ambient_polling_interval": settings.get("ambient_polling_interval", 10),
            "debug_enabled": settings.get("debug_enabled", False)
        }
        
        response = await arduino_comm.send_command(command)
        if response.status == "ok":
            logger.info("Settings applied to Arduino successfully")
        else:
            logger.warning(f"Failed to apply settings to Arduino: {response.msg}")
    except FileNotFoundError:
        logger.warning("Configuration file not found, using default values")
    except Exception as e:
        logger.error(f"Error applying settings to Arduino: {e}")

# Global Arduino communicator instance
arduino_comm = ArduinoCommunicator()
