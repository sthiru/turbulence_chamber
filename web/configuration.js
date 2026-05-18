// Configuration page specific JavaScript

// Global variables
let ws;

// API call function
async function apiCall(endpoint, method = 'GET', data = null) {
    const options = {
        method,
        headers: {
            'Content-Type': 'application/json'
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
}

// Show error message
function showErrorMessage(message, type = 'error') {
    const errorDiv = document.getElementById('error-message');
    if (errorDiv) {
        errorDiv.textContent = message;
        errorDiv.className = `alert alert-${type} alert-sm mb-3`;
        errorDiv.classList.remove('d-none');
        
        // Auto-hide after 5 seconds
        setTimeout(() => {
            errorDiv.classList.add('d-none');
        }, 5000);
    }
}

// Hide error message
function hideErrorMessage() {
    const errorDiv = document.getElementById('error-message');
    if (errorDiv) {
        errorDiv.classList.add('d-none');
    }
}

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
                    // Ignore ping messages
                    return;
                }
                
                // Update system status if present
                if (data.device_status) {
                    const deviceStatus = document.getElementById('device-status');
                    if (deviceStatus) {
                        deviceStatus.textContent = data.device_status;
                    }
                }
                
                if (data.arduino_port) {
                    const arduinoPort = document.getElementById('arduino-port');
                    if (arduinoPort) {
                        arduinoPort.textContent = data.arduino_port;
                    }
                }
                
            } catch (error) {
                console.error('Error parsing WebSocket message:', error);
            }
        };
        
        ws.onclose = function() {
            console.log('WebSocket disconnected');
            // Attempt to reconnect after 3 seconds
            setTimeout(initWebSocket, 3000);
        };
        
        ws.onerror = function(error) {
            console.error('WebSocket error:', error);
            showErrorMessage('WebSocket connection error');
        };
        
    } catch (error) {
        console.error('Failed to create WebSocket connection:', error);
        showErrorMessage('Failed to initialize WebSocket');
    }
}

// Initialize COM port controls
function initComPortControls() {
    const reconnectButton = document.getElementById('reconnect-arduino');
    if (reconnectButton) {
        reconnectButton.addEventListener('click', async function() {
            try {
                showErrorMessage('Reconnecting to Arduino...', 'info');
                const response = await apiCall('/api/arduino/reconnect', 'POST');
                if (response.status === 'success') {
                    showErrorMessage('Arduino reconnected successfully', 'success');
                } else {
                    showErrorMessage('Failed to reconnect Arduino');
                }
            } catch (error) {
                console.error('Failed to reconnect Arduino:', error);
                showErrorMessage('Failed to reconnect Arduino');
            }
        });
    }
    
    const setPollingIntervalButton = document.getElementById('set-polling-interval');
    if (setPollingIntervalButton) {
        setPollingIntervalButton.addEventListener('click', async function() {
            const interval = parseFloat(document.getElementById('polling-interval').value);
            try {
                await saveAllSettings();
                showErrorMessage('Polling interval updated', 'success');
            } catch (error) {
                console.error('Failed to set polling interval:', error);
                showErrorMessage('Failed to set polling interval');
            }
        });
    }
    
    const setAmbientPollingIntervalButton = document.getElementById('set-ambient-polling-interval');
    if (setAmbientPollingIntervalButton) {
        setAmbientPollingIntervalButton.addEventListener('click', async function() {
            const interval = parseFloat(document.getElementById('ambient-polling-interval').value);
            try {
                await saveAllSettings();
                showErrorMessage('Ambient polling interval updated', 'success');
            } catch (error) {
                console.error('Failed to set ambient polling interval:', error);
                showErrorMessage('Failed to set ambient polling interval');
            }
        });
    }
    
    const setHistorySizeButton = document.getElementById('set-history-size');
    if (setHistorySizeButton) {
        setHistorySizeButton.addEventListener('click', async function() {
            const size = parseInt(document.getElementById('history-size').value);
            try {
                await saveAllSettings();
                showErrorMessage('History size updated', 'success');
            } catch (error) {
                console.error('Failed to set history size:', error);
                showErrorMessage('Failed to set history size');
            }
        });
    }
}

