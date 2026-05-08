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

logger = logging.getLogger(__name__)

class ArduinoCommunicator:
    def __init__(self, port: str = None, baudrate: int = 250000):
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
                for i in range(4, 10):
                    port_name = f'COM{i}'
                    try:
                        serial.Serial(port=port_name, baudrate=self.baudrate).close()
                        self.port = port_name
                        break
                    except serial.SerialException:
                        pass
                else:
                    self.port = 'COM4'
            else:
                self.port = '/dev/ttyACM0'  # Linux
    
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
                            logger.debug(f"Loaded Arduino port from config: {port_value}")
                            return port_value
        except Exception as e:
            logger.warning(f"Failed to load Arduino config: {e}")
        return None
        
    async def connect(self) -> bool:
        """Connect to Arduino via serial port"""
        try:
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=2.0,
                write_timeout=2.0
            )
            self.is_connected = True
            logger.debug(f"Connected to Arduino on {self.port}")
            logger.debug("Waiting for Arduino to initialize...")
            await asyncio.sleep(3)  # Increased from 2 to 3 seconds
            
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
            logger.debug("Disconnected from Arduino")
    
    async def send_command(self, command: ArduinoCommand) -> ArduinoResponse:
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
                        status="error",
                        msg="Not connected to Arduino"
                    )
            
            try:
                # Convert command to JSON and send
                cmd_start = time.time()
                cmd_json = json.dumps(command.dict(exclude_none=True))
                
                # Clear any pending input first
                self.serial_conn.reset_input_buffer()
                
                # Send command
                self.serial_conn.write((cmd_json + '\n').encode())
                self.serial_conn.flush()
                logger.debug(f"Command sent to Arduino on {self.port}, took {time.time() - cmd_start:.3f}s")
                
                # Check if data was actually written
                bytes_written = self.serial_conn.out_waiting
                logger.debug(f"Bytes waiting to be written: {bytes_written}")
                
                # Wait for response
                read_start = time.time()
                response_line = await self._read_line()
                read_time = time.time() - read_start
                logger.debug(f"Read line took {read_time:.3f}s, Raw response from Arduino: {response_line}")
                
                logger.info(f"Total command time: {time.time() - total_start:.3f}s (read: {read_time:.3f}s)")
                
                if response_line:
                    try:
                        response_data = json.loads(response_line)
                        return ArduinoResponse(**response_data)
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON decode error: {e}")
                        logger.error(f"Raw response: '{response_line}'")
                        logger.error(f"Response length: {len(response_line)}")
                        logger.error(f"Response bytes: {[ord(c) for c in response_line]}")
                        
                        # Check if this is a sensor error message (not a connection issue)
                        if 'disconnected' in response_line.lower() or 'sensor' in response_line.lower():
                            # Sensor error - do not disconnect, just return error
                            logger.warning("Sensor error detected, returning error without disconnecting")
                            return ArduinoResponse(
                                status="error",
                                msg=response_line
                            )
                        
                        # Connection might be unstable, mark as disconnected
                        logger.warning("Connection appears unstable, disconnecting...")
                        await self.disconnect()
                        
                        return ArduinoResponse(
                            status="error",
                            msg=f"JSON decode error: {e}"
                        )
                else:
                    logger.warning("No response from Arduino")
                    # No response might mean connection lost
                    await self.disconnect()
                    return ArduinoResponse(
                        status="error",
                        msg="No response from Arduino"
                    )
                    
            except Exception as e:
                logger.error(f"Error communicating with Arduino: {e}")
                # Mark as disconnected on any communication error
                await self.disconnect()
                return ArduinoResponse(
                    status="error",
                    msg=f"Communication error: {str(e)}"
                )
    
    async def _read_line(self, timeout: float = 5.0) -> Optional[str]:
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
                    read_size = min(bytes_available, 1024)
                    chunk = self.serial_conn.read(read_size)
                    
                    if chunk:
                        chunk_str = chunk.decode('utf-8', errors='ignore')
                        buffer += chunk_str
                        
                        # Check for newline in the buffer
                        if '\n' in buffer:
                            # Extract the first complete line
                            lines = buffer.split('\n', 1)
                            result = lines[0].strip()
                            
                            total_time = time.time() - loop_start
                            logger.info(f"Read line completed in {total_time:.3f}s, {len(result)} chars, buffer size: {len(buffer)}")
                            
                            if not result:
                                logger.warning("Arduino sent empty response")
                                return None
                            
                            return result
                        else:
                            # No newline yet, buffer the data and continue waiting
                            logger.debug(f"Buffered {len(chunk)} bytes (total buffer: {len(buffer)})")
                            await asyncio.sleep(0.001)
                except UnicodeDecodeError as e:
                    logger.warning(f"Unicode decode error: {e}")
                    continue
            else:
                # No data available, short sleep
                await asyncio.sleep(0.001)
        
        total_time = time.time() - loop_start
        logger.warning(f"Read line timeout after {total_time:.3f}s, buffer content: {buffer[:100]}")
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
                        logger.debug("Arduino connection healthy")
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
                    logger.debug("Arduino disconnected, attempting to reconnect...")
                    await self.connect()
                    if self.is_connected:
                        consecutive_failures = 0
                        logger.debug("Arduino reconnected successfully")
                    else:
                        consecutive_failures += 1
                        logger.warning(f"Reconnection failed {consecutive_failures}/{max_failures}")
                        
            except Exception as e:
                consecutive_failures += 1
                logger.error(f"Connection monitoring error {consecutive_failures}/{max_failures}: {e}")
                await self.disconnect()
            
            await asyncio.sleep(5)  # Check every 5 seconds (more frequent)

# Global Arduino communicator instance
arduino_comm = ArduinoCommunicator()
