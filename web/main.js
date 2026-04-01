// Beta Page JavaScript
// WebSocket connection
let ws = null;
let videoWs = null;
let reconnectInterval = null;
let videoReconnectInterval = null;

// Video streaming variables
let isVideoStreaming = false;
let videoClientId = null;
const currentVideoMode = 'video'; // Always video mode now

// Configuration
const CONFIG = {
    WS_URL: `ws://${window.location.host}/ws/status`,
    VIDEO_WS_URL: `ws://${window.location.host}/ws/video`,
    RECONNECT_DELAY: 3000,
    WARNING_TEMP: 60,
    DANGER_TEMP: 80
};

// Initialize WebSocket connection
function initWebSocket() {
    try {
        ws = new WebSocket(CONFIG.WS_URL);
        
        ws.onopen = function() {
            console.log('WebSocket connected');
            if (reconnectInterval) {
                clearInterval(reconnectInterval);
                reconnectInterval = null;
            }
        };
        
        ws.onmessage = function(event) {
            try {
                const data = JSON.parse(event.data);
                handleWebSocketMessage(data);
            } catch (error) {
                console.error('Error parsing WebSocket data:', error);
            }
        };
        
        ws.onclose = function() {
            console.log('WebSocket disconnected');
            scheduleReconnect();
        };
        
        ws.onerror = function(error) {
            console.error('WebSocket error:', error);
            scheduleReconnect();
        };
        
    } catch (error) {
        console.error('Error initializing WebSocket:', error);
        scheduleReconnect();
    }
}

// Initialize video streaming WebSocket
function initVideoWebSocket() {
    if (!videoClientId) {
        videoClientId = 'client_' + Math.random().toString(36).substr(2, 9);
    }
    
    try {
        const videoWsUrl = `${CONFIG.VIDEO_WS_URL}/${videoClientId}`;
        console.log('Connecting to video streaming WebSocket:', videoWsUrl);
        
        videoWs = new WebSocket(videoWsUrl);
        
        videoWs.onopen = function() {
            console.log('Video streaming WebSocket connected');
            if (videoReconnectInterval) {
                clearInterval(videoReconnectInterval);
                videoReconnectInterval = null;
            }
        };
        
        videoWs.onmessage = function(event) {
            try {
                const data = JSON.parse(event.data);
                handleVideoWebSocketMessage(data);
            } catch (error) {
                console.error('Error parsing video WebSocket data:', error);
            }
        };
        
        videoWs.onclose = function() {
            console.log('Video streaming WebSocket disconnected');
            scheduleVideoReconnect();
        };
        
        videoWs.onerror = function(error) {
            console.error('Video streaming WebSocket error:', error);
            scheduleVideoReconnect();
        };
        
    } catch (error) {
        console.error('Error initializing video WebSocket:', error);
        scheduleVideoReconnect();
    }
}

// Handle video streaming WebSocket messages
function handleVideoWebSocketMessage(data) {
    switch (data.type) {
        case 'stream_status':
            console.log('Video streaming status:', data.status);
            updateVideoStreamStatus(data.status);
            break;
            
        case 'video_frame':
            displayVideoFrame(data.frame);
            break;
            
        case 'stream_response':
            console.log('Stream response:', data);
            if (data.action === 'start' && data.success) {
                isVideoStreaming = true;
            } else if (data.action === 'stop' && data.success) {
                isVideoStreaming = false;
            }
            break;
            
        case 'ping':
            videoWs.send('{"type":"pong"}');
            break;
            
        case 'pong':
            // Ping/pong response received
            break;
            
        default:
            console.log('Unknown video message type:', data.type);
    }
}

// Display video frame in SVG
function displayVideoFrame(frameData) {
    const svgObject = document.querySelector('object[data="/static/main.svg"]');
    let svgDoc = null;
    
    if (svgObject && svgObject.contentDocument) {
        svgDoc = svgObject.contentDocument;
    } else if (svgObject && svgObject.getSVGDocument) {
        svgDoc = svgObject.getSVGDocument();
    }
    
    if (!svgDoc) {
        console.error('SVG document not found for video frame display');
        return;
    }
    
    // Find the video stream element in SVG
    const svgVideoStreamElement = svgDoc.getElementById('svgVideoStream');
    const videoLoadingIndicator = svgDoc.getElementById('videoLoadingIndicator');
    const videoStatusIndicator = svgDoc.getElementById('videoStatusIndicator');
    
    if (svgVideoStreamElement && frameData) {
        // Create data URL from base64 frame data
        const dataUrl = `data:image/jpeg;base64,${frameData}`;
        svgVideoStreamElement.setAttribute('href', dataUrl);
        
        // Hide loading indicator and show streaming status
        if (videoLoadingIndicator) {
            videoLoadingIndicator.style.display = 'none';
        }
        if (videoStatusIndicator) {
            videoStatusIndicator.setAttribute('fill', '#28a745'); // Green for active streaming
        }
    }
}

