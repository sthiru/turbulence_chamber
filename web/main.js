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

// Initialize bottom bar functionality after loading
initializeBottomBar();

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
        // Get latest data for system status
        const dataArray = Array.isArray(data.data) ? data.data : [data.data];
        const latestData = dataArray[dataArray.length - 1];

        if (latestData) {
            try {
                updateSensorData(latestData);
            } catch (error) {
                console.error('Error in updateSensorData:', error);
            }
            
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
                
                if (temp < 20) {
                    circle.classList.add('sensor-normal');
                } else if (temp < 30) {
                    circle.classList.add('sensor-warning');
                } else {
                    circle.classList.add('sensor-danger');
                }
            }
        }
    });

    // Update hotplate surface temperatures (using separate variables)
    const hotplate1TempElement = svgDoc.getElementById('hotplate1-temp');
    const hotplate2TempElement = svgDoc.getElementById('hotplate2-temp');
    
    // Hotplate 1 temperature
    if (data.temp_hotplate1 !== undefined && hotplate1TempElement) {
        if (data.temp_hotplate1 < -100) {
            hotplate1TempElement.textContent = '--°C';
        } else {
            hotplate1TempElement.textContent = data.temp_hotplate1.toFixed(1) + '°C';
        }
    }
    
    // Hotplate 2 temperature
    if (data.temp_hotplate2 !== undefined && hotplate2TempElement) {
        if (data.temp_hotplate2 < -100) {
            hotplate2TempElement.textContent = '--°C';
        } else {
            hotplate2TempElement.textContent = data.temp_hotplate2.toFixed(1) + '°C';
        }
    }

    // Update ambient temperature and humidity (from separate internal/external variables)
    const ambientTempElement = svgDoc.getElementById('ambientTemp');
    const ambientHumElement = svgDoc.getElementById('ambientHum');
    const internalHumElement = svgDoc.getElementById('internalHum');

    // External temperature (ambient)
    if (data.bmpTemperature_external !== undefined && data.bmpTemperature_external >= -100 && ambientTempElement) {
        ambientTempElement.textContent = data.bmpTemperature_external.toFixed(1) + '°C';
    }

    // External humidity (ambient)
    if (data.dhtHumidity_external !== undefined && data.dhtHumidity_external >= 0 && ambientHumElement) {
        ambientHumElement.textContent = data.dhtHumidity_external.toFixed(1) + '%';
    }

    // Internal humidity
    if (data.dhtHumidity_internal !== undefined && data.dhtHumidity_internal >= 0 && internalHumElement) {
        internalHumElement.textContent = data.dhtHumidity_internal.toFixed(1) + '%';
    }
    
    // Update hot plates
    const dataArray = Array.isArray(data) ? data : [data];
    const firstDataItem = dataArray[0];
    const hotPlateStates = (firstDataItem && firstDataItem.hot_plate_states) ? firstDataItem.hot_plate_states : [];
    hotPlateStates.forEach((state, index) => {
        const hotplateElement = svgDoc.getElementById(`hotplate${index + 1}`);
        const switchKnob = svgDoc.getElementById(`hotplate${index + 1}-switch-knob`);
        
        if (hotplateElement) {
            if (state) {
                // Directly set SVG attributes for ON state
                hotplateElement.setAttribute('fill', '#ff6b6b');
                hotplateElement.setAttribute('stroke', '#ff4444');
                hotplateElement.setAttribute('stroke-width', '3');
            } else {
                // Directly set SVG attributes for OFF state
                hotplateElement.setAttribute('fill', '#c0c0c0');
                hotplateElement.setAttribute('stroke', '#333');
                hotplateElement.setAttribute('stroke-width', '2');
            }
        }
        
        // Update switch knob position
        if (switchKnob) {
            if (state) {
                // ON position - move knob to the right
                switchKnob.setAttribute('cx', '30');
                switchKnob.setAttribute('fill', '#28a745');
            } else {
                // OFF position - move knob to the left
                switchKnob.setAttribute('cx', '10');
                switchKnob.setAttribute('fill', '#fff');
            }
        }
    });
    
    // Update fans
    const fanSpeeds = (firstDataItem && firstDataItem.fan_speeds) ? firstDataItem.fan_speeds : [];
    fanSpeeds.forEach((speed, index) => {
        const fanElement = svgDoc.getElementById(`fan${index + 1}`);
        const sliderKnob = svgDoc.getElementById(`fan${index + 1}-slider-knob`);

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

        // Update slider knob position based on speed (0-255 maps to -20 to 40)
        if (sliderKnob) {
            const sliderRange = 60; // From -20 to 40
            const validSpeed = speed || 0; // Handle undefined/null/0 values
            const knobPosition = -20 + (validSpeed / 255) * sliderRange;
            sliderKnob.setAttribute('cy', knobPosition);
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
        // Take the first value from the CN² array for display
        const cn2Array = Array.isArray(data.cn2) ? data.cn2 : [data.cn2];
        const cn2Value = cn2Array[0].toExponential(2);
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
    const flowRates = (firstDataItem && firstDataItem.flow_rates) ? firstDataItem.flow_rates : [];
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
            setTimeout(initFanSliders, 100); // Initialize fan slider drag handling
        });
        
        // Also try immediately in case SVG is already loaded
        if (svgObject.contentDocument) {
            setTimeout(initFanControls, 100);
            setTimeout(initFanSliders, 100);
        }
    } else {
        console.error('SVG object not found');
    }
});

