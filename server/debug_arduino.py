#!/usr/bin/env python3
"""
Arduino Communication Debug Script
Test direct Arduino communication to identify the issue
"""

import asyncio
import sys
import os

# Add the server directory to the path
sys.path.append(os.path.dirname(__file__))

from arduino_comm import ArduinoCommunicator
import logging

# Enable detailed logging
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_arduino_communication():
    """Test Arduino communication step by step"""
    
    print("Arduino Communication Debug")
    print("=" * 40)
    
    # Test 1: Create communicator
    print("\n1. Creating Arduino communicator...")
    arduino_comm = ArduinoCommunicator(port='COM4')
    print(f"   Port: {arduino_comm.port}")
    print(f"   Baudrate: {arduino_comm.baudrate}")
    
    # Test 2: Connect to Arduino
    print("\n2. Connecting to Arduino...")
    try:
        success = await arduino_comm.connect()
        print(f"   Connection result: {success}")
        print(f"   Is connected: {arduino_comm.is_connected}")
        
        if not success:
            print("❌ Failed to connect to Arduino")
            return
            
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return
    
    # Test 3: Send get_status command
    print("\n3. Testing get_status command...")
    try:
        response = await arduino_comm.get_status()
        print(f"   Response status: {response.status}")
        print(f"   Response message: {response.msg}")
        
        if response.data:
            print(f"   Response data: {response.data}")
        else:
            print("   No response data received")
            
    except Exception as e:
        print(f"❌ get_status error: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 4: Test raw communication
    print("\n4. Testing raw serial communication...")
    try:
        if arduino_comm.serial_conn and arduino_comm.serial_conn.is_open:
            # Clear buffers
            arduino_comm.serial_conn.reset_input_buffer()
            arduino_comm.serial_conn.reset_output_buffer()
            
            # Send command directly
            import json
            command = {"cmd": "get_status"}
            cmd_json = json.dumps(command)
            
            print(f"   Sending: {cmd_json}")
            arduino_comm.serial_conn.write((cmd_json + '\n').encode())
            arduino_comm.serial_conn.flush()
            
            # Read response
            response_line = ""
            import time
            start_time = time.time()
            
            while time.time() - start_time < 3.0:  # 3 second timeout
                if arduino_comm.serial_conn.in_waiting > 0:
                    char = arduino_comm.serial_conn.read(1).decode('utf-8', errors='ignore')
                    response_line += char
                    if char == '\n':
                        break
                await asyncio.sleep(0.01)
            
            response_line = response_line.strip()
            print(f"   Raw response: {response_line}")
            
            if response_line:
                try:
                    response_data = json.loads(response_line)
                    print(f"   Parsed response: {response_data}")
                except json.JSONDecodeError as e:
                    print(f"   JSON decode error: {e}")
            else:
                print("   No response received")
                
    except Exception as e:
        print(f"❌ Raw communication error: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 5: Disconnect
    print("\n5. Disconnecting...")
    try:
        await arduino_comm.disconnect()
        print("   Disconnected successfully")
    except Exception as e:
        print(f"❌ Disconnect error: {e}")
    
    print("\n✅ Debug completed!")

if __name__ == "__main__":
    asyncio.run(test_arduino_communication())