// Update video streaming status display
function updateVideoStreamStatus(status) {
    isVideoStreaming = status.is_streaming || false;
    
    // Update UI elements based on streaming status
    const videoStatusElement = document.getElementById('video-stream-status');
    if (videoStatusElement) {
        videoStatusElement.textContent = isVideoStreaming ? 'Streaming' : 'Not Streaming';
        videoStatusElement.className = isVideoStreaming ? 'text-success' : 'text-muted';
    }
    
    // Always show video mode
    const cameraModeElement = document.getElementById('camera-mode');
    if (cameraModeElement) {
        cameraModeElement.textContent = 'Live Video';
    }
    
    // Update SVG video status indicator
    const svgObject = document.querySelector('object[data="/static/main.svg"]');
    let svgDoc = null;
    
    if (svgObject && svgObject.contentDocument) {
        svgDoc = svgObject.contentDocument;
    } else if (svgObject && svgObject.getSVGDocument) {
        svgDoc = svgObject.getSVGDocument();
    }
    
    if (svgDoc) {
        const videoStatusIndicator = svgDoc.getElementById('videoStatusIndicator');
        const videoLoadingIndicator = svgDoc.getElementById('videoLoadingIndicator');
        
        if (videoStatusIndicator) {
            if (isVideoStreaming) {
                videoStatusIndicator.setAttribute('fill', '#28a745'); // Green
                if (videoLoadingIndicator) {
                    videoLoadingIndicator.style.display = 'none';
                }
            } else {
                videoStatusIndicator.setAttribute('fill', '#dc3545'); // Red
                if (videoLoadingIndicator) {
                    videoLoadingIndicator.style.display = 'block';
                    videoLoadingIndicator.textContent = 'Waiting for Stream...';
                }
            }
        }
    }
}

// Initialize video display
function initVideoDisplay() {
    const svgObject = document.querySelector('object[data="/static/main.svg"]');
    let svgDoc = null;
    
    if (svgObject && svgObject.contentDocument) {
        svgDoc = svgObject.contentDocument;
    } else if (svgObject && svgObject.getSVGDocument) {
        svgDoc = svgObject.getSVGDocument();
    }
    
    if (svgDoc) {
        const videoLoadingIndicator = svgDoc.getElementById('videoLoadingIndicator');
        const videoStatusIndicator = svgDoc.getElementById('videoStatusIndicator');
        
        if (videoLoadingIndicator) {
            videoLoadingIndicator.textContent = 'Loading Video...';
            videoLoadingIndicator.style.display = 'block';
        }
        
        if (videoStatusIndicator) {
            videoStatusIndicator.setAttribute('fill', '#ffc107'); // Yellow for loading
        }
    }
}

// Schedule reconnection
function scheduleReconnect() {
    if (!reconnectInterval) {
        reconnectInterval = setInterval(() => {
            console.log('Attempting to reconnect...');
            initWebSocket();
        }, CONFIG.RECONNECT_DELAY);
    }
}

// Schedule video reconnection
function scheduleVideoReconnect() {
    if (!videoReconnectInterval) {
        videoReconnectInterval = setInterval(() => {
            console.log('Attempting to reconnect video streaming...');
            initVideoWebSocket();
        }, CONFIG.RECONNECT_DELAY);
    }
}

// Update system ready status display
function updateSystemReadyStatus(systemReady) {
    const statusElement = document.getElementById('connectionStatus');
    console.log('updateSystemReadyStatus called with:', systemReady);
    console.log('Status element found:', statusElement);
    
    if (statusElement) {
        if (systemReady) {
            statusElement.className = 'connection-status connected';
            statusElement.innerHTML = '<i class="fas fa-check-circle"></i> System Ready';
            console.log('Status set to connected');
        } else {
            statusElement.className = 'connection-status disconnected';
            statusElement.innerHTML = '<i class="fas fa-exclamation-circle"></i> System Not Ready';
            console.log('Status set to disconnected');
        }
    } else {
        console.error('Connection status element not found!');
    }
}

