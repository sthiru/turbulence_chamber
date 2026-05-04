// Beta Page JavaScript
// WebSocket connection
let ws = null;
let reconnectInterval = null;

// Configuration
const CONFIG = {
    WS_URL: `ws://${window.location.host}/ws/status`,
    RECONNECT_DELAY: 3000,
    WARNING_TEMP: 60,
    DANGER_TEMP: 80
};

// Initialize WebSocket connection
function initWebSocket() {
    try {
        // Check if server is available
        const serverUrl = `http://${window.location.host}`;
        fetch(serverUrl)
            .then(response => {
                if (response.ok) {
                    // Server is available, connect WebSocket
                    ws = new WebSocket(CONFIG.WS_URL);
                    
                    ws.onopen = function() {
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
                            // Silently handle parsing errors
                        }
                    };
                    
                    ws.onclose = function() {
                        scheduleReconnect();
                    };
                    
                    ws.onerror = function(error) {
                        // Try to display connection status
                        updateSystemReadyStatus(false);
                        scheduleReconnect();
                    };
                } else {
                    throw new Error('Server not responding');
                }
            })
            .catch(error => {
                console.error('Server not available, WebSocket connection failed');
                updateSystemReadyStatus(false);
                scheduleReconnect();
            });
            
    } catch (error) {
        updateSystemReadyStatus(false);
        scheduleReconnect();
    }
}

// Schedule reconnection
function scheduleReconnect() {
    if (!reconnectInterval) {
        reconnectInterval = setInterval(() => {
            initWebSocket();
        }, CONFIG.RECONNECT_DELAY);
    }
}

// Update system ready status display
function updateSystemReadyStatus(systemReady) {
    const statusElement = document.getElementById('connectionStatus');
    
    if (statusElement) {
        if (systemReady) {
            statusElement.className = 'connection-status connected';
            statusElement.innerHTML = '<i class="fas fa-check-circle"></i> System Ready';
        } else {
            statusElement.className = 'connection-status disconnected';
            statusElement.innerHTML = '<i class="fas fa-exclamation-circle"></i> System Not Ready';
        }
    }
}

