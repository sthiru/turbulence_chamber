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
                        // Update temperature inputs with target temperatures
                        if (latestData.target_temperatures) {
                            latestData.target_temperatures.forEach((target, index) => {
                                const tempInput = document.getElementById(`target-temp-${index}`);
                                if (tempInput) {
                                    tempInput.value = target;
                                }
                            });
                        }
                    }
                } else if (data.type === 'current_data') {
                    // Handle current data updates (subsequent messages)
                    console.log('Current data message received, records:', data.count);
                    
                    // Update with latest data for all displays
                    if (data.data && data.data.length > 0) {
                        const latestData = data.data[data.data.length - 1];
                        // Update temperature inputs with target temperatures
                        if (latestData.target_temperatures) {
                            latestData.target_temperatures.forEach((target, index) => {
                                const tempInput = document.getElementById(`target-temp-${index}`);
                                if (tempInput) {
                                    tempInput.value = target;
                                }
                            });
                        }
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
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        return await response.json();
    } catch (error) {
        console.error('API call error:', error);
        showErrorMessage(`API Error: ${error.message}`);
        throw error;
    }
}

async function saveTemperatureSettings() {
    const targetTemp0 = parseFloat(document.getElementById('target-temp-0').value);
    const targetTemp1 = parseFloat(document.getElementById('target-temp-1').value);
    const safetyTemp = parseFloat(document.getElementById('safety-temp').value);
    const pidKp = parseFloat(document.getElementById('pid-kp').value);
    const pidKi = parseFloat(document.getElementById('pid-ki').value);
    const pidKd = parseFloat(document.getElementById('pid-kd').value);
    
    try {
        await apiCall('/api/temperature/settings', 'POST', {
            target_temperatures: [targetTemp0, targetTemp1],
            safety_temperature: safetyTemp,
            pid_parameters: {
                kp: pidKp,
                ki: pidKi,
                kd: pidKd
            }
        });
        showErrorMessage('Temperature settings saved successfully!', 'success');
    } catch (error) {
        console.error('Failed to save temperature settings:', error);
        showErrorMessage('Failed to save temperature settings');
    }
}

async function saveFanSettings() {
    const startBehaviour = document.getElementById('fan-start-behaviour').value;
    
    try {
        await apiCall('/api/fan/settings', 'POST', {
            start_behaviour: startBehaviour
        });
        showErrorMessage('Fan settings saved successfully!', 'success');
    } catch (error) {
        console.error('Failed to save fan settings:', error);
        showErrorMessage('Failed to save fan settings');
    }
}

async function saveAllSettings() {
    const targetTemp0 = parseFloat(document.getElementById('target-temp-0').value);
    const targetTemp1 = parseFloat(document.getElementById('target-temp-1').value);
    const safetyTemp = parseFloat(document.getElementById('safety-temp').value);
    const pidKp = parseFloat(document.getElementById('pid-kp').value);
    const pidKi = parseFloat(document.getElementById('pid-ki').value);
    const pidKd = parseFloat(document.getElementById('pid-kd').value);
    const startBehaviour = document.getElementById('fan-start-behaviour').value;
    const arduinoPort = document.getElementById('com-port-select').value;
    const pollingInterval = parseFloat(document.getElementById('polling-interval').value);
    const ambientPollingInterval = parseFloat(document.getElementById('ambient-polling-interval').value);
    const historySize = parseInt(document.getElementById('history-size').value);
    
    try {
        await apiCall('/api/settings', 'POST', {
            target_temperatures: [targetTemp0, targetTemp1],
            safety_temperature: safetyTemp,
            pid_parameters: {
                kp: pidKp,
                ki: pidKi,
                kd: pidKd
            },
            fan_start_behaviour: startBehaviour,
            arduino_port: arduinoPort,
            polling_interval: pollingInterval,
            ambient_polling_interval: ambientPollingInterval,
            history_size: historySize
        });
        showErrorMessage('All configuration settings saved successfully!', 'success');
    } catch (error) {
        console.error('Failed to save all settings:', error);
        showErrorMessage('Failed to save all configuration settings');
    }
}

async function loadSettings() {
    try {
        const settings = await apiCall('/api/settings', 'GET');
        
        if (settings.error) {
            console.error('Failed to load settings:', settings.error);
            return;
        }
        
        // Load temperature settings
        if (settings.target_temperatures) {
            const temp0Input = document.getElementById('target-temp-0');
            const temp1Input = document.getElementById('target-temp-1');
            if (temp0Input && settings.target_temperatures[0] !== undefined) {
                temp0Input.value = settings.target_temperatures[0];
            }
            if (temp1Input && settings.target_temperatures[1] !== undefined) {
                temp1Input.value = settings.target_temperatures[1];
            }
        }
        
        // Load safety temperature
        if (settings.safety_temperature !== undefined) {
            const safetyTempInput = document.getElementById('safety-temp');
            if (safetyTempInput) {
                safetyTempInput.value = settings.safety_temperature;
            }
        }
        
        // Load PID parameters
        if (settings.pid_parameters) {
            const kpInput = document.getElementById('pid-kp');
            const kiInput = document.getElementById('pid-ki');
            const kdInput = document.getElementById('pid-kd');
            if (kpInput && settings.pid_parameters.kp !== undefined) {
                kpInput.value = settings.pid_parameters.kp;
            }
            if (kiInput && settings.pid_parameters.ki !== undefined) {
                kiInput.value = settings.pid_parameters.ki;
            }
            if (kdInput && settings.pid_parameters.kd !== undefined) {
                kdInput.value = settings.pid_parameters.kd;
            }
        }
        
        // Load fan start behaviour
        if (settings.fan_start_behaviour) {
            const fanBehaviourSelect = document.getElementById('fan-start-behaviour');
            if (fanBehaviourSelect) {
                fanBehaviourSelect.value = settings.fan_start_behaviour;
            }
        }
        
        // Load Arduino port
        if (settings.arduino_port !== undefined) {
            const comPortSelect = document.getElementById('com-port-select');
            if (comPortSelect) {
                comPortSelect.value = settings.arduino_port;
            }
        }
        
        // Load polling interval
        if (settings.polling_interval !== undefined) {
            const pollingIntervalInput = document.getElementById('polling-interval');
            if (pollingIntervalInput) {
                pollingIntervalInput.value = settings.polling_interval;
            }
        }
        
        // Load ambient polling interval
        if (settings.ambient_polling_interval !== undefined) {
            const ambientPollingIntervalInput = document.getElementById('ambient-polling-interval');
            if (ambientPollingIntervalInput) {
                ambientPollingIntervalInput.value = settings.ambient_polling_interval;
            }
        }
        
        // Load history size
        if (settings.history_size !== undefined) {
            const historySizeInput = document.getElementById('history-size');
            if (historySizeInput) {
                historySizeInput.value = settings.history_size;
            }
        }
        
        console.log('Settings loaded successfully');
    } catch (error) {
        console.error('Failed to load settings:', error);
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
    
    // Initialize WebSocket
    initWebSocket();
    
    // Initialize COM port controls
    initComPortControls();
    
    // Load saved settings
    loadSettings();
    
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
