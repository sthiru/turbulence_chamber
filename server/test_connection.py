#!/usr/bin/env python3
"""
Test script to debug WebSocket connection issues
"""

import asyncio
import websockets
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_websocket_connection():
    """Test WebSocket connection to the server"""
    uri = "ws://localhost:8000/ws/status"
    
    try:
        logger.info(f"Attempting to connect to {uri}...")
        async with websockets.connect(uri) as websocket:
            logger.info("WebSocket connection established!")
            
            # Listen for messages
            message_count = 0
            while message_count < 5:  # Listen for 5 messages
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                    data = json.loads(message)
                    logger.info(f"Received message {message_count + 1}: {data}")
                    message_count += 1
                except asyncio.TimeoutError:
                    logger.warning("Timeout waiting for message")
                    break
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON received: {e}")
                    break
                    
    except Exception as e:
        logger.error(f"WebSocket connection failed: {e}")
        return False
    
    return True

async def test_api_endpoints():
    """Test API endpoints"""
    import aiohttp
    
    base_url = "http://localhost:8000"
    
    try:
        async with aiohttp.ClientSession() as session:
            # Test root endpoint
            async with session.get(f"{base_url}/") as response:
                if response.status == 200:
                    logger.info("Root endpoint working")
                else:
                    logger.error(f"Root endpoint failed: {response.status}")
            
            # Test status endpoint
            async with session.get(f"{base_url}/api/status") as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"Status endpoint working: {data}")
                else:
                    logger.error(f"Status endpoint failed: {response.status}")
                    
    except Exception as e:
        logger.error(f"API test failed: {e}")

if __name__ == "__main__":
    print("Testing Temperature Control System Server...")
    print("=" * 50)
    
    # Test API endpoints first
    print("\n1. Testing API endpoints...")
    asyncio.run(test_api_endpoints())
    
    # Test WebSocket connection
    print("\n2. Testing WebSocket connection...")
    success = asyncio.run(test_websocket_connection())
    
    if success:
        print("\n✅ All tests passed!")
    else:
        print("\n❌ Some tests failed. Check the server logs.")
        print("\nTroubleshooting steps:")
        print("1. Make sure the server is running: python main.py")
        print("2. Check if port 8000 is available")
        print("3. Verify Arduino connection (if applicable)")
        print("4. Check server logs for detailed error messages")