// Handle WebSocket messages
function handleWebSocketMessage(data) {
    if (data.type === 'system_status') {
        updateSystemStatus(data);
    } else if (data.type === 'historical_data' || data.type === 'current_data') {
        updateSensorData(data.data);
        
        // Get latest data for system status
        const dataArray = Array.isArray(data.data) ? data.data : [data.data];
        const latestData = dataArray[dataArray.length - 1];
        
        if (latestData) {
            updateSensorData(latestData);
            
            // Capture data point if data capture is active
            captureDataPoint(latestData);
            
            // Also update system ready status if available in current_data
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

    // Update ambient temperature and humidity (from DHT sensor)
    const ambientTemps = data.temperature_dht || [];
    const humidities = data.humidity || [];

    if (ambientTemps.length > 0 && ambientTemps[0] >= -100) {
        const ambientTempElement = svgDoc.getElementById('ambientTemp');
        if (ambientTempElement) {
            ambientTempElement.textContent = ambientTemps[0].toFixed(1) + '°C';
        }
    }

    if (humidities.length > 1 && humidities[1] >= 0) {
        const ambientHumElement = svgDoc.getElementById('ambientHum');
        if (ambientHumElement) {
            ambientHumElement.textContent = humidities[1].toFixed(1) + '%';
        }

        // Also update internal humidity (using the same humidity data for now)
        const internalHumElement = svgDoc.getElementById('internalHum');
        if (internalHumElement) {
            internalHumElement.textContent = humidities[1].toFixed(1) + '%';
        }
    }
    
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

    // Update windflow sensors
    const flowRates = data.flow_rates || [];
    flowRates.forEach((flow, index) => {
        const flowElement = svgDoc.getElementById(`flow${index + 1}`);
        if (flowElement) {
            flowElement.textContent = flow.toFixed(2) + ' m/s';
        }
    });
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    initWebSocket();
    
    // Wait for SVG to load before initializing controls
    const svgObject = document.querySelector('object[data="/static/main.svg"]');
    if (svgObject) {
        svgObject.addEventListener('load', function() {
            setTimeout(initFanControls, 100); // Small delay to ensure SVG is ready
        });
        
        // Also try immediately in case SVG is already loaded
        if (svgObject.contentDocument) {
            setTimeout(initFanControls, 100);
        }
    } else {
        console.error('SVG object not found');
    }
    
    // Initialize data capture functionality
    initDataCapture();
});

// Data Capture System
let capturedData = [];
let isCapturing = false;
let currentSessionId = null;

function initDataCapture() {
    const startBtn = document.getElementById('startCaptureBtn');
    const stopBtn = document.getElementById('stopCaptureBtn');
    const downloadIconBtn = document.getElementById('downloadIconBtn');
    const dataCounter = document.getElementById('dataCounter');
    
    if (startBtn) {
        startBtn.addEventListener('click', startDataCapture);
    }
    
    if (stopBtn) {
        stopBtn.addEventListener('click', stopDataCapture);
    }
    
    if (downloadIconBtn) {
        downloadIconBtn.addEventListener('click', downloadCapturedData);
    }
    
    // Check capture status on page load
    checkCaptureStatus();
}

async function checkCaptureStatus() {
    try {
        const response = await fetch('/api/data-capture/status');
        const status = await response.json();
        
        if (status.active) {
            isCapturing = true;
            currentSessionId = status.session?.id;
            updateCaptureUI(true);
        }
    } catch (e) {
        console.error('Error checking capture status:', e);
    }
}

async function startDataCapture() {
    try {
        const response = await fetch('/api/data-capture', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                start: true,
                capture_id: `session_${new Date().toISOString().replace(/[:.]/g, '-')}`
            })
        });
        
        const result = await response.json();
        
        if (result.status === 'success') {
            isCapturing = true;
            currentSessionId = result.session_id;
            capturedData = []; // Reset data array
            
            updateCaptureUI(true);
            
            // Show notification
            showNotification('Data capture started', 'success');
        } else {
            console.error('Failed to start data capture:', result.message);
            showNotification('Failed to start data capture: ' + result.message, 'error');
        }
    } catch (e) {
        console.error('Error starting data capture:', e);
        showNotification('Error starting data capture', 'error');
    }
}

async function stopDataCapture() {
    try {
        const response = await fetch('/api/data-capture', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                start: false
            })
        });
        
        const result = await response.json();
        
        if (result.status === 'success') {
            isCapturing = false;
            
            updateCaptureUI(false);
            
            // Show notification with session info
            showNotification(`Data capture stopped. ${result.session_info.total_data_points} data points captured.`, 'info');
        } else {
            console.error('Failed to stop data capture:', result.message);
            showNotification('Failed to stop data capture: ' + result.message, 'error');
        }
    } catch (e) {
        console.error('Error stopping data capture:', e);
        showNotification('Error stopping data capture', 'error');
    }
}

function updateCaptureUI(capturing) {
    const startBtn = document.getElementById('startCaptureBtn');
    const stopBtn = document.getElementById('stopCaptureBtn');
    const downloadIconBtn = document.getElementById('downloadIconBtn');
    
    if (capturing) {
        if (startBtn) startBtn.classList.add('d-none');
        if (stopBtn) stopBtn.classList.remove('d-none');
        if (downloadIconBtn) downloadIconBtn.classList.remove('d-none');
    } else {
        if (startBtn) startBtn.classList.remove('d-none');
        if (stopBtn) stopBtn.classList.add('d-none');
        
        // Always keep download button visible if there's captured data
        if (downloadIconBtn) {
            if (capturedData.length > 0) {
                downloadIconBtn.classList.remove('d-none');
            } else {
                downloadIconBtn.classList.add('d-none');
            }
        }
    }
}

