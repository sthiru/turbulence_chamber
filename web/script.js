// Global variables
let ws;

// Configuration
const CONFIG = {
    MAX_TEMP: 80,
    WARNING_TEMP: 50,
    DANGER_TEMP: 70,
    UPDATE_INTERVAL: 2000,
    CHART_MAX_POINTS: 150, // 5 minutes at 2-second intervals
    CHART_DURATION: 300000, // 5 minutes in milliseconds
    NUM_SENSORS: 12,
    SENSOR_COLORS: [
        '#FF6384', // Red
        '#36A2EB', // Blue  
        '#FFCE56', // Yellow
        '#4BC0C0', // Teal
        '#9966FF', // Purple
        '#FF9F40', // Orange
        '#FF6384', // Red
        '#C9CBCF', // Gray
        '#4BC0C0', // Teal
        '#36A2EB', // Blue
        '#FFCE56', // Yellow
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
                } else if (data.type === 'historical_data') {
                    // Handle complete historical data (first time)
                    console.log('Historical data message received, records:', data.count);
                    
                    // Update with latest data for all displays
                    if (data.data && data.data.length > 0) {
                        const latestData = data.data[data.data.length - 1];
                        updateHotPlateControls(latestData.target_temperatures || [], latestData.hot_plate_states || []);
                        updateFanControls(latestData.fan_speeds || []);
                    }
                } else if (data.type === 'current_data') {
                    // Handle current data updates (subsequent messages)
                    console.log('Current data message received, records:', data.count);
                    
                    // Update with latest data for all displays
                    if (data.data && data.data.length > 0) {
                        const latestData = data.data[data.data.length - 1];
                        updateHotPlateControls(latestData.target_temperatures || [], latestData.hot_plate_states || []);
                        updateFanControls(latestData.fan_speeds || []);
                    }
                }
            } catch (error) {
                console.error('Error parsing WebSocket data:', error);
                showErrorMessage('Invalid data received from server');
            }
        };
        
        ws.onclose = function(event) {
            console.log('WebSocket disconnected, code:', event.code, 'reason:', event.reason);
            // Try to reconnect after 3 seconds
            setTimeout(initWebSocket, 3000);
        };
        
        ws.onerror = function(error) {
            console.error('WebSocket error:', error);
            showErrorMessage('Connection error. Please check if the server is running on port 8000.');
        };
    } catch (error) {
        console.error('Error creating WebSocket:', error);
        showErrorMessage('Failed to establish connection to server. Please check if the server is running.');
    }
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