// Handle WebSocket messages
function handleWebSocketMessage(data) {
    console.log('WebSocket message received:', data.type, data);
    
    if (data.type === 'system_status') {
        updateSystemStatus(data);
    } else if (data.type === 'historical_data' || data.type === 'current_data') {
        // Update sensor data
        if (data.data && data.data.length > 0) {
            updateSensorData(data.data[data.data.length - 1]);
            
            // Also update system ready status if available in current_data
            const latestData = data.data[data.data.length - 1];
            console.log('Latest data device_status:', latestData.device_status);
            if (latestData.device_status === 'online') {
                updateSystemReadyStatus(true);
            } else {
                updateSystemReadyStatus(false);
            }
        }
    }
}

// Update system status
function updateSystemStatus(data) {
    // Check if elements exist before trying to update them
    const systemReadyElement = document.getElementById('systemReady');
    const arduinoPortElement = document.getElementById('arduinoPort');
    
    if (systemReadyElement) {
        systemReadyElement.textContent = data.system_ready ? 'Yes' : 'No';
    }
    
    if (arduinoPortElement) {
        arduinoPortElement.textContent = data.arduino_port || '--';
    }
    
    // Update connection status to show system ready state
    updateSystemReadyStatus(data.system_ready);
}

// Update system ready status display
function updateSystemReadyStatus(systemReady) {
    const statusElement = document.getElementById('connectionStatus');
    if (systemReady) {
        statusElement.className = 'connection-status connected';
        statusElement.innerHTML = '<i class="fas fa-check-circle"></i> System Ready';
    } else {
        statusElement.className = 'connection-status disconnected';
        statusElement.innerHTML = '<i class="fas fa-exclamation-circle"></i> System Not Ready';
    }
}

