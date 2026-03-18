// Global variables
let ws;
let tempChart;
let tempData = {
    labels: [],
    datasets: []
};
let temperatureHistory = {
    timestamps: [],
    data: [] // Array of arrays for each sensor
};
let manualControlState = {
    hotplates: [false, false],
    fans: [false, false, false, false]
};

// Configuration
const CONFIG = {
    MAX_TEMP: 80,
    WARNING_TEMP: 50,
    DANGER_TEMP: 70,
    UPDATE_INTERVAL: 2000,
    CHART_MAX_POINTS: 150, // 5 minutes at 2-second intervals
    CHART_DURATION: 300000, // 5 minutes in milliseconds
    NUM_SENSORS: 5
};

// Initialize WebSocket connection
function initWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/status`;
    
    console.log('Attempting WebSocket connection to:', wsUrl);
    
    try {
        ws = new WebSocket(wsUrl);
        
        ws.onopen = function() {
            console.log('WebSocket connected successfully');
            updateConnectionStatus('online', 'Connected');
            hideErrorMessage();
        };
        
        ws.onmessage = function(event) {
            try {
                const data = JSON.parse(event.data);
                console.log('WebSocket data received:', data);
                
                // Ignore ping messages
                if (data.type === 'ping') {
                    console.log('Ping message received, ignoring');
                    return;
                }
                
                updateDisplay(data);
            } catch (error) {
                console.error('Error parsing WebSocket data:', error);
                showErrorMessage('Invalid data received from server');
            }
        };
        
        ws.onclose = function(event) {
            console.log('WebSocket disconnected, code:', event.code, 'reason:', event.reason);
            updateConnectionStatus('offline', 'Disconnected');
            // Try to reconnect after 3 seconds
            setTimeout(initWebSocket, 3000);
        };
        
        ws.onerror = function(error) {
            console.error('WebSocket error:', error);
            updateConnectionStatus('error', 'Connection Error');
            showErrorMessage('Connection error. Please check if the server is running on port 8000.');
        };
    } catch (error) {
        console.error('Error creating WebSocket:', error);
        updateConnectionStatus('error', 'Connection Failed');
        showErrorMessage('Failed to establish connection to server. Please check if the server is running.');
    }
}

// Update connection status
function updateConnectionStatus(status, text) {
    const statusElement = document.getElementById('connection-status');
    statusElement.className = `badge bg-${status === 'online' ? 'success' : status === 'offline' ? 'danger' : 'warning'}`;
    statusElement.innerHTML = `<i class="fas fa-circle"></i> ${text}`;
}

// Show/hide error messages
function showErrorMessage(message, type = 'danger') {
    const errorElement = document.getElementById('error-message');
    errorElement.textContent = message;
    errorElement.className = `alert alert-${type} mt-3`;
    errorElement.classList.remove('d-none');
    
    // Auto-hide success messages after 3 seconds
    if (type === 'success') {
        setTimeout(() => {
            hideErrorMessage();
        }, 3000);
    }
}

function hideErrorMessage() {
    const errorElement = document.getElementById('error-message');
    errorElement.classList.add('d-none');
}

// Update display with new data
function updateDisplay(data) {
    try {
        // Update system status
        updateSystemStatus(data);
        
        // Update temperature sensors
        updateTemperatureSensors(data.temperatures || []);
        
        // Update hot plate controls
        updateHotPlateControls(data.target_temperatures || [], data.hot_plate_states || []);
        
        // Update fan controls
        updateFanControls(data.fan_speeds || []);
        
        // Update chart
        updateChart(data.temperatures || []);
        
        // Update manual controls
        updateManualControls(data);
        
        // Update device status
        updateDeviceStatus(data);
        
    } catch (error) {
        console.error('Error updating display:', error);
        showErrorMessage('Error updating display');
    }
}

// Update system status
function updateSystemStatus(data) {
    const systemReadyElement = document.getElementById('system-ready');
    const deviceStatusElement = document.getElementById('device-status');
    const arduinoPortElement = document.getElementById('arduino-port');
    const pollingIntervalElement = document.getElementById('polling-interval-display');
    
    systemReadyElement.textContent = data.system_ready ? 'Yes' : 'No';
    systemReadyElement.className = data.system_ready ? 'text-success' : 'text-danger';
    
    deviceStatusElement.textContent = data.device_status || 'Unknown';
    
    // Update device status color
    const statusClass = data.device_status === 'online' ? 'text-success' : 
                       data.device_status === 'offline' ? 'text-danger' : 'text-warning';
    deviceStatusElement.className = statusClass;
    
    // Update Arduino port display
    if (data.arduino_port) {
        arduinoPortElement.textContent = data.arduino_port;
        arduinoPortElement.className = 'text-success';
        
        // Update the select dropdown to match current port
        const comPortSelect = document.getElementById('com-port-select');
        if (comPortSelect) {
            comPortSelect.value = data.arduino_port;
        }
    } else {
        arduinoPortElement.textContent = 'Not connected';
        arduinoPortElement.className = 'text-danger';
    }
    
    // Update polling interval display
    if (data.polling_interval) {
        pollingIntervalElement.textContent = data.polling_interval + 's';
        const pollingInput = document.getElementById('polling-interval');
        if (pollingInput) {
            pollingInput.value = data.polling_interval;
        }
    }
    
    // Show error message if present
    if (data.error) {
        showErrorMessage(data.error);
    } else {
        hideErrorMessage();
    }
}

// Update temperature sensor display
function updateTemperatureSensors(temperatures) {
    temperatures.forEach((temp, index) => {
        const tempElement = document.getElementById(`temp-${index + 1}`);
        const statusElement = document.getElementById(`temp-status-${index + 1}`);
        const cardElement = tempElement.closest('.sensor-card');
        
        if (tempElement) {
            const tempClass = getTemperatureClass(temp);
            const tempValue = temp < -100 ? 'Error' : `${temp.toFixed(1)}°C`;
            const icon = getTemperatureIcon(temp);
            
            // Update temperature value
            tempElement.textContent = tempValue;
            tempElement.className = `temp-display ${tempClass}`;
            
            // Update icon
            const iconElement = cardElement.querySelector('.card-title i');
            if (iconElement) {
                iconElement.className = `fas ${icon}`;
            }
            
            // Update status text
            if (statusElement) {
                if (temp >= 0 && temp < 100) {
                    statusElement.textContent = getTemperatureStatus(temp);
                    statusElement.style.display = 'block';
                } else {
                    statusElement.style.display = 'none';
                }
            }
        }
    });
}

// Get temperature class for styling
function getTemperatureClass(temp) {
    if (temp < -100) return 'temp-error';
    if (temp >= CONFIG.DANGER_TEMP) return 'temp-danger';
    if (temp >= CONFIG.WARNING_TEMP) return 'temp-warning';
    return 'temp-normal';
}

// Get temperature icon
function getTemperatureIcon(temp) {
    if (temp < -100) return 'fa-exclamation-triangle';
    if (temp >= CONFIG.DANGER_TEMP) return 'fa-temperature-high';
    if (temp >= CONFIG.WARNING_TEMP) return 'fa-temperature-half';
    return 'fa-temperature-low';
}

// Get temperature status text
function getTemperatureStatus(temp) {
    if (temp >= CONFIG.DANGER_TEMP) return 'Danger Zone';
    if (temp >= CONFIG.WARNING_TEMP) return 'Warning';
    return 'Normal';
}

// Update hot plate controls
function updateHotPlateControls(targetTemps, states) {
    targetTemps.forEach((target, index) => {
        // Update temperature input
        const tempInput = document.getElementById(`target-temp-${index}`);
        if (tempInput) {
            tempInput.value = target;
        }
        
        // Update button state
        const button = document.getElementById(`hotplate-btn-${index}`);
        if (button) {
            button.className = `btn btn-${states[index] ? 'danger' : 'success'} w-100`;
            button.innerHTML = `<i class="fas fa-power-off"></i> ${states[index] ? 'TURN OFF' : 'TURN ON'}`;
        }
    });
}

function updateFanControls(speeds) {
    speeds.forEach((speed, index) => {
        const percentage = Math.round((speed / 255) * 100);
        
        // Update progress bar
        const progressBar = document.getElementById(`fan-progress-${index}`);
        if (progressBar) {
            progressBar.style.width = `${percentage}%`;
            progressBar.textContent = `${percentage}%`;
        }
        
        // Update range slider
        const rangeSlider = document.getElementById(`fan-speed-${index}`);
        if (rangeSlider) {
            rangeSlider.value = speed;
        }
        
        // Update speed value display
        const speedValue = document.getElementById(`fan-speed-value-${index}`);
        if (speedValue) {
            speedValue.textContent = speed;
        }
    });
}

// Update fan speed display
function updateFanDisplay(fanId, speed) {
    const displayElement = document.getElementById(`fan-display-${fanId}`);
    if (displayElement) {
        displayElement.textContent = speed;
    }
}

// Initialize temperature chart
function initChart() {
    const ctx = document.getElementById('tempChart').getContext('2d');
    
    tempChart = new Chart(ctx, {
        type: 'line',
        data: tempData,
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    max: CONFIG.MAX_TEMP,
                    title: {
                        display: true,
                        text: 'Temperature (°C)'
                    },
                    ticks: {
                        callback: function(value) {
                            return value + '°C';
                        }
                    }
                },
                x: {
                    title: {
                        display: true,
                        text: 'Time'
                    }
                }
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'top'
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return context.dataset.label + ': ' + context.parsed.y.toFixed(1) + '°C';
                        }
                    }
                }
            },
            animation: {
                duration: 500
            }
        }
    });
}

// Update temperature chart with 5-minute history
function updateChart(temperatures) {
    if (!tempChart) return;
    
    const now = new Date();
    const timestamp = now.getTime();
    const timeString = now.toLocaleTimeString();
    
    // Store temperature data
    temperatureHistory.timestamps.push(timestamp);
    if (temperatureHistory.data.length === 0) {
        // Initialize data arrays for each sensor
        temperatures.forEach(() => temperatureHistory.data.push([]));
    }
    
    temperatures.forEach((temp, index) => {
        temperatureHistory.data[index].push(temp);
    });
    
    // Remove data older than 5 minutes
    const cutoffTime = timestamp - CONFIG.CHART_DURATION;
    const cutoffIndex = temperatureHistory.timestamps.findIndex(t => t >= cutoffTime);
    
    if (cutoffIndex > 0) {
        temperatureHistory.timestamps = temperatureHistory.timestamps.slice(cutoffIndex);
        temperatureHistory.data = temperatureHistory.data.map(sensorData => 
            sensorData.slice(cutoffIndex)
        );
    }
    
    // Update chart data
    tempData.labels = temperatureHistory.timestamps.map(t => 
        new Date(t).toLocaleTimeString()
    );
    
    temperatures.forEach((temp, index) => {
        if (!tempData.datasets[index]) {
            tempData.datasets[index] = {
                label: `Sensor ${index + 1}`,
                data: [],
                borderColor: `hsl(${index * 60}, 70%, 50%)`,
                backgroundColor: `hsla(${index * 60}, 70%, 50%, 0.1)`,
                tension: 0.1,
                borderWidth: 2,
                pointRadius: 2,
                pointHoverRadius: 4
            };
        }
        
        tempData.datasets[index].data = temperatureHistory.data[index] || [];
    });
    
    tempChart.update('none'); // Update without animation for real-time performance
}

// API functions
async function apiCall(endpoint, method = 'GET', data = null) {
    try {
        const options = {
            method: method,
            headers: {
                'Content-Type': 'application/json',
            }
        };
        
        if (data) {
            options.body = JSON.stringify(data);
        }
        
        const response = await fetch(endpoint, options);
        
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
        }
        
        return await response.json();
    } catch (error) {
        console.error('API call error:', error);
        showErrorMessage(`API Error: ${error.message}`);
        throw error;
    }
}

// Control functions
async function toggleHotPlate(plateId) {
    const button = document.getElementById(`hotplate-btn-${plateId}`);
    const isCurrentlyOn = button.classList.contains('btn-danger');
    const newState = !isCurrentlyOn;
    
    try {
        await apiCall(`/api/hotplate/${plateId}/toggle`, 'POST', { state: newState });
        console.log(`Hot plate ${plateId + 1} toggled to ${newState}`);
        
        // Update button state immediately for better UX
        button.className = `btn btn-${newState ? 'danger' : 'success'} w-100`;
        button.innerHTML = `<i class="fas fa-power-off"></i> ${newState ? 'TURN OFF' : 'TURN ON'}`;
        
    } catch (error) {
        console.error('Failed to toggle hot plate:', error);
        // Revert button state on error
        button.className = `btn btn-${isCurrentlyOn ? 'danger' : 'success'} w-100`;
        button.innerHTML = `<i class="fas fa-power-off"></i> ${isCurrentlyOn ? 'TURN OFF' : 'TURN ON'}`;
    }
}

async function setTemperature(plateId) {
    const targetTempInput = document.getElementById(`target-temp-${plateId}`);
    const targetTemp = parseFloat(targetTempInput.value);
    
    if (isNaN(targetTemp) || targetTemp < 0 || targetTemp > CONFIG.MAX_TEMP) {
        showErrorMessage(`Temperature must be between 0 and ${CONFIG.MAX_TEMP}°C`);
        targetTempInput.focus();
        return;
    }
    
    try {
        await apiCall('/api/temperature/set', 'POST', {
            sensor: plateId,
            target: targetTemp
        });
        console.log(`Temperature set to ${targetTemp}°C for hot plate ${plateId + 1}`);
        
    } catch (error) {
        console.error('Failed to set temperature:', error);
    }
}

async function setFanSpeed(fanId) {
    const speedInput = document.getElementById(`fan-speed-${fanId}`);
    const speed = parseInt(speedInput.value);
    
    if (isNaN(speed) || speed < 0 || speed > 255) {
        showErrorMessage('Fan speed must be between 0 and 255');
        speedInput.focus();
        return;
    }
    
    try {
        await apiCall('/api/fan/set', 'POST', {
            fan: fanId,
            speed: speed
        });
        console.log(`Fan ${fanId + 1} speed set to ${speed}`);
        
    } catch (error) {
        console.error('Failed to set fan speed:', error);
    }
}

// Utility functions
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    console.log('Initializing Temperature Control System...');
    
    // Initialize chart
    initChart();
    
    // Initialize WebSocket
    initWebSocket();
    
    // Initialize manual controls
    initManualControls();
    
    // Initialize COM port controls
    initComPortControls();
    
    // Add keyboard shortcuts
    document.addEventListener('keydown', function(event) {
        // Ctrl+R: Refresh connection
        if (event.ctrlKey && event.key === 'r') {
            event.preventDefault();
            if (ws) {
                ws.close();
            }
            initWebSocket();
        }
    });
    
    // Add input validation
    document.addEventListener('input', function(event) {
        if (event.target.type === 'number') {
            const min = parseFloat(event.target.min);
            const max = parseFloat(event.target.max);
            const value = parseFloat(event.target.value);
            
            if (!isNaN(value) && value < min) {
                event.target.value = min;
            } else if (!isNaN(value) && value > max) {
                event.target.value = max;
            }
        }
    });
    
    // Add automatic temperature input updates
    document.addEventListener('change', function(event) {
        if (event.target.id && event.target.id.startsWith('target-temp-')) {
            const plateId = parseInt(event.target.id.split('-')[2]);
            const targetTemp = parseFloat(event.target.value);
            
            if (!isNaN(targetTemp) && targetTemp >= 0 && targetTemp <= 120) {
                console.log(`Auto-setting temperature for hot plate ${plateId + 1} to ${targetTemp}°C`);
                setTemperature(plateId);
            }
        }
    });
    
    // Add automatic fan speed updates
    document.addEventListener('input', function(event) {
        if (event.target.id && event.target.id.startsWith('fan-speed-')) {
            const fanId = parseInt(event.target.id.split('-')[2]);
            const speed = parseInt(event.target.value);
            
            if (!isNaN(speed) && speed >= 0 && speed <= 255) {
                // Update the speed value display
                const speedValueElement = document.getElementById(`fan-speed-value-${fanId}`);
                if (speedValueElement) {
                    speedValueElement.textContent = speed;
                }
                
                // Update progress bar
                const percentage = Math.round((speed / 255) * 100);
                const progressBar = document.getElementById(`fan-progress-${fanId}`);
                if (progressBar) {
                    progressBar.style.width = `${percentage}%`;
                    progressBar.textContent = `${percentage}%`;
                }
                
                console.log(`Auto-setting fan ${fanId + 1} speed to ${speed}`);
                setFanSpeed(fanId);
            }
        }
    });
    
    console.log('Temperature Control System initialized successfully');
});

// Initialize COM port controls
function initComPortControls() {
    const reconnectButton = document.getElementById('reconnect-arduino');
    const comPortSelect = document.getElementById('com-port-select');
    const setPollingButton = document.getElementById('set-polling-interval');
    
    if (reconnectButton) {
        reconnectButton.addEventListener('click', function() {
            reconnectArduino();
        });
    }
    
    if (comPortSelect) {
        comPortSelect.addEventListener('change', function() {
            if (this.value) {
                reconnectArduino(this.value);
            }
        });
    }
    
    if (setPollingButton) {
        setPollingButton.addEventListener('click', function() {
            setPollingInterval();
        });
    }
    
    // Add Enter key support for polling interval input
    const pollingInput = document.getElementById('polling-interval');
    if (pollingInput) {
        pollingInput.addEventListener('keypress', function(event) {
            if (event.key === 'Enter') {
                setPollingInterval();
            }
        });
    }
}

// Handle page visibility changes
document.addEventListener('visibilitychange', function() {
    if (document.hidden) {
        // Page is hidden, reduce update frequency
        if (ws) {
            ws.send('pause');
        }
    } else {
        // Page is visible, resume updates
        if (ws) {
            ws.send('resume');
        }
    }
});

// Cleanup on page unload
window.addEventListener('beforeunload', function() {
    if (ws) {
        ws.close();
    }
});

// Manual Control Functions
function initManualControls() {
    // Hot plate manual controls
    for (let i = 0; i < 2; i++) {
        // Manual control toggle
        const manualToggle = document.getElementById(`manual-hotplate-${i}`);
        if (manualToggle) {
            manualToggle.addEventListener('change', function() {
                manualControlState.hotplates[i] = this.checked;
                setManualControlToggle('hotplate', i, this.checked);
                updateManualControlUI();
            });
        }
        
        // Hot plate state toggle
        const stateToggle = document.getElementById(`manual-hotplate-${i}-state`);
        if (stateToggle) {
            stateToggle.addEventListener('change', function() {
                if (manualControlState.hotplates[i]) {
                    setManualHotPlateState(i, this.checked);
                }
            });
        }
        
        // Temperature input
        const tempInput = document.getElementById(`manual-hotplate-${i}-temp`);
        if (tempInput) {
            tempInput.addEventListener('change', function() {
                if (manualControlState.hotplates[i]) {
                    setManualHotPlateTemp(i, parseFloat(this.value));
                }
            });
        }
    }
    
    // Fan manual controls
    for (let i = 0; i < 4; i++) {
        // Manual control toggle
        const manualToggle = document.getElementById(`manual-fan-${i}`);
        if (manualToggle) {
            manualToggle.addEventListener('change', function() {
                manualControlState.fans[i] = this.checked;
                setManualControlToggle('fan', i, this.checked);
                updateManualControlUI();
            });
        }
        
        // Fan state toggle
        const stateToggle = document.getElementById(`manual-fan-${i}-state`);
        if (stateToggle) {
            stateToggle.addEventListener('change', function() {
                if (manualControlState.fans[i]) {
                    setManualFanState(i, this.checked);
                }
            });
        }
        
        // Fan speed slider
        const speedSlider = document.getElementById(`manual-fan-${i}-speed`);
        if (speedSlider) {
            speedSlider.addEventListener('input', function() {
                const valueDisplay = document.getElementById(`fan-${i}-speed-value`);
                if (valueDisplay) {
                    valueDisplay.textContent = this.value;
                }
                if (manualControlState.fans[i]) {
                    setManualFanSpeed(i, parseInt(this.value));
                }
            });
        }
    }
}

function updateManualControls(data) {
    // Update hot plate controls
    (data.hot_plate_states || []).forEach((state, index) => {
        const stateToggle = document.getElementById(`manual-hotplate-${index}-state`);
        const stateText = document.getElementById(`hotplate-${index}-state-text`);
        
        if (stateToggle && !manualControlState.hotplates[index]) {
            stateToggle.checked = state;
        }
        if (stateText) {
            stateText.textContent = state ? 'ON' : 'OFF';
        }
        
        const tempInput = document.getElementById(`manual-hotplate-${index}-temp`);
        if (tempInput && !manualControlState.hotplates[index]) {
            tempInput.value = (data.target_temperatures && data.target_temperatures[index]) || 25;
        }
    });
    
    // Update fan controls
    (data.fan_speeds || []).forEach((speed, index) => {
        const speedSlider = document.getElementById(`manual-fan-${index}-speed`);
        const speedValue = document.getElementById(`fan-${index}-speed-value`);
        const stateToggle = document.getElementById(`manual-fan-${index}-state`);
        const stateText = document.getElementById(`fan-${index}-state-text`);
        
        if (speedSlider && !manualControlState.fans[index]) {
            speedSlider.value = speed;
        }
        if (speedValue && !manualControlState.fans[index]) {
            speedValue.textContent = speed;
        }
        if (stateToggle && !manualControlState.fans[index]) {
            stateToggle.checked = speed > 0;
        }
        if (stateText) {
            stateText.textContent = speed > 0 ? 'ON' : 'OFF';
        }
    });
}

function updateManualControlUI() {
    // Update hot plate UI
    for (let i = 0; i < 2; i++) {
        const isManual = manualControlState.hotplates[i];
        const tempInput = document.getElementById(`manual-hotplate-${i}-temp`);
        const stateToggle = document.getElementById(`manual-hotplate-${i}-state`);
        
        if (tempInput) tempInput.disabled = !isManual;
        if (stateToggle) stateToggle.disabled = !isManual;
    }
    
    // Update fan UI
    for (let i = 0; i < 4; i++) {
        const isManual = manualControlState.fans[i];
        const speedSlider = document.getElementById(`manual-fan-${i}-speed`);
        const stateToggle = document.getElementById(`manual-fan-${i}-state`);
        
        if (speedSlider) speedSlider.disabled = !isManual;
        if (stateToggle) stateToggle.disabled = !isManual;
    }
}

function updateDeviceStatus(data) {
    // Update device connection status based on sensor data
    const temperatures = data.temperatures || [];
    
    // Check hot plates (assuming they're connected if corresponding sensors work)
    for (let i = 0; i < 2; i++) {
        const statusElement = document.getElementById(`hotplate-${i}-device-status`);
        if (statusElement) {
            // With 5 sensors, use sensor 0 for hot plate 0 and sensor 2 for hot plate 1
            const sensorIndex = i === 0 ? 0 : 2;
            const isConnected = sensorIndex < temperatures.length && 
                              temperatures[sensorIndex] > -100;
            statusElement.textContent = isConnected ? 'Connected' : 'Not connected';
            statusElement.className = isConnected ? 'text-success' : 'text-danger';
        }
    }
    
    // Check fans (assume all fans are connected if system is ready)
    for (let i = 0; i < 4; i++) {
        const statusElement = document.getElementById(`fan-${i}-device-status`);
        if (statusElement) {
            const isConnected = data.system_ready || false;
            statusElement.textContent = isConnected ? 'Connected' : 'Not connected';
            statusElement.className = isConnected ? 'text-success' : 'text-danger';
        }
    }
}

async function setManualHotPlateState(plateId, state) {
    try {
        await apiCall(`/api/hotplate/${plateId}/toggle`, 'POST', { state: state });
        console.log(`Manual hot plate ${plateId + 1} set to ${state}`);
    } catch (error) {
        console.error('Failed to set manual hot plate state:', error);
    }
}

async function setManualHotPlateTemp(plateId, temperature) {
    try {
        await apiCall('/api/temperature/set', 'POST', {
            sensor: plateId,
            target: temperature
        });
        console.log(`Manual hot plate ${plateId + 1} temperature set to ${temperature}°C`);
    } catch (error) {
        console.error('Failed to set manual hot plate temperature:', error);
    }
}

async function setManualFanState(fanId, state) {
    try {
        const speed = state ? 128 : 0; // 50% speed when turned on manually
        await apiCall('/api/fan/set', 'POST', {
            fan: fanId,
            speed: speed
        });
        
        // Update slider
        const speedSlider = document.getElementById(`manual-fan-${fanId}-speed`);
        const speedValue = document.getElementById(`fan-${fanId}-speed-value`);
        if (speedSlider) speedSlider.value = speed;
        if (speedValue) speedValue.textContent = speed;
        
        console.log(`Manual fan ${fanId + 1} set to ${state ? 'ON' : 'OFF'}`);
    } catch (error) {
        console.error('Failed to set manual fan state:', error);
    }
}

async function setManualFanSpeed(fanId, speed) {
    try {
        await apiCall('/api/fan/set', 'POST', {
            fan: fanId,
            speed: speed
        });
        
        // Update state toggle
        const stateToggle = document.getElementById(`manual-fan-${fanId}-state`);
        const stateText = document.getElementById(`fan-${fanId}-state-text`);
        if (stateToggle) stateToggle.checked = speed > 0;
        if (stateText) stateText.textContent = speed > 0 ? 'ON' : 'OFF';
        
        console.log(`Manual fan ${fanId + 1} speed set to ${speed}`);
    } catch (error) {
        console.error('Failed to set manual fan speed:', error);
    }
}

async function setManualControlToggle(deviceType, deviceId, manual) {
    try {
        const endpoint = deviceType === 'hotplate' ? 
            `/api/manual/hotplate/${deviceId}` : 
            `/api/manual/fan/${deviceId}`;
        
        await apiCall(endpoint, 'POST', manual);
        console.log(`Manual control for ${deviceType} ${deviceId + 1} set to ${manual}`);
    } catch (error) {
        console.error(`Failed to set manual control for ${deviceType}:`, error);
    }
}

// Arduino COM Port Management
async function reconnectArduino(newPort = null) {
    const reconnectButton = document.getElementById('reconnect-arduino');
    const originalText = reconnectButton.innerHTML;
    
    try {
        // Show loading state
        reconnectButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Connecting...';
        reconnectButton.disabled = true;
        
        const port = newPort || document.getElementById('com-port-select').value;
        
        // Send correct JSON format
        const requestBody = port ? { port: port } : {};
        
        const response = await apiCall('/api/arduino/reconnect', 'POST', requestBody);
        
        if (response.status === 'success') {
            showErrorMessage('Arduino reconnected successfully!', 'success');
            console.log('Arduino reconnected to port:', port);
        } else {
            showErrorMessage('Failed to reconnect Arduino: ' + response.message);
        }
        
    } catch (error) {
        console.error('Failed to reconnect Arduino:', error);
        showErrorMessage('Failed to reconnect Arduino: ' + error.message);
    } finally {
        // Restore button state
        reconnectButton.innerHTML = originalText;
        reconnectButton.disabled = false;
    }
}

// Polling Interval Management
async function setPollingInterval() {
    const intervalInput = document.getElementById('polling-interval');
    const setButton = document.getElementById('set-polling-interval');
    const originalText = setButton.innerHTML;
    
    try {
        const interval = parseFloat(intervalInput.value);
        
        if (interval < 0.5 || interval > 60) {
            showErrorMessage('Polling interval must be between 0.5 and 60 seconds');
            return;
        }
        
        // Show loading state
        setButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Setting...';
        setButton.disabled = true;
        
        const response = await apiCall('/api/polling_interval', 'POST', interval);
        
        if (response.status === 'success') {
            showErrorMessage('Polling interval updated successfully!', 'success');
            console.log('Polling interval set to:', interval + 's');
            
            // Update display
            const displayElement = document.getElementById('polling-interval-display');
            if (displayElement) {
                displayElement.textContent = interval + 's';
            }
        } else {
            showErrorMessage('Failed to set polling interval: ' + response.message);
        }
        
    } catch (error) {
        console.error('Failed to set polling interval:', error);
        showErrorMessage('Failed to set polling interval: ' + error.message);
    } finally {
        // Restore button state
        setButton.innerHTML = originalText;
        setButton.disabled = false;
    }
}
