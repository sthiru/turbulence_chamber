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
    NUM_SENSORS: 5,
    SENSOR_COLORS: [
        '#FF6384', // Red
        '#36A2EB', // Blue  
        '#FFCE56', // Yellow
        '#4BC0C0', // Teal
        '#9966FF'  // Purple
    ]
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
                
                // Handle different message types
                if (data.type === 'ping') {
                    console.log('Ping message received, ignoring');
                    return;
                } else if (data.type === 'system_status') {
                    // Update system status immediately for fast footer update
                    console.log('System status message received');
                    updateSystemStatus(data);
                    updateConnectionStatus(data.device_status, 'Connected');
                } else if (data.type === 'historical_data') {
                    // Handle complete historical data (first time)
                    console.log('Historical data message received, records:', data.count);
                    
                    // Update with latest data for all displays
                    if (data.data && data.data.length > 0) {
                        const latestData = data.data[data.data.length - 1];
                        updateTemperatureSensors(latestData.temperatures || []);
                        updateHotPlateControls(latestData.target_temperatures || [], latestData.hot_plate_states || []);
                        updateFanControls(latestData.fan_speeds || []);
                        updateDeviceStatus({}); // Empty since system status is in separate message
                        updateChart(data.data.slice(-50)); // Update chart with last 50 records
                        updateBMESensors(latestData); // Update BME280 sensors
                        updateCN2Display(latestData.cn2 || 0.0); // Update CN² display
                    }
                } else if (data.type === 'current_data') {
                    // Handle current data updates (subsequent messages)
                    console.log('Current data message received, records:', data.count);
                    
                    // Update with latest data for all displays
                    if (data.data && data.data.length > 0) {
                        const latestData = data.data[data.data.length - 1];
                        updateTemperatureSensors(latestData.temperatures || []);
                        updateHotPlateControls(latestData.target_temperatures || [], latestData.hot_plate_states || []);
                        updateFanControls(latestData.fan_speeds || []);
                        updateDeviceStatus({}); // Empty since system status is in separate message
                        updateChart(data.data); // Update chart with recent data only
                        updateBMESensors(latestData); // Update BME280 sensors
                        updateCN2Display(latestData.cn2 || 0.0); // Update CN² display
                    }
                } else {
                    // Handle legacy single message format
                    updateDisplay(data);
                }
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
    
    // Update main status badge
    const isReady = data.system_ready || false;
    const deviceStatus = data.device_status || 'unknown';
    const arduinoPort = data.arduino_port || 'Unknown';
    const pollingInterval = data.polling_interval || 3.0;
    
    // Update individual status elements with null checks
    if (systemReadyElement) {
        systemReadyElement.textContent = isReady ? 'Yes' : 'No';
        systemReadyElement.className = isReady ? 'text-success' : 'text-danger';
    }
    
    if (deviceStatusElement) {
        deviceStatusElement.textContent = deviceStatus;
        const deviceStatusClass = deviceStatus === 'online' ? 'text-success' : 
                                  deviceStatus === 'offline' ? 'text-danger' : 'text-warning';
        deviceStatusElement.className = deviceStatusClass;
    }
    
    // Update Arduino port display
    if (arduinoPortElement) {
        if (arduinoPort && arduinoPort !== 'Unknown') {
            arduinoPortElement.textContent = arduinoPort;
            arduinoPortElement.className = 'text-success';
        } else {
            arduinoPortElement.textContent = 'Unknown';
            arduinoPortElement.className = 'text-muted';
        }
    }
    
    // Update polling interval display
    if (pollingIntervalElement) {
        pollingIntervalElement.textContent = `${pollingInterval}s`;
    }
    
    // Update polling interval input
    const pollingInput = document.getElementById('polling-interval');
    if (pollingInput && data.polling_interval) {
        pollingInput.value = data.polling_interval;
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

// Update BME280 sensor displays
function updateBMESensors(data) {
    const bmeTemps = data.temperature_bme || [];
    const bmeHumidity = data.humidity || [];
    const bmePressure = data.pressure || [];
    
    // Update BME280 temperature displays
    bmeTemps.forEach((temp, index) => {
        const tempElement = document.getElementById(`bme-temp-${index + 1}`);
        const statusElement = document.getElementById(`bme-temp-status-${index + 1}`);
        const cardElement = tempElement?.closest('.sensor-card');
        
        if (tempElement) {
            tempElement.textContent = temp.toFixed(1) + '°C';
        }
        
        if (statusElement) {
            if (temp < -100) {
                statusElement.textContent = 'Error';
                if (cardElement) cardElement.className = 'card sensor-card h-100 border-danger';
            } else {
                statusElement.textContent = 'Normal';
                if (cardElement) {
                    cardElement.className = 'card sensor-card h-100';
                    if (temp >= CONFIG.DANGER_TEMP) {
                        cardElement.classList.add('border-danger');
                    } else if (temp >= CONFIG.WARNING_TEMP) {
                        cardElement.classList.add('border-warning');
                    } else {
                        cardElement.classList.add('border-success');
                    }
                }
            }
        }
    });
    
    // Update BME280 humidity displays
    bmeHumidity.forEach((humidity, index) => {
        const humidityElement = document.getElementById(`bme-humidity-${index + 1}`);
        if (humidityElement) {
            if (humidity < 0 || humidity > 100) {
                humidityElement.textContent = '--%';
            } else {
                humidityElement.textContent = humidity.toFixed(1) + '%';
            }
        }
    });
    
    // Update BME280 pressure displays
    bmePressure.forEach((pressure, index) => {
        const pressureElement = document.getElementById(`bme-pressure-${index + 1}`);
        if (pressureElement) {
            if (pressure < 0) {
                pressureElement.textContent = '-- hPa';
            } else {
                pressureElement.textContent = pressure.toFixed(1) + ' hPa';
            }
        }
    });
}

// Update CN² display
function updateCN2Display(cn2Value) {
    const cn2Element = document.getElementById('cn2-value');
    if (cn2Element) {
        // Format CN² value in scientific notation
        if (cn2Value === 0) {
            cn2Element.textContent = '0.00e+0';
        } else {
            cn2Element.textContent = cn2Value.toExponential(2);
        }
        
        // Add color coding based on CN² value ranges
        const cn2Container = cn2Element.closest('.cn2-container');
        if (cn2Container) {
            // Remove existing color classes
            cn2Container.classList.remove('cn2-low', 'cn2-medium', 'cn2-high');
            
            // Add color class based on value
            if (cn2Value < 1e-15) {
                cn2Container.classList.add('cn2-low');      // Green - Low turbulence
            } else if (cn2Value < 1e-13) {
                cn2Container.classList.add('cn2-medium');   // Yellow - Medium turbulence
            } else {
                cn2Container.classList.add('cn2-high');     // Red - High turbulence
            }
        }
        
        console.log(`CN² updated: ${cn2Value.toExponential(2)}`);
    }
}

// Update temperature chart with 5-minute history
function updateChart(statusData) {
    if (!tempChart) return;
    
    // Handle both single status object and array of status objects
    const statusArray = Array.isArray(statusData) ? statusData : [statusData];
    
    // Process each status record
    statusArray.forEach(status => {
        const now = status.timestamp ? new Date(status.timestamp) : new Date();
        const timestamp = now.getTime();
        const timeString = now.toLocaleTimeString();
        
        // Get temperatures from status data
        const temperatures = status.temperatures || [];
        
        // Store temperature data
        temperatureHistory.timestamps.push(timestamp);
        if (temperatureHistory.data.length === 0) {
            // Initialize data arrays for each sensor
            temperatures.forEach(() => temperatureHistory.data.push([]));
        }
        
        temperatures.forEach((temp, index) => {
            if (temperatureHistory.data[index]) {
                temperatureHistory.data[index].push(temp);
            }
        });
    });
    
    // Remove data older than 5 minutes
    const latestTimestamp = temperatureHistory.timestamps[temperatureHistory.timestamps.length - 1] || Date.now();
    const cutoffTime = latestTimestamp - CONFIG.CHART_DURATION;
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
    
    // Update each sensor dataset
    CONFIG.SENSOR_COLORS.forEach((color, index) => {
        if (index < temperatureHistory.data.length) {
            tempData.datasets[index] = {
                label: `Sensor ${index + 1}`,
                data: temperatureHistory.data[index] || [],
                borderColor: color,
                backgroundColor: color + '20',
                borderWidth: 2,
                tension: 0.4,
                fill: false
            };
        }
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
    
    if (!speedInput) {
        console.error('Speed input element not found for fan:', fanId);
        return;
    }
    
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
        
    } catch (error) {
        console.error('Failed to set fan speed:', error);
        showErrorMessage('Failed to set fan speed: ' + error.message);
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
    
    // Load saved settings
    loadSavedSettings();
    
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

// Initialize COM port controls
function initComPortControls() {
    const reconnectButton = document.getElementById('reconnect-arduino');
    const comPortSelect = document.getElementById('com-port-select');
    const setPollingButton = document.getElementById('set-polling-interval');
    const setHistorySizeButton = document.getElementById('set-history-size');
    const saveSettingsButton = document.getElementById('save-settings');
    
    if (reconnectButton) {
        reconnectButton.addEventListener('click', async function() {
            try {
                const originalText = reconnectButton.innerHTML;
                reconnectButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Reconnecting...';
                reconnectButton.disabled = true;
                
                const response = await apiCall('/api/arduino/reconnect', 'POST');
                
                if (response.status === 'success') {
                    showErrorMessage('Arduino reconnected successfully!', 'success');
                } else {
                    showErrorMessage('Failed to reconnect Arduino: ' + response.message);
                }
                
            } catch (error) {
                console.error('Failed to reconnect Arduino:', error);
                showErrorMessage('Failed to reconnect Arduino: ' + error.message);
            } finally {
                reconnectButton.innerHTML = '<i class="fas fa-sync-alt"></i> Reconnect';
                reconnectButton.disabled = false;
            }
        });
    }
    
    if (comPortSelect) {
        comPortSelect.addEventListener('change', async function() {
            const selectedPort = this.value;
            if (selectedPort) {
                try {
                    const response = await apiCall('/api/arduino/port', 'POST', { port: selectedPort });
                    
                    if (response.status === 'success') {
                        showErrorMessage(`Port changed to ${selectedPort}. Reconnecting...`, 'success');
                        // Trigger reconnect after a short delay
                        setTimeout(() => {
                            reconnectButton.click();
                        }, 1000);
                    } else {
                        showErrorMessage('Failed to change port: ' + response.message);
                    }
                } catch (error) {
                    console.error('Failed to change port:', error);
                    showErrorMessage('Failed to change port: ' + error.message);
                }
            }
        });
    }
    
    if (setPollingButton) {
        setPollingButton.addEventListener('click', setPollingInterval);
    }
    
    if (setHistorySizeButton) {
        setHistorySizeButton.addEventListener('click', async function() {
            try {
                const originalText = setHistorySizeButton.innerHTML;
                setHistorySizeButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Setting...';
                setHistorySizeButton.disabled = true;
                
                const historySize = parseInt(document.getElementById('history-size').value);
                
                if (historySize < 10 || historySize > 1000) {
                    showErrorMessage('History size must be between 10 and 1000 records', 'error');
                    return;
                }
                
                const response = await apiCall('/api/history_size', 'POST', { size: historySize });
                
                if (response.status === 'success') {
                    showErrorMessage(`History size set to ${historySize} records`, 'success');
                    updateHistoryInfo();
                } else {
                    showErrorMessage('Failed to set history size: ' + response.message);
                }
                
            } catch (error) {
                console.error('Failed to set history size:', error);
                showErrorMessage('Failed to set history size: ' + error.message);
            } finally {
                setHistorySizeButton.innerHTML = '<i class="fas fa-database"></i> Set';
                setHistorySizeButton.disabled = false;
            }
        });
    }
    
    if (saveSettingsButton) {
        saveSettingsButton.addEventListener('click', async function() {
            try {
                const originalText = saveSettingsButton.innerHTML;
                saveSettingsButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';
                saveSettingsButton.disabled = true;
                
                // Get current values
                const comPort = comPortSelect.value;
                const pollingInterval = document.getElementById('polling-interval').value;
                const historySize = document.getElementById('history-size').value;
                
                // Save settings to localStorage
                localStorage.setItem('arduino_com_port', comPort);
                localStorage.setItem('polling_interval', pollingInterval);
                localStorage.setItem('history_size', historySize);
                
                // Apply settings
                if (comPort) {
                    const portResponse = await apiCall('/api/arduino/port', 'POST', { port: comPort });
                    if (portResponse.status === 'success') {
                        console.log('COM port saved:', comPort);
                    }
                }
                
                const intervalResponse = await apiCall('/api/polling_interval', 'POST', parseFloat(pollingInterval));
                if (intervalResponse.status === 'success') {
                    console.log('Polling interval saved:', pollingInterval);
                }
                
                const historyResponse = await apiCall('/api/history_size', 'POST', { size: parseInt(historySize) });
                if (historyResponse.status === 'success') {
                    console.log('History size saved:', historySize);
                }
                
                showErrorMessage('Settings saved successfully!', 'success');
                
                // Close modal
                const modal = bootstrap.Modal.getInstance(document.getElementById('settingsModal'));
                if (modal) {
                    modal.hide();
                }
                
            } catch (error) {
                console.error('Failed to save settings:', error);
                showErrorMessage('Failed to save settings: ' + error.message);
            } finally {
                saveSettingsButton.innerHTML = '<i class="fas fa-save"></i> Save Settings';
                saveSettingsButton.disabled = false;
            }
        });
    }
}

// Update history information display
async function updateHistoryInfo() {
    try {
        const response = await apiCall('/api/history');
        if (response.status === 'success') {
            const currentSizeElement = document.getElementById('current-history-size');
            const recordCountElement = document.getElementById('current-record-count');
            
            if (currentSizeElement) {
                currentSizeElement.textContent = response.max_size || 100;
            }
            
            if (recordCountElement) {
                recordCountElement.textContent = response.count || 0;
            }
        }
    } catch (error) {
        console.error('Failed to get history info:', error);
    }
}

// Load saved settings on page load
function loadSavedSettings() {
    const savedComPort = localStorage.getItem('arduino_com_port');
    const savedPollingInterval = localStorage.getItem('polling_interval');
    const savedHistorySize = localStorage.getItem('history_size');
    
    if (savedComPort) {
        const comPortSelect = document.getElementById('com-port-select');
        if (comPortSelect) {
            comPortSelect.value = savedComPort;
        }
    }
    
    if (savedPollingInterval) {
        const pollingInput = document.getElementById('polling-interval');
        if (pollingInput) {
            pollingInput.value = savedPollingInterval;
        }
    }
    
    if (savedHistorySize) {
        const historySizeInput = document.getElementById('history-size');
        if (historySizeInput) {
            historySizeInput.value = savedHistorySize;
        }
    }
    
    // Update history information display
    updateHistoryInfo();
}

// Download current data based on storage settings
async function downloadCurrentData() {
    try {
        showErrorMessage('Preparing CSV download...', 'info');
        
        // Get current history size from settings or use default
        const historySizeInput = document.getElementById('history-size');
        const historySize = historySizeInput ? parseInt(historySizeInput.value) : 100;
        
        // Download all available data (up to the current storage limit)
        const response = await fetch('/api/download/csv');
        if (!response.ok) {
            throw new Error(`Failed to download: ${response.statusText}`);
        }
        
        // Get filename from response headers or create one
        const contentDisposition = response.headers.get('Content-Disposition');
        let filename = `arduino_data_${historySize}_records_${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.csv`;
        
        if (contentDisposition) {
            const filenameMatch = contentDisposition.match(/filename="?([^"]+)"?/);
            if (filenameMatch) {
                filename = filenameMatch[1];
            }
        }
        
        // Create blob and download
        const blob = await response.blob();
        const downloadUrl = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = downloadUrl;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(downloadUrl);
        document.body.removeChild(a);
        
        showErrorMessage(`Downloaded current data as CSV`, 'success');
        
    } catch (error) {
        console.error('Download error:', error);
        showErrorMessage(`Failed to download data: ${error.message}`, 'error');
    }
}

// Download data functions
async function downloadData(limit = 'all') {
    try {
        showErrorMessage('Preparing CSV download...', 'info');
        
        let url;
        if (limit === 'all') {
            url = '/api/download/csv';
        } else {
            url = `/api/download/csv/${parseInt(limit)}`;
        }
        
        // Create download link
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error(`Failed to download: ${response.statusText}`);
        }
        
        // Get filename from response headers or create one
        const contentDisposition = response.headers.get('Content-Disposition');
        let filename = `arduino_data_${limit}_${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.csv`;
        
        if (contentDisposition) {
            const filenameMatch = contentDisposition.match(/filename="?([^"]+)"?/);
            if (filenameMatch) {
                filename = filenameMatch[1];
            }
        }
        
        // Create blob and download
        const blob = await response.blob();
        const downloadUrl = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = downloadUrl;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(downloadUrl);
        document.body.removeChild(a);
        
        showErrorMessage(`Downloaded ${limit === 'all' ? 'all records' : `last ${limit} records`} as CSV`, 'success');
        
    } catch (error) {
        console.error('Download error:', error);
        showErrorMessage(`Failed to download data: ${error.message}`, 'error');
    }
}

async function downloadJSON(limit = 'all') {
    try {
        showErrorMessage('Preparing JSON download...', 'info');
        
        let url;
        if (limit === 'all') {
            url = '/api/history';
        } else {
            url = `/api/history/${parseInt(limit)}`;
        }
        
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error(`Failed to fetch data: ${response.statusText}`);
        }
        
        const data = await response.json();
        
        // Create JSON blob
        const jsonString = JSON.stringify(data, null, 2);
        const blob = new Blob([jsonString], { type: 'application/json' });
        
        // Create download
        const filename = `arduino_data_${limit}_${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.json`;
        const downloadUrl = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = downloadUrl;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(downloadUrl);
        document.body.removeChild(a);
        
        showErrorMessage(`Downloaded ${limit === 'all' ? 'all records' : `last ${limit} records`} as JSON`, 'success');
        
    } catch (error) {
        console.error('JSON download error:', error);
        showErrorMessage(`Failed to download JSON: ${error.message}`, 'error');
    }
}
