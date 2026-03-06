#!/usr/bin/env python3
"""
WebSocket Test Script
Test WebSocket connection and data reception from the server
"""

import asyncio
import websockets
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_websocket_connection():
    """Test WebSocket connection and data reception"""
    uri = "ws://localhost:8000/ws/status"
    
    try:
        logger.info(f"Connecting to WebSocket at {uri}...")
        async with websockets.connect(uri) as websocket:
            logger.info("✅ WebSocket connected successfully!")
            
            message_count = 0
            last_message_time = asyncio.get_event_loop().time()
            
            # Listen for messages for 30 seconds
            while message_count < 10:  # Listen for 10 messages or 30 seconds
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    current_time = asyncio.get_event_loop().time()
                    time_diff = current_time - last_message_time
                    
                    try:
                        data = json.loads(message)
                        logger.info(f"📨 Message {message_count + 1} (after {time_diff:.1f}s): {json.dumps(data, indent=2)}")
                        
                        # Check if message has expected data
                        if 'device_status' in data:
                            logger.info(f"   Device status: {data['device_status']}")
                        if 'temperatures' in data:
                            logger.info(f"   Temperatures: {data['temperatures']}")
                        if 'arduino_port' in data:
                            logger.info(f"   Arduino port: {data['arduino_port']}")
                        
                        message_count += 1
                        last_message_time = current_time
                        
                    except json.JSONDecodeError as e:
                        logger.error(f"❌ Invalid JSON received: {e}")
                        logger.error(f"   Raw message: {message}")
                        
                except asyncio.TimeoutError:
                    logger.warning("⏰ Timeout waiting for message")
                    break
                    
            logger.info(f"✅ Received {message_count} messages successfully")
            
    except websockets.exceptions.ConnectionClosed as e:
        logger.error(f"❌ WebSocket connection closed: {e}")
    except websockets.exceptions.ConnectionRefused:
        logger.error("❌ Connection refused - is the server running?")
    except Exception as e:
        logger.error(f"❌ WebSocket error: {e}")

async def test_api_endpoints():
    """Test API endpoints to verify server is working"""
    import aiohttp
    
    base_url = "http://localhost:8000"
    
    try:
        async with aiohttp.ClientSession() as session:
            # Test root endpoint
            async with session.get(f"{base_url}/") as response:
                if response.status == 200:
                    logger.info("✅ Root endpoint working")
                else:
                    logger.error(f"❌ Root endpoint failed: {response.status}")
            
            # Test status endpoint
            async with session.get(f"{base_url}/api/status") as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"✅ Status endpoint working: {data}")
                else:
                    logger.error(f"❌ Status endpoint failed: {response.status}")
                    
            # Test test endpoint
            async with session.get(f"{base_url}/api/test") as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"✅ Test endpoint working: {data}")
                else:
                    logger.error(f"❌ Test endpoint failed: {response.status}")
                    
    except Exception as e:
        logger.error(f"❌ API test failed: {e}")

if __name__ == "__main__":
    print("WebSocket Connection Test")
    print("=" * 40)
    
    # Test API endpoints first
    print("\n1. Testing API endpoints...")
    asyncio.run(test_api_endpoints())
    
    # Test WebSocket connection
    print("\n2. Testing WebSocket connection...")
    asyncio.run(test_websocket_connection())
    
    print("\nTroubleshooting Guide:")
    print("1. Make sure server is running: python main.py")
    print("2. Check server logs for WebSocket connection messages")
    print("3. Verify Arduino is connected and responding")
    print("4. Check browser console for WebSocket errors")
    print("5. Look for 'Starting status broadcasting task' in server logs")