// Update sensor data
function updateSensorData(data) {
    // Get the SVG document content
    const svgObject = document.querySelector('object[data="/static/main.svg"]');
    let svgDoc = null;
    
    if (svgObject && svgObject.contentDocument) {
        svgDoc = svgObject.contentDocument;
    } else if (svgObject && svgObject.getSVGDocument) {
        // Fallback for older browsers
        svgDoc = svgObject.getSVGDocument();
    }
    
    if (!svgDoc) {
        console.error('SVG document not found');
        return;
    }
    
    // Update temperatures
    const temperatures = data.temperatures || [];
    temperatures.forEach((temp, index) => {
        const tempElement = svgDoc.getElementById(`temp${index + 1}`);
        const sensorElement = svgDoc.getElementById(`sensor${index + 1}`);
        
        if (tempElement) {
            if (temp < -100) {
                tempElement.textContent = '--°C';
            } else {
                tempElement.textContent = temp.toFixed(1) + '°C';
            }
        }
        
        // Update sensor color based on temperature (SVG elements)
        if (sensorElement && temp >= -100) {
            const circle = sensorElement.querySelector('circle');
            if (circle) {
                circle.classList.remove('sensor-normal', 'sensor-warning', 'sensor-danger');
                
                if (temp >= CONFIG.DANGER_TEMP) {
                    circle.classList.add('sensor-danger');
                } else if (temp >= CONFIG.WARNING_TEMP) {
                    circle.classList.add('sensor-warning');
                } else {
                    circle.classList.add('sensor-normal');
                }
            }
        }
    });
    
    // Update hot plates
    const hotPlateStates = data.hot_plate_states || [];
    hotPlateStates.forEach((state, index) => {
        const hotplateElement = svgDoc.getElementById(`hotplate${index + 1}`);
        const statusElement = document.getElementById(`hotplate${index + 1}Status`);
        
        if (hotplateElement) {
            hotplateElement.classList.remove('hot-plate-on', 'hot-plate-off');
            if (state) {
                hotplateElement.classList.add('hot-plate-on');
            } else {
                hotplateElement.classList.add('hot-plate-off');
            }
        }
        
        if (statusElement) {
            statusElement.textContent = state ? 'ON' : 'OFF';
        }
    });
    
    // Update fans
    const fanSpeeds = data.fan_speeds || [];
    fanSpeeds.forEach((speed, index) => {
        const fanElement = svgDoc.getElementById(`fan${index + 1}`);
        const speedElement = document.getElementById(`fan${index + 1}Speed`);
        
        if (fanElement) {
            // Find the fan blade group within the SVG fan element using SVG document context
            const fanBlade = fanElement.querySelector('.fan-blade');
            
            if (fanBlade) {
                // Remove any existing SVG animations
                const existingAnim = fanBlade.querySelector('animateTransform');
                if (existingAnim) {
                    existingAnim.remove();
                }
                
                if (speed > 0) {
                    // Calculate rotation duration based on PWM speed (0-255)
                    // Higher speed = faster rotation = shorter duration
                    // Map: 255 -> 0.5s (fastest), 1 -> 5s (slowest)
                    const duration = 5.0 - (speed / 255) * 4.5; // 5s to 0.5s
                    
                    // Create SVG animateTransform element
                    const animateTransform = document.createElementNS('http://www.w3.org/2000/svg', 'animateTransform');
                    animateTransform.setAttribute('attributeName', 'transform');
                    animateTransform.setAttribute('type', 'rotate');
                    animateTransform.setAttribute('from', '0 0 0');
                    animateTransform.setAttribute('to', '360 0 0');
                    animateTransform.setAttribute('dur', `${duration}s`);
                    animateTransform.setAttribute('repeatCount', 'indefinite');
                    
                    fanBlade.appendChild(animateTransform);
                    animateTransform.beginElement();
                    
                } else {
                    // Stop animation
                    fanBlade.classList.add('fan-off');
                    fanBlade.style.animation = 'none';
                }
            }
        }
        
        if (speedElement) {
            speedElement.textContent = speed;
        }
    });
    
    // Update camera streaming status
    if (data.camera_status && data.camera_status.is_streaming !== undefined) {
        updateVideoStreamStatus(data.camera_status);
    }
    
    // Update CN² optical
    if (data.cn2_optical !== undefined && data.cn2_optical !== null) {
        const cn2OpticalElement = document.getElementById('cn2OpticalValue');
        if (cn2OpticalElement) {
            const cn2OpticalValue = data.cn2_optical.toExponential(2);
            cn2OpticalElement.textContent = cn2OpticalValue;
        }
    }
    
    // Update CN²
    if (data.cn2 !== undefined && data.cn2 !== null) {
        const cn2Value = data.cn2.toExponential(2);
        const cn2ValueElement = document.getElementById('cn2Value');
        if (cn2ValueElement) {
            cn2ValueElement.textContent = cn2Value;
        }
        
        // Update CN² title in SVG
        const cn2TitleElement = svgDoc.getElementById('cn2TitleValue');
        if (cn2TitleElement) {
            cn2TitleElement.textContent = cn2Value;
        }
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    initWebSocket();
    
    // Wait for SVG to load before initializing controls
    const svgObject = document.querySelector('object[data="/static/main.svg"]');
    if (svgObject) {
        svgObject.addEventListener('load', function() {
            console.log('SVG fully loaded, initializing controls...');
            setTimeout(initFanControls, 100); // Small delay to ensure SVG is ready
        });
        
        // Also try immediately in case SVG is already loaded
        if (svgObject.contentDocument) {
            console.log('SVG already loaded, initializing controls...');
            setTimeout(initFanControls, 100);
        }
    } else {
        console.error('SVG object not found');
    }
    
    initVideoDisplay();
    // Auto-start video streaming
    setTimeout(() => {
        if (videoWs && videoWs.readyState === WebSocket.OPEN) {
            videoWs.send('{"type":"start_stream"}');
        }
    }, 2000);
});

// Initialize fan controls
function initFanControls() {
    const svgObject = document.querySelector('object[data="/static/main.svg"]');
    console.log('SVG object found:', svgObject);
    let svgDoc = null;
    
    if (svgObject && svgObject.contentDocument) {
        svgDoc = svgObject.contentDocument;
        console.log('SVG document found via contentDocument');
    } else if (svgObject && svgObject.getSVGDocument) {
        svgDoc = svgObject.getSVGDocument();
        console.log('SVG document found via getSVGDocument');
    }
    
    if (!svgDoc) {
        console.error('SVG document not found - controls cannot be initialized');
        return;
    }
    
    console.log('SVG document ready, initializing controls...');
    
    // Initialize controls for each fan
    for (let i = 1; i <= 4; i++) {
        initFanControl(svgDoc, i);
    }
    
    // Initialize hot plate controls
    for (let i = 1; i <= 2; i++) {
        initHotPlateControl(svgDoc, i);
    }
}

