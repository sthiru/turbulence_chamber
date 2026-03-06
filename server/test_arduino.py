#!/usr/bin/env python3
"""
Arduino Communication Test Script
Test direct communication with Arduino to debug JSON parsing issues
"""

import serial
import json
import time
import sys

def test_arduino_communication(port='COM4', baudrate=115200):
    """Test direct communication with Arduino"""
    
    try:
        print(f"Connecting to Arduino on {port}...")
        ser = serial.Serial(port, baudrate, timeout=3)
        print("✅ Connected successfully!")
        
        # Wait for Arduino to initialize
        print("Waiting for Arduino to initialize...")
        time.sleep(2)
        
        # Clear buffers
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        
        # Test 1: Simple status command
        print("\n=== Test 1: Get Status Command ===")
        command = {"cmd": "get_status"}
        command_json = json.dumps(command)
        
        print(f"Sending: {command_json}")
        ser.write((command_json + '\n').encode())
        ser.flush()
        
        # Read response
        response = ser.readline().decode().strip()
        print(f"Raw response: {response}")
        
        if response:
            try:
                response_data = json.loads(response)
                print(f"Parsed response: {response_data}")
                
                if response_data.get("status") == "ok":
                    print("✅ Status command successful!")
                else:
                    print(f"❌ Error: {response_data.get('msg', 'Unknown error')}")
            except json.JSONDecodeError as e:
                print(f"❌ JSON decode error: {e}")
        else:
            print("❌ No response received")
        
        # Test 2: Check Arduino startup messages
        print("\n=== Test 2: Check Arduino Startup ===")
        print("Reading any pending messages...")
        while ser.in_waiting > 0:
            line = ser.readline().decode().strip()
            print(f"Arduino says: {line}")
            time.sleep(0.1)
        
        # Test 3: Send malformed JSON to see error handling
        print("\n=== Test 3: Malformed JSON Test ===")
        malformed = '{"cmd": "invalid"'  # Missing closing brace
        print(f"Sending malformed: {malformed}")
        ser.write((malformed + '\n').encode())
        ser.flush()
        
        response = ser.readline().decode().strip()
        print(f"Response to malformed: {response}")
        
        ser.close()
        print("\n✅ Test completed!")
        
    except serial.SerialException as e:
        print(f"❌ Serial error: {e}")
        print("Make sure:")
        print("1. Arduino is connected to the specified port")
        print("2. No other program is using the port")
        print("3. Arduino sketch is uploaded and running")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")

def test_json_format():
    """Test different JSON formats"""
    print("\n=== Testing JSON Formats ===")
    
    formats = [
        '{"cmd": "get_status"}',
        '{"cmd":"get_status"}',
        "{ \"cmd\": \"get_status\" }",
        '{"cmd":"get_status"}\r\n',
        '{"cmd":"get_status"}\n',
    ]
    
    for i, fmt in enumerate(formats, 1):
        print(f"\nFormat {i}: {repr(fmt)}")
        try:
            data = json.loads(fmt)
            print(f"✅ Valid JSON: {data}")
        except json.JSONDecodeError as e:
            print(f"❌ Invalid JSON: {e}")

if __name__ == "__main__":
    print("Arduino Communication Debug Tool")
    print("=" * 40)
    
    # Test JSON formats
    test_json_format()
    
    # Test Arduino communication
    port = 'COM4'  # Change if needed
    if len(sys.argv) > 1:
        port = sys.argv[1]
    
    test_arduino_communication(port)
    
    print("\nTroubleshooting tips:")
    print("1. Check Arduino Serial Monitor for startup messages")
    print("2. Verify baud rate matches (115200)")
    print("3. Make sure Arduino sketch is compiled and uploaded")
    print("4. Check for serial port conflicts")
