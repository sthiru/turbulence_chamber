// Global variables
let ws;
let tempChart;
let tempData = {
    labels: [],
    datasets: []
};

// Configuration
const CONFIG = {
    MAX_TEMP: 80,
    WARNING_TEMP: 50,
    DANGER_TEMP: 70,
    UPDATE_INTERVAL: 2000,
    CHART_MAX_POINTS: 20
};

// Initialize WebSocket connection
function initWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/status`;
    
    try {
        ws = new WebSocket(wsUrl);
        
        ws.onopen = function() {
            updateConnectionStatus('online', 'Connected');
            console.log('WebSocket connected');
            hideErrorMessage();
        };
        
        ws.onmessage = function(event) {
            try {
                const data = JSON.parse(event.data);
                updateDisplay(data);
            } catch (error) {
                console.error('Error parsing WebSocket data:', error);
                showErrorMessage('Invalid data received from server');
            }
        };
        
        ws.onclose = function(event) {
            updateConnectionStatus('offline', 'Disconnected');
            console.log('WebSocket disconnected, code:', event.code);
            // Try to reconnect after 3 seconds
            setTimeout(initWebSocket, 3000);
        };
        
        ws.onerror = function(error) {
            updateConnectionStatus('error', 'Connection Error');
            console.error('WebSocket error:', error);
            showErrorMessage('Connection error. Please check server status.');
        };
    } catch (error) {
        console.error('Error creating WebSocket:', error);
        updateConnectionStatus('error', 'Connection Failed');
        showErrorMessage('Failed to establish connection to server');
    }
}

// Update connection status
function updateConnectionStatus(status, text) {
    const statusElement = document.getElementById('connection-status');
    statusElement.className = `badge bg-${status === 'online' ? 'success' : status === 'offline' ? 'danger' : 'warning'}`;
    statusElement.innerHTML = `<i class="fas fa-circle"></i> ${text}`;
}

// Show/hide error messages
function showErrorMessage(message) {
    const errorElement = document.getElementById('error-message');
    errorElement.textContent = message;
    errorElement.classList.remove('d-none');
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
        
    } catch (error) {
        console.error('Error updating display:', error);
        showErrorMessage('Error updating display');
    }
}

// Update system status
function updateSystemStatus(data) {
    const systemReadyElement = document.getElementById('system-ready');
    const deviceStatusElement = document.getElementById('device-status');
    
    systemReadyElement.textContent = data.system_ready ? 'Yes' : 'No';
    systemReadyElement.className = data.system_ready ? 'text-success' : 'text-danger';
    
    deviceStatusElement.textContent = data.device_status || 'Unknown';
    
    // Update device status color
    const statusClass = data.device_status === 'online' ? 'text-success' : 
                       data.device_status === 'offline' ? 'text-danger' : 'text-warning';
    deviceStatusElement.className = statusClass;
    
    // Show error message if present
    if (data.error) {
        showErrorMessage(data.error);
    } else {
        hideErrorMessage();
    }
}

// Update temperature sensor display
function updateTemperatureSensors(temperatures) {
    const container = document.getElementById('temperature-sensors');
    container.innerHTML = '';
    
    temperatures.forEach((temp, index) => {
        const tempClass = getTemperatureClass(temp);
        const tempValue = temp < -100 ? 'Error' : `${temp.toFixed(1)}°C`;
        const icon = getTemperatureIcon(temp);
        
        const sensorHtml = `
            <div class="col-md-6 mb-3">
                <div class="card sensor-card h-100">
                    <div class="card-body text-center">
                        <h6 class="card-title">
                            <i class="fas ${icon}"></i> Sensor ${index + 1}
                        </h6>
                        <div class="temp-display ${tempClass}">${tempValue}</div>
                        ${temp >= 0 && temp < 100 ? `<small class="text-muted">${getTemperatureStatus(temp)}</small>` : ''}
                    </div>
                </div>
            </div>
        `;
        container.innerHTML += sensorHtml;
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
    const container = document.getElementById('hot-plate-controls');
    container.innerHTML = '';
    
    targetTemps.forEach((target, index) => {
        const plateHtml = `
            <div class="row align-items-center mb-3 p-2 border rounded">
                <div class="col-md-3">
                    <label class="form-label fw-bold">
                        <i class="fas fa-fire"></i> Hot Plate ${index + 1}
                    </label>
                </div>
                <div class="col-md-3">
                    <div class="input-group">
                        <input type="number" class="form-control" id="target-temp-${index}" 
                               value="${target}" min="0" max="${CONFIG.MAX_TEMP}" step="0.5">
                        <span class="input-group-text">°C</span>
                    </div>
                </div>
                <div class="col-md-3">
                    <button class="btn btn-${states[index] ? 'danger' : 'success'} w-100" 
                            onclick="toggleHotPlate(${index})"
                            id="hotplate-btn-${index}">
                        <i class="fas fa-power-off"></i> ${states[index] ? 'TURN OFF' : 'TURN ON'}
                    </button>
                </div>
                <div class="col-md-3">
                    <button class="btn btn-primary w-100" onclick="setTemperature(${index})">
                        <i class="fas fa-thermometer-half"></i> SET TEMP
                    </button>
                </div>
            </div>
        `;
        container.innerHTML += plateHtml;
    });
}

// Update fan controls
function updateFanControls(speeds) {
    const container = document.getElementById('fan-controls');
    container.innerHTML = '';
    
    speeds.forEach((speed, index) => {
        const percentage = Math.round((speed / 255) * 100);
        const fanHtml = `
            <div class="row align-items-center mb-3 p-2 border rounded">
                <div class="col-md-3">
                    <label class="form-label fw-bold">
                        <i class="fas fa-fan"></i> Fan ${index + 1}
                    </label>
                </div>
                <div class="col-md-6">
                    <input type="range" class="form-range fan-control" id="fan-speed-${index}" 
                           min="0" max="255" value="${speed}" 
                           oninput="updateFanDisplay(${index}, this.value)">
                    <div class="d-flex justify-content-between">
                        <small class="text-muted">Speed: <span id="fan-display-${index}">${speed}</span>/255</small>
                        <small class="text-muted">${percentage}%</small>
                    </div>
                </div>
                <div class="col-md-3">
                    <button class="btn btn-primary w-100" onclick="setFanSpeed(${index})">
                        <i class="fas fa-fan"></i> APPLY
                    </button>
                </div>
            </div>
        `;
        container.innerHTML += fanHtml;
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

// Update temperature chart
function updateChart(temperatures) {
    if (!tempChart) return;
    
    const now = new Date().toLocaleTimeString();
    
    // Add new time label
    if (tempData.labels.length >= CONFIG.CHART_MAX_POINTS) {
        tempData.labels.shift();
        tempData.datasets.forEach(dataset => dataset.data.shift());
    }
    tempData.labels.push(now);
    
    // Update datasets
    temperatures.forEach((temp, index) => {
        if (!tempData.datasets[index]) {
            tempData.datasets[index] = {
                label: `Sensor ${index + 1}`,
                data: [],
                borderColor: `hsl(${index * 60}, 70%, 50%)`,
                backgroundColor: `hsla(${index * 60}, 70%, 50%, 0.1)`,
                tension: 0.1,
                borderWidth: 2
            };
        }
        
        if (tempData.datasets[index].data.length >= CONFIG.CHART_MAX_POINTS) {
            tempData.datasets[index].data.shift();
        }
        tempData.datasets[index].data.push(temp);
    });
    
    tempChart.update();
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
        await apiCall(`/api/hotplate/${plateId}/toggle`, 'POST', newState);
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
    
    console.log('Temperature Control System initialized successfully');
});

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