// Save all settings
async function saveAllSettings() {
    const targetTemp0 = parseFloat(document.getElementById('target-temp-0').value);
    const targetTemp1 = parseFloat(document.getElementById('target-temp-1').value);
    const safetyTemp = parseFloat(document.getElementById('safety-temp').value);
    const pidKp0 = parseFloat(document.getElementById('pid-kp-0').value);
    const pidKi0 = parseFloat(document.getElementById('pid-ki-0').value);
    const pidKd0 = parseFloat(document.getElementById('pid-kd-0').value);
    const pidKp1 = parseFloat(document.getElementById('pid-kp-1').value);
    const pidKi1 = parseFloat(document.getElementById('pid-ki-1').value);
    const pidKd1 = parseFloat(document.getElementById('pid-kd-1').value);
    const startBehaviour = document.getElementById('fan-start-behaviour').value;
    const arduinoPort = document.getElementById('com-port-select').value;
    const pollingInterval = parseFloat(document.getElementById('polling-interval').value);
    const ambientPollingInterval = parseFloat(document.getElementById('ambient-polling-interval').value);
    const historySize = parseInt(document.getElementById('history-size').value);
    const debugEnabled = document.getElementById('debug-enabled').checked;
    
    try {
        await apiCall('/api/settings', 'POST', {
            target_temperatures: [targetTemp0, targetTemp1],
            safety_temperature: safetyTemp,
            pid_parameters: {
                hotplate_0: {kp: pidKp0, ki: pidKi0, kd: pidKd0},
                hotplate_1: {kp: pidKp1, ki: pidKi1, kd: pidKd1}
            },
            fan_start_behaviour: startBehaviour,
            arduino_port: arduinoPort,
            polling_interval: pollingInterval,
            ambient_polling_interval: ambientPollingInterval,
            history_size: historySize,
            debug_enabled: debugEnabled
        });
        showErrorMessage('All configuration settings saved successfully!', 'success');
    } catch (error) {
        console.error('Failed to save all settings:', error);
        showErrorMessage('Failed to save all configuration settings');
    }
}

// Load settings from server
async function loadSettings() {
    try {
        const settings = await apiCall('/api/settings', 'GET');
        
        if (settings.error) {
            console.error('Failed to load settings:', settings.error);
            return;
        }
        
        console.log('Loaded settings:', settings);
        
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
            // Load Hot Plate 0 PID parameters
            if (settings.pid_parameters.hotplate_0) {
                const kp0Input = document.getElementById('pid-kp-0');
                const ki0Input = document.getElementById('pid-ki-0');
                const kd0Input = document.getElementById('pid-kd-0');
                if (kp0Input && settings.pid_parameters.hotplate_0.kp !== undefined) {
                    kp0Input.value = settings.pid_parameters.hotplate_0.kp;
                }
                if (ki0Input && settings.pid_parameters.hotplate_0.ki !== undefined) {
                    ki0Input.value = settings.pid_parameters.hotplate_0.ki;
                }
                if (kd0Input && settings.pid_parameters.hotplate_0.kd !== undefined) {
                    kd0Input.value = settings.pid_parameters.hotplate_0.kd;
                }
            }
            
            // Load Hot Plate 1 PID parameters
            if (settings.pid_parameters.hotplate_1) {
                const kp1Input = document.getElementById('pid-kp-1');
                const ki1Input = document.getElementById('pid-ki-1');
                const kd1Input = document.getElementById('pid-kd-1');
                if (kp1Input && settings.pid_parameters.hotplate_1.kp !== undefined) {
                    kp1Input.value = settings.pid_parameters.hotplate_1.kp;
                }
                if (ki1Input && settings.pid_parameters.hotplate_1.ki !== undefined) {
                    ki1Input.value = settings.pid_parameters.hotplate_1.ki;
                }
                if (kd1Input && settings.pid_parameters.hotplate_1.kd !== undefined) {
                    kd1Input.value = settings.pid_parameters.hotplate_1.kd;
                }
            }
            
            // Fallback to old single PID parameter structure if present
            if (settings.pid_parameters.kp !== undefined) {
                const kp0Input = document.getElementById('pid-kp-0');
                const kp1Input = document.getElementById('pid-kp-1');
                if (kp0Input) kp0Input.value = settings.pid_parameters.kp;
                if (kp1Input) kp1Input.value = settings.pid_parameters.kp;
            }
            if (settings.pid_parameters.ki !== undefined) {
                const ki0Input = document.getElementById('pid-ki-0');
                const ki1Input = document.getElementById('pid-ki-1');
                if (ki0Input) ki0Input.value = settings.pid_parameters.ki;
                if (ki1Input) ki1Input.value = settings.pid_parameters.ki;
            }
            if (settings.pid_parameters.kd !== undefined) {
                const kd0Input = document.getElementById('pid-kd-0');
                const kd1Input = document.getElementById('pid-kd-1');
                if (kd0Input) kd0Input.value = settings.pid_parameters.kd;
                if (kd1Input) kd1Input.value = settings.pid_parameters.kd;
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
        
        // Load debug enabled
        if (settings.debug_enabled !== undefined) {
            const debugEnabledInput = document.getElementById('debug-enabled');
            if (debugEnabledInput) {
                debugEnabledInput.checked = settings.debug_enabled;
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
        showErrorMessage('Failed to load settings from server');
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    console.log('Initializing Configuration Page...');
    
    // Initialize WebSocket
    initWebSocket();
    
    // Initialize COM port controls
    initComPortControls();
    
    // Load saved settings
    loadSettings();
    
    console.log('Configuration page initialized');
});