// Initialize individual fan control
function initFanControl(svgDoc, fanNumber) {
    const controlsGroup = svgDoc.getElementById(`fan${fanNumber}-controls`);
    console.log(`Fan ${fanNumber} controls group found:`, controlsGroup);
    if (!controlsGroup) return;
    
    const sliderElement = svgDoc.getElementById(`fan${fanNumber}-slider`);
    const sliderKnob = svgDoc.getElementById(`fan${fanNumber}-slider-knob`);
    
    console.log(`Fan ${fanNumber} elements - slider:`, sliderElement, 'sliderKnob:', sliderKnob);
    
    let isDragging = false;
    let currentSpeed = 0;
    
    // Slider drag handlers
    if (sliderElement && sliderKnob) {
        console.log(`Fan ${fanNumber} slider elements found, adding drag handlers...`);
        
        sliderKnob.addEventListener('mousedown', function(e) {
            console.log(`Fan ${fanNumber} slider mousedown!`);
            isDragging = true;
            e.preventDefault();
            e.stopPropagation();
        });
        
        document.addEventListener('mousemove', function(e) {
            if (!isDragging) return;
            
            const sliderRect = sliderElement.getBoundingClientRect();
            const svgRect = svgDoc.ownerSVGElement.getBoundingClientRect();
            
            // Calculate relative position
            const relativeY = e.clientY - svgRect.top - (sliderRect.top - svgRect.top);
            const clampedY = Math.max(-20, Math.min(40, relativeY));
            
            // Update knob position
            sliderKnob.setAttribute('cy', clampedY);
            
            // Calculate speed (0-255)
            currentSpeed = Math.round(((40 - clampedY) / 60) * 255);
            
            // Send speed command
            sendFanCommand(fanNumber, currentSpeed);
        });
        
        document.addEventListener('mouseup', function() {
            if (isDragging) {
                console.log(`Fan ${fanNumber} slider drag ended, speed: ${currentSpeed}`);
                isDragging = false;
            }
        });
        
        // Check if element has pointer-events
        const computedStyle = window.getComputedStyle(sliderElement);
        console.log(`Fan ${fanNumber} slider pointer-events:`, computedStyle.pointerEvents);
    } else {
        console.error(`Fan ${fanNumber} slider elements not found!`);
    }
}

// Update switch visual state
function updateSwitchVisual(switchKnob, isOn) {
    if (!switchKnob) return;
    
    if (isOn) {
        switchKnob.setAttribute('cx', '30');
        switchKnob.setAttribute('fill', '#28a745');
        switchKnob.setAttribute('stroke', '#1e7e34');
    } else {
        switchKnob.setAttribute('cx', '10');
        switchKnob.setAttribute('fill', '#fff');
        switchKnob.setAttribute('stroke', '#999');
    }
}

// Send fan command to server
function sendFanCommand(fanNumber, speed) {
    const command = {
        type: 'fan_control',
        fan: fanNumber,
        speed: speed
    };
    
    // Send via WebSocket if connected
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(command));
    }
}

// Initialize individual hot plate control
function initHotPlateControl(svgDoc, plateNumber) {
    const switchElement = svgDoc.getElementById(`hotplate${plateNumber}-switch`);
    const switchKnob = svgDoc.getElementById(`hotplate${plateNumber}-switch-knob`);
    const hotPlateElement = svgDoc.getElementById(`hotplate${plateNumber}`);
    
    console.log(`Hot plate ${plateNumber} elements - switch:`, switchElement, 'knob:', switchKnob, 'plate:', hotPlateElement);
    
    let isOn = false;
    
    // Switch click handler
    if (switchElement) {
        switchElement.addEventListener('click', function() {
            console.log(`Hot plate ${plateNumber} switch clicked!`);
            isOn = !isOn;
            updateHotPlateSwitchVisual(switchKnob, isOn);
            updateHotPlateVisual(hotPlateElement, isOn);
            
            // Send hot plate control command
            sendHotPlateCommand(plateNumber, isOn);
        });
    }
}