async function captureDataPoint(data) {
    // This function is called by WebSocket to capture data points
    // Data capture logic is now handled by bottom-bar.js
    console.log('Data point received:', data);
}

// Initialize fan controls
let hotplateControlsInitialized = false;

function initFanControls() {
    const svgObject = document.querySelector('object[data="/static/main.svg"]');
    
    if (!svgObject) {
        return;
    }
    
    // Listen for postMessage from SVG
    window.addEventListener('message', function(event) {
        if (event.data && event.data.type === 'fan_speed_change') {
            const fanNumber = event.data.fan;
            const speed = event.data.speed;
            sendFanCommand(fanNumber, speed);
        }
    });
    
    // Wait for SVG to load
    svgObject.addEventListener('load', function() {
        let svgDoc = null;
        
        if (svgObject.contentDocument) {
            svgDoc = svgObject.contentDocument;
        } else if (svgObject.getSVGDocument) {
            svgDoc = svgObject.getSVGDocument();
        }
        
        if (svgDoc) {
            initHotPlateControl(svgDoc, 0); // Hotplate 1 (Arduino ID 0)
            initHotPlateControl(svgDoc, 1); // Hotplate 2 (Arduino ID 1)
            hotplateControlsInitialized = true;
        }
    });
    
    // Also try immediately in case SVG is already loaded
    try {
        if (svgObject.contentDocument) {
            // SVG already loaded - initialize hotplate controls
            const svgDoc = svgObject.contentDocument;
            initHotPlateControl(svgDoc, 0); // Hotplate 1 (Arduino ID 0)
            initHotPlateControl(svgDoc, 1); // Hotplate 2 (Arduino ID 1)
        }
    } catch (error) {
        // Error in immediate SVG initialization
    }
}

// Initialize individual fan control (no longer used - replaced by SVG-internal handling)
function initFanControl(svgDoc, fanNumber) {
    // This function is no longer used as slider handling is now done within the SVG
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
async function sendFanCommand(fanNumber, speed) {
    try {
        const response = await fetch('/api/fan/set', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                fan: fanNumber,
                speed: speed
            })
        });
        
        if (!response.ok) {
            console.error('Failed to set fan speed:', response.statusText);
        }
    } catch (error) {
        console.error('Error sending fan command:', error);
    }
}

