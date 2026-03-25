#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simple camera test script
"""

import tempfile
import os
import sys
import time
from camera_acquisition import capture_camera_image, get_camera_status, initialize_camera_system

def main():
    """Run camera tests with real Pylon SDK"""
    # Add current directory to path
    sys.path.insert(0, '.')
    
    # Create test directory
    test_dir = tempfile.mkdtemp()
    camera_images_folder = os.path.join(test_dir, 'camera_images')
    os.makedirs(camera_images_folder, exist_ok=True)
    
    try:
        print('=== Camera System Test (Real Pylon SDK) ===')
        
        # Test 1: Initialize camera system
        print('1. Testing camera system initialization...')
        success = initialize_camera_system(camera_images_folder)
        print(f'   Initialization: {"SUCCESS" if success else "FAILED"}')
        
        # Test 2: Get camera status
        print('2. Testing camera status...')
        status = get_camera_status(camera_images_folder)
        print(f'   Camera Status: {status}')
        print(f'   Status check: {"SUCCESS" if status else "FAILED"}')
        
        # Test 3: Multiple captures
        print('3. Testing multiple captures...')
        filenames = []
        start_time = time.time()
        
        for i in range(3):
            filename = capture_camera_image(camera_images_folder)
            if filename:
                filenames.append(filename)
                print(f'   Capture {i+1}: {filename}')
                # Verify file exists
                expected_path = os.path.join(camera_images_folder, filename)
                if os.path.exists(expected_path):
                    file_size = os.path.getsize(expected_path)
                    print(f'     File size: {file_size} bytes')
                else:
                    print(f'     File not found')
            else:
                print(f'   Capture {i+1}: FAILED')
        
        elapsed = time.time() - start_time
        if len(filenames) > 0:
            print(f'   Captured {len(filenames)} images in {elapsed:.2f} seconds')
            print(f'   Average time: {elapsed/len(filenames):.3f} seconds per image')
        else:
            print('   No images captured')
        
        # Test 4: Verify unique filenames
        if len(filenames) > 0:
            print('4. Testing filename uniqueness...')
            unique_filenames = set(filenames)
            if len(unique_filenames) == len(filenames):
                print('   All filenames are unique')
            else:
                print('   Duplicate filenames found')
        
        print('=== Test Summary ===')
        print('Camera system test completed')
        print(f'Images captured: {len(filenames)}')
        print('Real Pylon SDK mode active')
        
    except Exception as e:
        print(f'Error during testing: {e}')

if __name__ == '__main__':
    main()