// Update hot plate switch visual state
function updateHotPlateSwitchVisual(switchKnob, isOn) {
    if (!switchKnob) return;
    
    if (isOn) {
        switchKnob.setAttribute('cx', '30');
        switchKnob.setAttribute('fill', '#28a745');
        switchKnob.setAttribute('stroke', '#1e7e34');
    } else {
        switchKnob.setAttribute('cx', '10');
        switchKnob.setAttribute('fill', '#fff');
        switchKnob.setAttribute('stroke', '#999');
    }
}

// Update hot plate visual state
function updateHotPlateVisual(hotPlateElement, isOn) {
    if (!hotPlateElement) return;
    
    if (isOn) {
        hotPlateElement.classList.remove('hot-plate-off');
        hotPlateElement.classList.add('hot-plate-on');
    } else {
        hotPlateElement.classList.remove('hot-plate-on');
        hotPlateElement.classList.add('hot-plate-off');
    }
}

// Send hot plate command to server
function sendHotPlateCommand(plateNumber, isOn) {
    const command = {
        type: 'hotplate_control',
        hotplate: plateNumber,
        state: isOn
    };
    
    // Send via WebSocket if connected
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(command));
    }
}

// Add test functions for manual fan animation testing
window.testFanAnimation = function(fanNumber = 1, speed = 255) {
    const svgObject = document.querySelector('object[data="/static/main.svg"]');
    let svgDoc = null;
    
    if (svgObject && svgObject.contentDocument) {
        svgDoc = svgObject.contentDocument;
    } else if (svgObject && svgObject.getSVGDocument) {
        // Fallback for older browsers
        svgDoc = svgObject.getSVGDocument();
    }
    
    if (!svgDoc) {
        return false;
    }
    
    const fanElement = svgDoc.getElementById(`fan${fanNumber}`);
    const fanBlade = fanElement?.querySelector('.fan-blade');
    
    if (fanBlade) {
        const duration = 5.0 - (speed / 255) * 4.5;
        
        // Remove any existing animations
        const existingAnim = fanBlade.querySelector('animateTransform');
        if (existingAnim) {
            existingAnim.remove();
        }
        
        if (speed > 0) {
            // Create SVG animateTransform element
            const animateTransform = document.createElementNS('http://www.w3.org/2000/svg', 'animateTransform');
            animateTransform.setAttribute('attributeName', 'transform');
            animateTransform.setAttribute('type', 'rotate');
            animateTransform.setAttribute('from', '0 0 0');
            animateTransform.setAttribute('to', '360 0 0');
            animateTransform.setAttribute('dur', `${duration}s`);
            animateTransform.setAttribute('repeatCount', 'indefinite');
            
            fanBlade.appendChild(animateTransform);
            animateTransform.beginElement();
            
            return true;
        } else {
            // Speed is 0, no animation needed
        }
        
        return true;
    } else {
        return false;
    }
};

// Test all fans at different speeds
window.testAllFans = function() {
    testFanAnimation(1, 255); // Fastest
    testFanAnimation(2, 128); // Medium
    testFanAnimation(3, 64);  // Slow
    testFanAnimation(4, 0);   // Stopped
};

// Stop all fans
window.stopAllFans = function() {
    const svgObject = document.querySelector('object[data="/static/main.svg"]');
    let svgDoc = null;
    
    if (svgObject && svgObject.contentDocument) {
        svgDoc = svgObject.contentDocument;
    } else if (svgObject && svgObject.getSVGDocument) {
        svgDoc = svgObject.getSVGDocument();
    }
    
    if (!svgDoc) {
        console.error('SVG document not found');
        return false;
    }
    
    for (let i = 1; i <= 4; i++) {
        const fanElement = svgDoc.getElementById(`fan${i}`);
        const fanBlade = fanElement?.querySelector('.fan-blade');
        
        if (fanBlade) {
            // Remove SVG animations
            const animations = fanBlade.querySelectorAll('animateTransform');
            animations.forEach(anim => anim.remove());
            
            // Also remove CSS classes and styles
            fanBlade.classList.remove('fan-on');
            fanBlade.classList.add('fan-off');
            fanBlade.style.animation = 'none';
        }
    }
    
    return true;
};