function captureDataPoint(data) {
    if (!isCapturing) return;
    
    // Create a data point with timestamp and relevant sensor data
    const dataPoint = {
        timestamp: new Date().toISOString(),
        temperatures: data.temperatures || [],
        target_temperatures: data.target_temperatures || [],
        fan_speeds: data.fan_speeds || [],
        hot_plate_states: data.hot_plate_states || [],
        cn2: data.cn2 || 0,
        cn2_optical: data.cn2_optical || null,
        temperature_bmp: data.temperature_bmp || [],
        humidity: data.humidity || [],
        pressure: data.pressure || [],
        image_filename: data.image_filename || null,
        session_id: currentSessionId
    };
    
    capturedData.push(dataPoint);
    updateDataCounter();
}

function updateDataCounter() {
    const dataCounter = document.getElementById('dataCounter');
    if (dataCounter) {
        dataCounter.textContent = capturedData.length;
        
        // Update badge color based on data count
        dataCounter.className = capturedData.length === 0 ? 'badge bg-secondary' : 
                              capturedData.length < 100 ? 'badge bg-primary' : 
                              capturedData.length < 500 ? 'badge bg-info' : 'badge bg-success';
    }
}

async function downloadCapturedData() {
    try {
        const response = await fetch('/api/data-capture/download');
        
        if (response.ok) {
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = response.headers.get('Content-Disposition')?.split('filename=')[1]?.replace(/"/g, '') || 'turbulence_data.csv';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
            
            showNotification('Data downloaded successfully', 'success');
        } else {
            const error = await response.json();
            console.error('Failed to download data:', error.detail);
            showNotification('Failed to download data: ' + error.detail, 'error');
        }
    } catch (e) {
        console.error('Error downloading data:', e);
        showNotification('Error downloading data', 'error');
    }
}

function showNotification(message, type = 'info') {
    // Create a simple notification (you can enhance this with a proper notification library)
    const notification = document.createElement('div');
    notification.className = `alert alert-${type === 'error' ? 'danger' : type === 'success' ? 'success' : 'info'} alert-dismissible fade show position-fixed`;
    notification.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
    notification.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    document.body.appendChild(notification);
    
    // Auto-remove after 5 seconds
    setTimeout(() => {
        if (notification.parentNode) {
            notification.parentNode.removeChild(notification);
        }
    }, 5000);
}

// Initialize fan controls
function initFanControls() {
    const svgObject = document.querySelector('object[data="/static/main.svg"]');
    let svgDoc = null;
    
    if (svgObject && svgObject.contentDocument) {
        svgDoc = svgObject.contentDocument;
    } else if (svgObject && svgObject.getSVGDocument) {
        svgDoc = svgObject.getSVGDocument();
    }
    
    if (!svgDoc) {
        return;
    }
    
    // Initialize controls for each fan
    for (let i = 1; i <= 4; i++) {
        initFanControl(svgDoc, i);
    }
    
    // Initialize hot plate controls
    initHotPlateControl(svgDoc, 1);
    initHotPlateControl(svgDoc, 2);
}

// Initialize individual fan control
function initFanControl(svgDoc, fanNumber) {
    const controlsGroup = svgDoc.getElementById(`fan${fanNumber}-controls`);
    if (!controlsGroup) return;
    
    const sliderElement = svgDoc.getElementById(`fan${fanNumber}-slider`);
    const sliderKnob = svgDoc.getElementById(`fan${fanNumber}-slider-knob`);
    
    let isDragging = false;
    let currentSpeed = 0;
    
    // Slider drag handlers
    if (sliderElement && sliderKnob) {
        
        sliderKnob.addEventListener('mousedown', function(e) {
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
                isDragging = false;
            }
        });
        
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
    
    let isOn = false;
    
    // Switch click handler
    if (switchElement) {
        switchElement.addEventListener('click', function() {
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
