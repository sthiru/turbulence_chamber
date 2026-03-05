import serial
import json
import asyncio
import logging
from typing import Optional, Dict, Any
from models import ArduinoCommand, ArduinoResponse, SystemStatus, DeviceStatus

logger = logging.getLogger(__name__)

class ArduinoCommunicator:
    def __init__(self, port: str = '/dev/ttyUSB0', baudrate: int = 115200):
        self.port = port
        self.baudrate = baudrate
        self.serial_conn: Optional[serial.Serial] = None
        self.is_connected = False
        self._lock = asyncio.Lock()
        
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
            logger.info(f"Connected to Arduino on {self.port}")
            
            # Wait for Arduino to initialize
            await asyncio.sleep(2)
            
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
            logger.info("Disconnected from Arduino")
    
    async def send_command(self, command: ArduinoCommand) -> ArduinoResponse:
        """Send command to Arduino and get response"""
        async with self._lock:
            if not self.is_connected or not self.serial_conn:
                return ArduinoResponse(
                    status="error",
                    msg="Not connected to Arduino"
                )
            
            try:
                # Convert command to JSON and send
                cmd_json = json.dumps(command.dict(exclude_none=True))
                logger.debug(f"Sending command: {cmd_json}")
                
                self.serial_conn.write((cmd_json + '\n').encode())
                self.serial_conn.flush()
                
                # Wait for response
                response_line = await self._read_line()
                
                if response_line:
                    response_data = json.loads(response_line)
                    return ArduinoResponse(**response_data)
                else:
                    return ArduinoResponse(
                        status="error",
                        msg="No response from Arduino"
                    )
                    
            except Exception as e:
                logger.error(f"Error communicating with Arduino: {e}")
                return ArduinoResponse(
                    status="error",
                    msg=f"Communication error: {str(e)}"
                )
    
    async def _read_line(self, timeout: float = 3.0) -> Optional[str]:
        """Read a line from serial port with timeout"""
        if not self.serial_conn:
            return None
            
        buffer = ""
        start_time = asyncio.get_event_loop().time()
        
        while (asyncio.get_event_loop().time() - start_time) < timeout:
            if self.serial_conn.in_waiting > 0:
                char = self.serial_conn.read(1).decode()
                buffer += char
                
                if char == '\n':
                    return buffer.strip()
            
            await asyncio.sleep(0.01)
        
        logger.warning("Timeout waiting for Arduino response")
        return None
    
    async def get_status(self) -> ArduinoResponse:
        """Get current system status from Arduino"""
        command = ArduinoCommand(cmd="get_status")
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
        while True:
            try:
                if self.is_connected and self.serial_conn:
                    # Send status command to check connection
                    response = await self.get_status()
                    if response.status == "error":
                        logger.warning("Arduino communication error, attempting reconnect")
                        await self.disconnect()
                        await asyncio.sleep(1)
                        await self.connect()
                else:
                    # Try to reconnect
                    await self.connect()
                    
            except Exception as e:
                logger.error(f"Connection monitoring error: {e}")
                await self.disconnect()
            
            await asyncio.sleep(10)  # Check every 10 seconds

# Global Arduino communicator instance
arduino_comm = ArduinoCommunicator()
