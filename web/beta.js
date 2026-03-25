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
        ws = new WebSocket(CONFIG.WS_URL);
        
        ws.onopen = function() {
            console.log('WebSocket connected');
            updateConnectionStatus(true);
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
            updateConnectionStatus(false);
            scheduleReconnect();
        };
        
        ws.onerror = function(error) {
            console.error('WebSocket error:', error);
            updateConnectionStatus(false);
        };
        
    } catch (error) {
        console.error('Error initializing WebSocket:', error);
        updateConnectionStatus(false);
        scheduleReconnect();
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

// Update connection status
function updateConnectionStatus(connected) {
    const statusElement = document.getElementById('connectionStatus');
    if (connected) {
        statusElement.className = 'connection-status connected';
        statusElement.innerHTML = '<i class="fas fa-wifi"></i> Connected';
    } else {
        statusElement.className = 'connection-status disconnected';
        statusElement.innerHTML = '<i class="fas fa-wifi"></i> Disconnected';
    }
}

// Handle WebSocket messages
function handleWebSocketMessage(data) {
    if (data.type === 'system_status') {
        updateSystemStatus(data);
    } else if (data.type === 'historical_data' || data.type === 'current_data') {
        updateSensorData(data.data[data.data.length - 1]);
    }
}

// Update system status
function updateSystemStatus(data) {
    document.getElementById('systemReady').textContent = data.system_ready ? 'Yes' : 'No';
    document.getElementById('arduinoPort').textContent = data.arduino_port || '--';
}

// Update sensor data
function updateSensorData(data) {
    // Update temperature sensors
    const temperatures = data.temperatures || [];
    temperatures.forEach((temp, index) => {
        const tempElement = document.getElementById(`temp${index + 1}`);
        const sensorElement = document.getElementById(`sensor${index + 1}`);
        
        if (tempElement) {
            if (temp < -100) {
                tempElement.textContent = '--°C';
            } else {
                tempElement.textContent = temp.toFixed(1) + '°C';
            }
        }
        
        // Update sensor color based on temperature
        if (sensorElement && temp >= -100) {
            const circle = sensorElement.querySelector('.sensor-circle');
            circle.classList.remove('sensor-normal', 'sensor-warning', 'sensor-danger');
            
            if (temp >= CONFIG.DANGER_TEMP) {
                circle.classList.add('sensor-danger');
            } else if (temp >= CONFIG.WARNING_TEMP) {
                circle.classList.add('sensor-warning');
            } else {
                circle.classList.add('sensor-normal');
            }
        }
    });
    
    // Update hot plates
    const hotPlateStates = data.hot_plate_states || [];
    hotPlateStates.forEach((state, index) => {
        const hotplateElement = document.getElementById(`hotplate${index + 1}`);
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
        const fanElement = document.getElementById(`fan${index + 1}`);
        const speedElement = document.getElementById(`fan${index + 1}Speed`);
        const fanBlade = fanElement.querySelector('.fan-blade');
        
        if (fanBlade) {
            // Remove all animation classes first
            fanBlade.classList.remove('fan-on', 'fan-off');
            
            if (speed > 0) {
                // Calculate rotation duration based on PWM speed (0-255)
                // Higher speed = faster rotation = shorter duration
                // Map: 255 -> 0.5s (fastest), 1 -> 5s (slowest)
                const duration = 5.0 - (speed / 255) * 4.5; // 5s to 0.5s
                
                // Set animation duration before adding the class
                fanBlade.style.animationDuration = `${duration}s`;
                
                // Add the animation class
                fanBlade.classList.add('fan-on');
            } else {
                // Stop animation
                fanBlade.classList.add('fan-off');
                fanBlade.style.animationDuration = '';
            }
        }
        
        if (speedElement) {
            speedElement.textContent = speed;
        }
    });
    
    // Update camera image and status
    if (data.camera_image !== undefined) {
        const cameraImageElement = document.getElementById('cameraImage');
        const cameraPlaceholderElement = document.getElementById('cameraPlaceholder');
        const cameraStatusElement = document.getElementById('cameraStatus');
        
        if (data.camera_image) {
            // Update image source
            const imageUrl = `/camera_images/${data.camera_image}`;
            cameraImageElement.src = imageUrl;
            cameraImageElement.style.display = 'block';
            cameraPlaceholderElement.style.display = 'none';
            
            // Update status
            if (cameraStatusElement) {
                cameraStatusElement.textContent = `Latest: ${data.camera_image}`;
            }
        } else {
            // Hide image, show placeholder
            cameraImageElement.style.display = 'none';
            cameraPlaceholderElement.style.display = 'flex';
            
            if (cameraStatusElement) {
                cameraStatusElement.textContent = 'No camera image available';
            }
        }
    }
    
    // Update camera status
    if (data.camera_status !== undefined) {
        const cameraStatusElement = document.getElementById('cameraStatus');
        if (cameraStatusElement) {
            let statusText = 'Camera: ';
            let statusClass = '';
            
            if (data.camera_status.error) {
                statusText += `Error - ${data.camera_status.error}`;
                statusClass = 'camera-status-disconnected';
            } else if (data.camera_status.connected) {
                statusText += 'Connected';
                statusClass = 'camera-status-connected';
            } else if (data.camera_status.available) {
                statusText += 'Available';
                statusClass = 'camera-status-connected';
            } else {
                statusText += 'Simulation Mode';
                statusClass = 'camera-status-simulation';
            }
            
            cameraStatusElement.textContent = statusText;
            cameraStatusElement.className = statusClass;
        }
    }
    
    // Update CN² optical
    if (data.cn2_optical !== undefined) {
        const cn2OpticalElement = document.getElementById('cn2OpticalValue');
        if (cn2OpticalElement) {
            const cn2OpticalValue = data.cn2_optical.toExponential(2);
            cn2OpticalElement.textContent = cn2OpticalValue;
        }
    }
    
    // Update CN²
    if (data.cn2 !== undefined) {
        const cn2Value = data.cn2.toExponential(2);
        document.getElementById('cn2Value').textContent = cn2Value;
        document.getElementById('cn2TitleValue').textContent = cn2Value;
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    initWebSocket();
});