// Initialize individual hot plate control
function initHotPlateControl(svgDoc, plateNumber) {
    if (hotplateControlsInitialized) return;
    // Map 0-based Arduino ID to 1-based SVG element ID
    const svgPlateNumber = plateNumber + 1;
    const switchElement = svgDoc.getElementById(`hotplate${svgPlateNumber}-switch`);
    const switchKnob = svgDoc.getElementById(`hotplate${svgPlateNumber}-switch-knob`);
    const hotPlateElement = svgDoc.getElementById(`hotplate${svgPlateNumber}`);
    
    let isOn = false;
    
    // Switch click handler
    if (switchElement) {
        switchElement.addEventListener('click', async function() {
            isOn = !isOn;
            updateHotPlateSwitchVisual(switchKnob, isOn);
            updateHotPlateVisual(hotPlateElement, isOn);
            
            // Send hot plate control command (use 0-based Arduino ID)
            await sendHotPlateCommand(plateNumber, isOn);
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
async function sendHotPlateCommand(plateNumber, isOn) {
    try {
        const response = await fetch(`/api/hotplate/${plateNumber}/toggle`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                state: isOn
            })
        });
        
        if (!response.ok) {
            console.error('Failed to toggle hot plate:', response.statusText);
        } else {
            console.log(`Hot plate ${plateNumber} toggled to ${isOn ? 'ON' : 'OFF'}`);
        }
    } catch (error) {
        console.error('Error sending hot plate command:', error);
    }
}

// Fan slider drag handling (extracted from main.svg)
let draggingFan = null;
let startY = 0;
let startCy = 0;

function initFanSliders() {
    const svgObject = document.querySelector('object[data="/static/main.svg"]');
    if (!svgObject) return;
    
    const svgDoc = svgObject.contentDocument || svgObject.getSVGDocument();
    if (!svgDoc) return;
    
    for (let i = 1; i <= 4; i++) {
        const slider = svgDoc.getElementById(`fan${i}-slider`);
        const knob = svgDoc.getElementById(`fan${i}-slider-knob`);
        
        if (slider && knob) {
            knob.addEventListener('mousedown', function(e) {
                draggingFan = i;
                startY = e.clientY;
                startCy = parseFloat(knob.getAttribute('cy')) || 10;
                e.preventDefault();
                e.stopPropagation();
                
                // Add temporary SVG document-level listeners for drag
                const handleMouseMove = function(moveEvent) {
                    if (!draggingFan) return;
                    
                    const deltaY = moveEvent.clientY - startY;
                    let newCy = startCy + deltaY;
                    
                    // Clamp to slider range (-20 to 40)
                    if (newCy < -20) newCy = -20;
                    if (newCy > 40) newCy = 40;
                    
                    knob.setAttribute('cy', newCy);
                };
                
                const handleMouseUp = function() {
                    if (draggingFan) {
                        // Calculate final speed and send command
                        const currentCy = parseFloat(knob.getAttribute('cy')) || 10;
                        const speed = Math.round(((40 - currentCy) / 60) * 255);
                        sendFanCommand(draggingFan - 1, speed);
                        
                        draggingFan = null;
                    }
                    svgDoc.removeEventListener('mousemove', handleMouseMove);
                    svgDoc.removeEventListener('mouseup', handleMouseUp);
                };
                
                svgDoc.addEventListener('mousemove', handleMouseMove);
                svgDoc.addEventListener('mouseup', handleMouseUp);
            });
            
            slider.addEventListener('mousedown', function(e) {
                draggingFan = i;
                startY = e.clientY;
                startCy = parseFloat(knob.getAttribute('cy')) || 10;
                e.preventDefault();
                e.stopPropagation();
                
                // Add temporary SVG document-level listeners for drag
                const handleMouseMove = function(moveEvent) {
                    if (!draggingFan) return;
                    
                    const deltaY = moveEvent.clientY - startY;
                    let newCy = startCy + deltaY;
                    
                    // Clamp to slider range (-20 to 40)
                    if (newCy < -20) newCy = -20;
                    if (newCy > 40) newCy = 40;
                    
                    knob.setAttribute('cy', newCy);
                };
                
                const handleMouseUp = function() {
                    if (draggingFan) {
                        // Calculate final speed and send command
                        const currentCy = parseFloat(knob.getAttribute('cy')) || 10;
                        const speed = Math.round(((40 - currentCy) / 60) * 255);
                        sendFanCommand(draggingFan - 1, speed);
                        
                        draggingFan = null;
                    }
                    svgDoc.removeEventListener('mousemove', handleMouseMove);
                    svgDoc.removeEventListener('mouseup', handleMouseUp);
                };
                
                svgDoc.addEventListener('mousemove', handleMouseMove);
                svgDoc.addEventListener('mouseup', handleMouseUp);
            });
        }
    }
}
