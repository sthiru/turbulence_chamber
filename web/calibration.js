// Calibration control script
let isCalibrating = false;
let calibrationSessionId = null;
let calibrationData = [];
let polynomialCharts = {};

// DOM elements
const statusBadge = document.getElementById('calibrationStatus');
const progressBar = document.getElementById('progressBar');
const progressPercent = document.getElementById('progressPercent');
const currentStep = document.getElementById('currentStep');
const totalSteps = document.getElementById('totalSteps');
const estimatedTime = document.getElementById('estimatedTime');
const sessionId = document.getElementById('sessionId');
const stepType = document.getElementById('stepType');
const calibrationLog = document.getElementById('calibrationLog');

// Buttons
const startBtn = document.getElementById('startCalibration');
const stopBtn = document.getElementById('stopCalibration');

// Load calibration data from CSV
async function loadCalibrationData(sessionId) {
    try {
        const response = await fetch(`/api/calibration/data/${sessionId}`);
        const result = await response.json();
        
        if (result.status === 'success' && Array.isArray(result.data)) {
            return result.data;
        } else {
            addLog(result.message || 'Failed to load calibration data', 'error');
            return [];
        }
    } catch (error) {
        addLog(`Error loading calibration data: ${error}`, 'error');
        return [];
    }
}

// Load polynomial coefficients
async function loadPolynomials() {
    try {
        const response = await fetch('/api/calibration/windflow-polynomials');
        const result = await response.json();
        if (result.status === 'success') {
            return result.polynomials;
        }
        return null;
    } catch (error) {
        addLog(`Error loading polynomials: ${error}`, 'error');
        return null;
    }
}

// Load latest calibration data from root folder
async function loadLatestCalibrationData() {
    try {
        const response = await fetch('/api/calibration/data');
        const result = await response.json();

        if (result.status === 'success' && Array.isArray(result.data)) {
            calibrationData = result.data;
            populateCalibrationTable(result.data);
            document.getElementById('noDataMessage').style.display = 'none';
            document.getElementById('dataTableContainer').style.display = 'block';
            document.getElementById('downloadButtons').style.display = 'block';

            // Load session metadata to get session ID
            const metadataResponse = await fetch('/api/calibration/latest-metadata');
            const metadataResult = await metadataResponse.json();

            if (metadataResult.status === 'success' && metadataResult.metadata) {
                document.getElementById('resultsSummary').style.display = 'block';
                document.getElementById('resultsSessionId').textContent = `Session ID: ${metadataResult.metadata.session_id}`;
                calibrationSessionId = metadataResult.metadata.session_id;
                addLog('Latest calibration data loaded', 'success');
            } else if (result.data.length > 0) {
                addLog('Calibration data loaded', 'success');
            }
        }
    } catch (error) {
        addLog(`Error loading calibration data: ${error}`, 'error');
    }
}

// Populate calibration data table
function populateCalibrationTable(data) {
    const tbody = document.getElementById('calibrationDataBody');
    tbody.innerHTML = '';

    if (!Array.isArray(data)) {
        addLog('Invalid calibration data format', 'error');
        return;
    }

    if (data.length === 0) {
        addLog('No calibration data available', 'warning');
        return;
    }

    data.forEach(row => {
        const tr = document.createElement('tr');
        const fanSpeed = parseFloat(row.fan_speed);
        const sensor0 = parseFloat(row.sensor_0_avg);
        const sensor1 = parseFloat(row.sensor_1_avg);
        const sensor2 = parseFloat(row.sensor_2_avg);
        const sensor3 = parseFloat(row.sensor_3_avg);

        tr.innerHTML = `
            <td>${fanSpeed}</td>
            <td>${!isNaN(sensor0) ? sensor0.toFixed(3) : '-'}</td>
            <td>${!isNaN(sensor1) ? sensor1.toFixed(3) : '-'}</td>
            <td>${!isNaN(sensor2) ? sensor2.toFixed(3) : '-'}</td>
            <td>${!isNaN(sensor3) ? sensor3.toFixed(3) : '-'}</td>
        `;
        tbody.appendChild(tr);
    });
}

// Calculate polynomial value (coefficients in descending order from numpy polyfit)
function calculatePolynomial(x, coefficients) {
    if (!coefficients || coefficients.length === 0) return 0;
    let result = 0;
    for (let i = 0; i < coefficients.length; i++) {
        // coefficients are in descending order: [a, b, c] for ax² + bx + c
        result += coefficients[i] * Math.pow(x, coefficients.length - 1 - i);
    }
    return result;
}

// Render polynomial fit chart
function renderFanChart(fanId, data, polynomial) {
    const canvasId = `chartFan${fanId}`;
    const polyDivId = `polyFan${fanId}`;
    const canvas = document.getElementById(canvasId);
    const polyDiv = document.getElementById(polyDivId);
    
    if (!canvas) return;
    
    // Destroy existing chart if it exists
    if (polynomialCharts[fanId]) {
        polynomialCharts[fanId].destroy();
    }
    
    // Extract data points for this fan
    const dataPoints = data.map(row => ({
        x: row.fan_speed,
        y: row[`sensor_${fanId}_avg`] || 0
    })).filter(p => p.y > 0);
    
    // Generate polynomial curve points
    const curvePoints = [];
    if (polynomial && polynomial[fanId] && polynomial[fanId].coefficients) {
        const coeffs = polynomial[fanId].coefficients;
        for (let x = 15; x <= 255; x += 5) {
            curvePoints.push({
                x: x,
                y: calculatePolynomial(x, coeffs)
            });
        }
        
        // Display polynomial equation
        const polyStr = coeffs.map((c, i) => {
            if (i === 0) return `${(c || 0).toFixed(6)}`;
            if (i === 1) return `${(c || 0).toFixed(6)}x`;
            return `${(c || 0).toFixed(6)}x^${i}`;
        }).reverse().join(' + ');
        polyDiv.innerHTML = `<strong>R²:</strong> ${(polynomial[fanId]?.r_squared || 0).toFixed(4)}<br><strong>Polynomial:</strong> ${polyStr}`;
    } else {
        polyDiv.innerHTML = 'No polynomial data available';
    }
    
    // Create chart
    const ctx = canvas.getContext('2d');
    polynomialCharts[fanId] = new Chart(ctx, {
        type: 'scatter',
        data: {
            datasets: [
                {
                    label: 'Data Points',
                    data: dataPoints,
                    backgroundColor: 'rgba(54, 162, 235, 0.6)',
                    borderColor: 'rgba(54, 162, 235, 1)',
                    pointRadius: 5,
                    pointHoverRadius: 7,
                    showLine: false
                },
                {
                    label: 'Polynomial Fit',
                    data: curvePoints,
                    borderColor: 'rgba(255, 99, 132, 1)',
                    backgroundColor: 'rgba(255, 99, 132, 0.1)',
                    pointRadius: 0,
                    borderWidth: 2,
                    tension: 0.4,
                    showLine: true
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    display: true,
                    position: 'top'
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return `${context.dataset.label}: (${context.parsed.x}, ${(context.parsed.y || 0).toFixed(3)})`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    type: 'linear',
                    position: 'bottom',
                    title: {
                        display: true,
                        text: 'Fan Speed (PWM)'
                    },
                    min: 0,
                    max: 260
                },
                y: {
                    title: {
                        display: true,
                        text: 'Flow Rate'
                    },
                    beginAtZero: true
                }
            }
        }
    });
}

// Display calibration results
async function displayCalibrationResults(sessionId) {
    calibrationSessionId = sessionId;

    // Show table section and expand it
    document.getElementById('dataTableSection').classList.add('show');
    document.getElementById('noDataMessage').style.display = 'none';
    document.getElementById('dataTableContainer').style.display = 'block';
    document.getElementById('downloadButtons').style.display = 'block';
    document.getElementById('resultsSummary').style.display = 'block';
    document.getElementById('resultsSessionId').textContent = `Session ID: ${sessionId}`;

    // Load calibration data
    const data = await loadCalibrationData(sessionId);
    if (data) {
        calibrationData = data;
        populateCalibrationTable(data);
    }

    // Load and display polynomials in graphs section
    const polynomials = await loadPolynomials();
    if (polynomials) {
        document.getElementById('polynomialGraphSection').classList.add('show');
        document.getElementById('noGraphDataMessage').style.display = 'none';
        document.getElementById('graphsContainer').style.display = 'flex';

        for (let i = 0; i < 4; i++) {
            renderFanChart(i, calibrationData, polynomials);
        }
    }

    // Scroll to table section
    document.getElementById('tableSection').scrollIntoView({ behavior: 'smooth' });
}

// Download CSV
document.getElementById('downloadCSV').addEventListener('click', () => {
    if (!calibrationSessionId || !Array.isArray(calibrationData) || calibrationData.length === 0) {
        addLog('No calibration data to download', 'warning');
        return;
    }
    
    const csvContent = [
        ['timestamp', 'fan_speed', 'sensor_0_avg', 'sensor_1_avg', 'sensor_2_avg', 'sensor_3_avg'],
        ...calibrationData.map(row => [
            row.timestamp,
            row.fan_speed,
            row.sensor_0_avg || '',
            row.sensor_1_avg || '',
            row.sensor_2_avg || '',
            row.sensor_3_avg || ''
        ])
    ].map(row => row.join(',')).join('\n');
    
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `calibration_${calibrationSessionId}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    addLog('CSV downloaded', 'success');
});

// Download Polynomials
document.getElementById('downloadPolynomials').addEventListener('click', async () => {
    const polynomials = await loadPolynomials();
    if (polynomials) {
        const jsonContent = JSON.stringify(polynomials, null, 2);
        const blob = new Blob([jsonContent], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `polynomials_${calibrationSessionId}.json`;
        a.click();
        URL.revokeObjectURL(url);
        addLog('Polynomials downloaded', 'success');
    }
});

// Log function
function addLog(message, type = 'info') {
    const timestamp = new Date().toLocaleTimeString();
    const logClass = `log-${type}`;
    const entry = document.createElement('div');
    entry.className = `log-entry ${logClass}`;
    entry.textContent = `[${timestamp}] [${type.toUpperCase()}] ${message}`;
    calibrationLog.appendChild(entry);
    calibrationLog.scrollTop = calibrationLog.scrollHeight;
}

// Format time
function formatTime(seconds) {
    if (!seconds || seconds < 0) return '--:--:--';
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    return `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

// Update status display
function updateStatus(status) {
    statusBadge.className = 'badge status-badge';
    
    switch(status) {
        case 'idle':
            statusBadge.classList.add('bg-secondary');
            statusBadge.textContent = 'Idle';
            break;
        case 'running':
            statusBadge.classList.add('bg-primary');
            statusBadge.textContent = 'Running';
            break;
        case 'paused':
            statusBadge.classList.add('bg-warning');
            statusBadge.textContent = 'Paused';
            break;
        case 'completed':
            statusBadge.classList.add('bg-success');
            statusBadge.textContent = 'Completed';
            break;
        case 'failed':
            statusBadge.classList.add('bg-danger');
            statusBadge.textContent = 'Failed';
            break;
        default:
            statusBadge.classList.add('bg-secondary');
            statusBadge.textContent = status;
    }
}

// Update hot plate status display
function updateHotplateStatus(status) {
    const hotplateStatusBadge = document.getElementById('hotplateCalibrationStatus');
    
    if (hotplateStatusBadge) {
        hotplateStatusBadge.className = 'badge status-badge';
        
        switch(status) {
            case 'idle':
                hotplateStatusBadge.classList.add('bg-secondary');
                hotplateStatusBadge.textContent = 'Idle';
                break;
            case 'running':
                hotplateStatusBadge.classList.add('bg-warning');
                hotplateStatusBadge.textContent = 'Running';
                break;
            case 'heating':
                hotplateStatusBadge.classList.add('bg-danger');
                hotplateStatusBadge.textContent = 'Heating';
                break;
            case 'recording':
                hotplateStatusBadge.classList.add('bg-info');
                hotplateStatusBadge.textContent = 'Recording';
                break;
            case 'completed':
                hotplateStatusBadge.classList.add('bg-success');
                hotplateStatusBadge.textContent = 'Completed';
                break;
            case 'failed':
                hotplateStatusBadge.classList.add('bg-danger');
                hotplateStatusBadge.textContent = 'Failed';
                break;
            default:
                hotplateStatusBadge.classList.add('bg-secondary');
                hotplateStatusBadge.textContent = status;
        }
    }
}

// Start calibration
startBtn.addEventListener('click', async () => {
    const fanSpeedStep = parseInt(document.getElementById('fanSpeedStep').value) || 5;
    const settlingTime = parseInt(document.getElementById('settlingTime').value) || 1000;
    const numSamples = parseInt(document.getElementById('numSamples').value) || 3;
    
    try {
        addLog('Starting windflow calibration...', 'info');
        
        // Start data capture before starting calibration
        if (typeof startDataCapture === 'function') {
            await startDataCapture();
            addLog('Data capture started', 'success');
        }
        
        const response = await fetch(`/api/calibration/windflow/start?fan_speed_step=${fanSpeedStep}&settling_time_ms=${settlingTime}&num_samples=${numSamples}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        const result = await response.json();
        
        if (result.status === 'success') {
            isCalibrating = true;
            startBtn.disabled = true;
            stopBtn.disabled = false;
            addLog(`Calibration started (Step: ${fanSpeedStep} PWM, Settling time: ${settlingTime}ms, Samples: ${numSamples})`, 'success');

            // Show status section
            document.getElementById('statusSection').style.display = 'block';

            // Connect WebSocket for real-time updates
            connectWebSocket();
        } else {
            addLog(`Failed to start calibration: ${result.message}`, 'error');
        }
    } catch (error) {
        addLog(`Error starting calibration: ${error}`, 'error');
    }
});

// Stop calibration
stopBtn.addEventListener('click', async () => {
    try {
        const response = await fetch('/api/calibration/control', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'stop' })
        });

        const result = await response.json();

        if (result.status === 'success') {
            addLog('Calibration stopped', 'info');
        } else {
            addLog(`Failed to stop calibration: ${result.message}`, 'error');
        }
    } catch (error) {
        addLog(`Error stopping calibration: ${error}`, 'error');
    }
});

// Download calibration data
document.getElementById('downloadCalibrationData').addEventListener('click', downloadCalibrationData);
document.getElementById('downloadHotplateData').addEventListener('click', downloadCalibrationData);
document.getElementById('downloadCSV').addEventListener('click', downloadCalibrationData);

// Hot plate calibration handlers
const hotplateStartBtn = document.getElementById('startHotplateCalibration');
const hotplateStopBtn = document.getElementById('stopHotplateCalibration');

hotplateStartBtn.addEventListener('click', async () => {
    const tempMin = parseFloat(document.getElementById('hotplateTempMin').value) || 80;
    const tempMax = parseFloat(document.getElementById('hotplateTempMax').value) || 120;
    const tempStep = parseFloat(document.getElementById('hotplateTempStep').value) || 2;
    const fanSpeeds = document.getElementById('hotplateFanSpeeds').value || "255,191,128,64";
    const duration = parseInt(document.getElementById('hotplateDuration').value) || 900;
    const interval = parseInt(document.getElementById('hotplateInterval').value) || 10;

    try {
        // Confirm long-running calibration
        const confirmCalibration = confirm('This is a long-running calibration that could take many hours. Are you sure you want to proceed?');
        if (!confirmCalibration) {
            addLog('Hot plate calibration cancelled by user', 'warning');
            return;
        }

        addLog('Starting 4D calibration...', 'info');
        
        // Start data capture before starting calibration
        if (typeof startDataCapture === 'function') {
            await startDataCapture();
            addLog('Data capture started', 'success');
        }
        
        const response = await fetch(`/api/calibration/hotplate/start?temp_min=${tempMin}&temp_max=${tempMax}&temp_step=${tempStep}&fan_speeds=${fanSpeeds}&recording_duration=${duration}&sampling_interval=${interval}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        const result = await response.json();

        if (result.status === 'success') {
            isCalibrating = true;
            hotplateStartBtn.disabled = true;
            hotplateStopBtn.disabled = false;
            addLog(`4D calibration started (Temp: ${tempMin}-${tempMax}°C, Fans: ${result.fan_speeds})`, 'success');
            addLog(`Estimated duration: ${result.estimated_duration}`, 'info');

            // Show hot plate status section
            document.getElementById('hotplateStatusSection').style.display = 'block';
            
            // Initialize hot plate progress display
            updateHotplateStatus('running');
            document.getElementById('hotplateSessionId').textContent = result.session_id || '--';
            document.getElementById('hotplatePhase').textContent = 'Initializing';
            document.getElementById('hotplatePhaseDetails').textContent = 'Starting hot plate calibration...';

            // Connect WebSocket for real-time updates
            connectWebSocket();
        } else {
            addLog(`Failed to start hot plate calibration: ${result.message}`, 'error');
        }
    } catch (error) {
        addLog(`Error starting hot plate calibration: ${error}`, 'error');
    }
});

hotplateStopBtn.addEventListener('click', async () => {
    try {
        const response = await fetch('/api/calibration/control', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'stop' })
        });

        const result = await response.json();

        if (result.status === 'success') {
            addLog('Hot plate calibration stopped', 'warning');
            
            // Stop data capture after stopping calibration
            if (typeof stopDataCapture === 'function') {
                await stopDataCapture();
                addLog('Data capture stopped', 'success');
            }
            hotplateStopBtn.disabled = true;
        } else {
            addLog(`Failed to stop calibration: ${result.message}`, 'error');
        }
    } catch (error) {
        addLog(`Error stopping calibration: ${error}`, 'error');
    }
});

// WebSocket connection for real-time calibration status - only connect on start
let calibrationWebSocket = null;
let wsConnected = false;

// System status WebSocket connection
let systemWebSocket = null;
let systemWsConnected = false;

function connectSystemWebSocket() {
    if (systemWebSocket && systemWebSocket.readyState === WebSocket.OPEN) {
        return; // Already connected
    }
    
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    systemWebSocket = new WebSocket(`${protocol}//${window.location.host}/ws/status`);
    
    systemWebSocket.onopen = () => {
        systemWsConnected = true;
        updateSystemReadyStatus(true);
    };
    
    systemWebSocket.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            
            if (data.type === 'system_status') {
                // Update system status based on device status
                const isReady = data.device_status === 'online' && data.system_ready;
                updateSystemReadyStatus(isReady);
            }
        } catch (error) {
            console.error('Error processing system status message:', error);
        }
    };
    
    systemWebSocket.onerror = (error) => {
        systemWsConnected = false;
        updateSystemReadyStatus(false);
    };
    
    systemWebSocket.onclose = (event) => {
        systemWsConnected = false;
        systemWebSocket = null;
        updateSystemReadyStatus(false);
        
        // Auto-reconnect after 3 seconds
        setTimeout(() => {
            if (!systemWsConnected) {
                connectSystemWebSocket();
            }
        }, 3000);
    };
}

function disconnectSystemWebSocket() {
    if (systemWebSocket && systemWebSocket.readyState === WebSocket.OPEN) {
        systemWebSocket.close();
        systemWebSocket = null;
        systemWsConnected = false;
    }
}

function connectWebSocket() {
    if (calibrationWebSocket && calibrationWebSocket.readyState === WebSocket.OPEN) {
        return; // Already connected
    }
    
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    calibrationWebSocket = new WebSocket(`${protocol}//${window.location.host}/ws/calibration`);
    
    calibrationWebSocket.onopen = () => {
        wsConnected = true;
        addLog('Connected to calibration status via WebSocket', 'info');
    };
    
    calibrationWebSocket.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            console.log('Received calibration WebSocket message:', data);
            
            if (data.type === 'calibration_status') {
                const session = data.session;
                console.log('Session data:', session);
                console.log('Progress:', data.progress);
                
                // Check if this is hot plate calibration (has temperature info)
                const isHotplateCalibration = session.current_temperature !== undefined && session.current_temperature !== null;
                console.log('Is hotplate calibration:', isHotplateCalibration);
                
                if (isHotplateCalibration) {
                    // Update hot plate calibration display
                    document.getElementById('hotplateSessionId').textContent = session.session_id || '--';
                    
                    // Show data points if available, otherwise show steps
                    if (session.total_data_points && session.total_data_points > 0) {
                        document.getElementById('hotplateCurrentStep').textContent = session.captured_data_points || '0';
                        document.getElementById('hotplateTotalSteps').textContent = session.total_data_points || '0';
                    } else {
                        document.getElementById('hotplateCurrentStep').textContent = session.current_step || '0';
                        document.getElementById('hotplateTotalSteps').textContent = session.total_steps || '0';
                    }
                    
                    document.getElementById('hotplateProgressBar').style.width = `${(data.progress || 0)}%`;
                    document.getElementById('hotplateProgressPercent').textContent = `${(data.progress || 0).toFixed(1)}%`;
                    
                    // Update temperature and fan speed
                    if (session.current_temperature !== undefined && session.current_temperature !== null) {
                        document.getElementById('hotplateCurrentTemp').textContent = `${session.current_temperature.toFixed(1)}°C`;
                    }
                    if (session.current_fan_speed !== undefined && session.current_fan_speed !== null) {
                        document.getElementById('hotplateCurrentFan').textContent = `${session.current_fan_speed} PWM`;
                    }
                    
                    // Update estimated time
                    if (data.estimated_remaining_time) {
                        document.getElementById('hotplateEstimatedTime').textContent = formatTime(data.estimated_remaining_time);
                    }
                    
                    // Update phase information
                    if (session.phase) {
                        document.getElementById('hotplatePhase').textContent = session.phase;
                    }
                    if (session.phase_details) {
                        document.getElementById('hotplatePhaseDetails').textContent = session.phase_details;
                    }
                    
                    // Update status
                    updateHotplateStatus(session.status);
                    
                    // Check if completed or failed
                    if (session.status === 'completed' || session.status === 'failed') {
                        resetHotplateUI();
                        disconnectWebSocket();
                        
                        if (session.status === 'completed') {
                            addLog('Hot plate calibration completed successfully!', 'success');
                            // Display results if available
                            if (session.session_id) {
                                displayCalibrationResults(session.session_id);
                            }
                        } else {
                            addLog(`Hot plate calibration failed: ${session.error_message}`, 'error');
                        }
                    }
                } else {
                    // Update windflow calibration display
                    console.log('Updating windflow calibration display');
                    sessionId.textContent = session.session_id;
                    
                    // Show data points if available, otherwise show steps
                    if (session.total_data_points && session.total_data_points > 0) {
                        currentStep.textContent = session.captured_data_points || '0';
                        totalSteps.textContent = session.total_data_points || '0';
                    } else {
                        currentStep.textContent = session.current_step || '0';
                        totalSteps.textContent = session.total_steps || '0';
                    }
                    
                    console.log('Updating progress bar to:', data.progress);
                    progressBar.style.width = `${(data.progress || 0)}%`;
                    progressPercent.textContent = `${(data.progress || 0).toFixed(1)}%`;
                    
                    // Update estimated time
                    if (data.estimated_remaining_time) {
                        estimatedTime.textContent = formatTime(data.estimated_remaining_time);
                    }
                    
                    // Update status
                    updateStatus(session.status);
                    
                    // Check if completed or failed
                    if (session.status === 'completed' || session.status === 'failed') {
                        // Stop data capture
                        if (typeof stopDataCapture === 'function') {
                            stopDataCapture().catch(e => console.error('Error stopping data capture:', e));
                        }
                        
                        resetUI();
                        disconnectWebSocket();
                        
                        if (session.status === 'completed') {
                            addLog('Calibration completed successfully!', 'success');
                            // Automatically display results
                            displayCalibrationResults(session.session_id);
                        } else {
                            addLog(`Calibration failed: ${session.error_message}`, 'error');
                        }
                    }
                }
            } else if (data.type === 'ping') {
                calibrationWebSocket.send(JSON.stringify({ type: 'pong' }));
            }
        } catch (error) {
            addLog(`Error processing WebSocket message: ${error}`, 'error');
        }
    };
    
    calibrationWebSocket.onerror = (error) => {
        wsConnected = false;
        addLog('WebSocket error', 'warning');
    };
    
    calibrationWebSocket.onclose = (event) => {
        wsConnected = false;
        calibrationWebSocket = null;
        addLog('WebSocket connection closed', 'info');
    };
}

function disconnectWebSocket() {
    if (calibrationWebSocket && calibrationWebSocket.readyState === WebSocket.OPEN) {
        calibrationWebSocket.close();
        calibrationWebSocket = null;
        wsConnected = false;
        addLog('WebSocket disconnected', 'info');
    }
}

function resetUI() {
    isCalibrating = false;
    updateStatus('idle');

    startBtn.disabled = false;
    stopBtn.disabled = true;

    progressBar.style.width = '0%';
    progressPercent.textContent = '0%';
    currentStep.textContent = '0';
    totalSteps.textContent = '0';
    estimatedTime.textContent = '--:--:--';
    stepType.textContent = '--';

    // Hide status section
    document.getElementById('statusSection').style.display = 'none';
}

function resetHotplateUI() {
    isCalibrating = false;
    updateHotplateStatus('idle');

    hotplateStartBtn.disabled = false;
    hotplateStopBtn.disabled = true;

    document.getElementById('hotplateProgressBar').style.width = '0%';
    document.getElementById('hotplateProgressPercent').textContent = '0%';
    document.getElementById('hotplateCurrentStep').textContent = '0';
    document.getElementById('hotplateTotalSteps').textContent = '0';
    document.getElementById('hotplateEstimatedTime').textContent = '--:--:--';
    document.getElementById('hotplateCurrentTemp').textContent = '--°C';
    document.getElementById('hotplateCurrentFan').textContent = '-- PWM';
    document.getElementById('hotplatePhase').textContent = 'Initializing...';
    document.getElementById('hotplatePhaseDetails').textContent = 'Preparing calibration setup';

    // Hide hot plate status section
    document.getElementById('hotplateStatusSection').style.display = 'none';
}

// Load latest polynomials on page load
async function loadLatestPolynomials() {
    try {
        const response = await fetch('/api/calibration/windflow-polynomials');
        const result = await response.json();

        if (result.status === 'success' && result.polynomials && result.polynomials.length > 0) {
            // Show graphs section and expand it
            document.getElementById('polynomialGraphSection').classList.add('show');
            document.getElementById('noGraphDataMessage').style.display = 'none';
            document.getElementById('graphsContainer').style.display = 'flex';

            // Update session ID in table section summary
            if (result.polynomials[0].calibration_id) {
                document.getElementById('resultsSummary').style.display = 'block';
                document.getElementById('resultsSessionId').textContent = `Session ID: ${result.polynomials[0].calibration_id}`;
                calibrationSessionId = result.polynomials[0].calibration_id;
            }

            // Render charts for each fan
            for (let i = 0; i < 4; i++) {
                if (result.polynomials[i] && result.polynomials[i].data_points) {
                    const dataPoints = result.polynomials[i].data_points.map(dp => ({
                        fan_speed: dp[0],
                        [`sensor_${i}_avg`]: dp[1]
                    }));
                    calibrationData = dataPoints;
                    renderFanChart(i, dataPoints, result.polynomials);
                }
            }

            addLog('Latest calibration data loaded', 'success');
        } else {
            // Show no data message and hide graphs
            document.getElementById('polynomialGraphSection').classList.remove('show');
            document.getElementById('noGraphDataMessage').style.display = 'block';
            document.getElementById('graphsContainer').style.display = 'none';
            document.getElementById('resultsSummary').style.display = 'none';
        }
    } catch (error) {
        // Show no data message on error
        document.getElementById('polynomialGraphSection').classList.remove('show');
        document.getElementById('noGraphDataMessage').style.display = 'block';
        document.getElementById('graphsContainer').style.display = 'none';
        document.getElementById('resultsSummary').style.display = 'none';
        addLog('No calibration data available', 'warning');
    }
}

// Load calibration data when table section is expanded
document.getElementById('dataTableSection').addEventListener('show.bs.collapse', function () {
    loadLatestCalibrationData();
});

// Load latest polynomials on page initialization
loadLatestPolynomials();

// Check for existing calibration sessions on page load
checkExistingSession();

// Update system ready status display
function updateSystemReadyStatus(systemReady) {
    const statusElement = document.getElementById('connectionStatus');
    
    if (statusElement) {
        if (systemReady === 'connecting') {
            statusElement.className = 'connection-status connecting';
            statusElement.innerHTML = '<i class="fas fa-wifi"></i> Connecting...';
        } else if (systemReady) {
            statusElement.className = 'connection-status connected';
            statusElement.innerHTML = '<i class="fas fa-check-circle"></i> System Ready';
        } else {
            statusElement.className = 'connection-status disconnected';
            statusElement.innerHTML = '<i class="fas fa-exclamation-circle"></i> System Not Ready';
        }
    }
}

// Check for existing calibration session
async function checkExistingSession() {
    try {
        const response = await fetch('/api/calibration/session');
        const result = await response.json();
        
        if (result.status === 'success' && result.has_session) {
            const session = result.session;
            addLog(`Found existing calibration session: ${session.session_id}`, 'info');
            addLog(`Status: ${session.status}, Type: ${session.calibration_type}`, 'info');
            
            // Display session based on type
            if (session.calibration_type === 'hotplate') {
                displayExistingHotplateSession(session);
            } else if (session.calibration_type === 'windflow') {
                displayExistingWindflowSession(session);
            }
            
            // Connect WebSocket for real-time updates if session is running
            if (session.is_running) {
                connectWebSocket();
            }
        }
    } catch (error) {
        addLog(`Error checking existing session: ${error}`, 'warning');
    }
}

// Display existing hot plate session
function displayExistingHotplateSession(session) {
    // Switch to hot plate tab
    const hotplateTab = document.getElementById('hotplate-tab');
    if (hotplateTab) {
        hotplateTab.click();
    }
    
    // Only show hot plate progress section if session is running
    if (session.is_running) {
        document.getElementById('hotplateStatusSection').style.display = 'block';
    }
    
    // Update session info
    document.getElementById('hotplateSessionId').textContent = session.session_id || '--';
    document.getElementById('hotplateCurrentStep').textContent = session.current_step || '0';
    document.getElementById('hotplateTotalSteps').textContent = session.total_steps || '0';
    document.getElementById('hotplateProgressBar').style.width = `${session.progress || 0}%`;
    document.getElementById('hotplateProgressPercent').textContent = `${(session.progress || 0).toFixed(1)}%`;
    
    // Update temperature and fan speed
    if (session.current_temperature !== undefined && session.current_temperature !== null) {
        document.getElementById('hotplateCurrentTemp').textContent = `${session.current_temperature.toFixed(1)}°C`;
    }
    if (session.current_fan_speed !== undefined && session.current_fan_speed !== null) {
        document.getElementById('hotplateCurrentFan').textContent = `${session.current_fan_speed} PWM`;
    }
    
    // Update phase information
    if (session.phase) {
        document.getElementById('hotplatePhase').textContent = session.phase;
    }
    if (session.phase_details) {
        document.getElementById('hotplatePhaseDetails').textContent = session.phase_details;
    }
    
    // Update status
    updateHotplateStatus(session.status);
    
    // Update buttons based on session status
    if (session.is_running) {
        hotplateStartBtn.disabled = true;
        hotplateStopBtn.disabled = false;
        isCalibrating = true;
    } else {
        hotplateStartBtn.disabled = false;
        hotplateStopBtn.disabled = true;
        isCalibrating = false;
    }
    
    addLog(`Hot plate calibration session restored: ${(session.progress || 0).toFixed(1)}% complete`, 'success');
}

// Display existing windflow session
function displayExistingWindflowSession(session) {
    // Switch to windflow tab
    const windflowTab = document.getElementById('windflow-tab');
    if (windflowTab) {
        windflowTab.click();
    }
    
    // Only show windflow progress section if session is running
    if (session.is_running) {
        document.getElementById('statusSection').style.display = 'block';
    }
    
    // Update session info
    sessionId.textContent = session.session_id || '--';
    currentStep.textContent = session.current_step || '0';
    totalSteps.textContent = session.total_steps || '0';
    progressBar.style.width = `${session.progress || 0}%`;
    progressPercent.textContent = `${(session.progress || 0).toFixed(1)}%`;
    
    // Update status
    updateStatus(session.status);
    
    // Update buttons based on session status
    if (session.is_running) {
        startBtn.disabled = true;
        stopBtn.disabled = false;
        isCalibrating = true;
    } else {
        startBtn.disabled = false;
        stopBtn.disabled = true;
        isCalibrating = false;
    }
    
    addLog(`Windflow calibration session restored: ${(session.progress || 0).toFixed(1)}% complete`, 'success');
}

// Load calibration data on page load

// Download calibration data
async function downloadCalibrationData() {
    try {
        const response = await fetch('/api/data-capture/download');
        
        if (response.ok) {
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = response.headers.get('Content-Disposition')?.split('filename=')[1]?.replace(/"/g, '') || 'data_capture.csv';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
            
            addLog('Calibration data downloaded successfully', 'success');
        } else {
            addLog('Failed to download calibration data', 'error');
        }
    } catch (e) {
        console.error('Error downloading calibration data:', e);
        addLog('Error downloading calibration data', 'error');
    }
}

// Initialize connection status
updateSystemReadyStatus('connecting');

// Connect to system status WebSocket on page load
connectSystemWebSocket();

// WebSocket is not auto-connected anymore

// PID Calibration Variables
let pidCalibrating = false;
let pidCalibrationData = [];
let pidCharts = {};
let pidWebSocket = null;
let pidSessionId = null;

// Load PID settings from settings.json
async function loadPidSettings() {
    try {
        const response = await fetch('/api/settings');
        const settings = await response.json();
        
        if (settings.pid_parameters) {
            // Load Hot Plate 1 PID parameters
            if (settings.pid_parameters.hotplate_0) {
                document.getElementById('pid-kp-0').value = settings.pid_parameters.hotplate_0.kp || 35;
                document.getElementById('pid-ki-0').value = settings.pid_parameters.hotplate_0.ki || 0.5;
                document.getElementById('pid-kd-0').value = settings.pid_parameters.hotplate_0.kd || 0;
            }
            
            // Load Hot Plate 2 PID parameters
            if (settings.pid_parameters.hotplate_1) {
                document.getElementById('pid-kp-1').value = settings.pid_parameters.hotplate_1.kp || 80;
                document.getElementById('pid-ki-1').value = settings.pid_parameters.hotplate_1.ki || 0.5;
                document.getElementById('pid-kd-1').value = settings.pid_parameters.hotplate_1.kd || 1;
            }
            
            showPidMessage('PID settings loaded successfully', 'success');
        }
    } catch (error) {
        console.error('Failed to load PID settings:', error);
        showPidMessage('Failed to load PID settings', 'error');
    }
}

// Save PID settings to settings.json
async function savePidSettings() {
    const pidKp0 = parseFloat(document.getElementById('pid-kp-0').value);
    const pidKi0 = parseFloat(document.getElementById('pid-ki-0').value);
    const pidKd0 = parseFloat(document.getElementById('pid-kd-0').value);
    const pidKp1 = parseFloat(document.getElementById('pid-kp-1').value);
    const pidKi1 = parseFloat(document.getElementById('pid-ki-1').value);
    const pidKd1 = parseFloat(document.getElementById('pid-kd-1').value);
    
    try {
        // First load current settings to preserve other values
        const getResponse = await fetch('/api/settings');
        const currentSettings = await getResponse.json();
        
        // Update only the pid_parameters
        currentSettings.pid_parameters = {
            hotplate_0: {
                kp: pidKp0,
                ki: pidKi0,
                kd: pidKd0
            },
            hotplate_1: {
                kp: pidKp1,
                ki: pidKi1,
                kd: pidKd1
            }
        };
        
        // Save the complete settings object
        const response = await fetch('/api/settings', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(currentSettings)
        });
        
        if (response.ok) {
            showPidMessage('PID settings saved successfully', 'success');
        } else {
            showPidMessage('Failed to save PID settings', 'error');
        }
    } catch (error) {
        console.error('Failed to save PID settings:', error);
        showPidMessage('Failed to save PID settings', 'error');
    }
}

// Show PID settings message
function showPidMessage(message, type) {
    const messageDiv = document.getElementById('pid-settings-message');
    if (messageDiv) {
        messageDiv.textContent = message;
        messageDiv.className = `alert alert-${type} alert-sm`;
        messageDiv.classList.remove('d-none');
        
        setTimeout(() => {
            messageDiv.classList.add('d-none');
        }, 3000);
    }
}

// Initialize PID charts
function initPidCharts() {
    const chartConfig = (label) => ({
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: label,
                data: [],
                borderColor: 'rgb(75, 192, 192)',
                backgroundColor: 'rgba(75, 192, 192, 0.2)',
                tension: 0.1
            }]
        },
        options: {
            responsive: true,
            scales: {
                x: {
                    title: {
                        display: true,
                        text: 'Time (s)'
                    }
                },
                y: {
                    title: {
                        display: true,
                        text: 'Temperature (°C)'
                    }
                }
            }
        }
    });

    pidCharts[0] = new Chart(
        document.getElementById('pidChart0'),
        chartConfig('Hot Plate 1 Temperature')
    );

    pidCharts[1] = new Chart(
        document.getElementById('pidChart1'),
        chartConfig('Hot Plate 2 Temperature')
    );
}

// Start PID calibration
async function startPidCalibration() {
    pidCalibrating = true;
    pidCalibrationData = [];
    
    // Generate session ID
    const now = new Date();
    pidSessionId = `pid_calibration_${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}_${String(now.getHours()).padStart(2, '0')}${String(now.getMinutes()).padStart(2, '0')}${String(now.getSeconds()).padStart(2, '0')}`;
    
    document.getElementById('startPidCalibration').disabled = true;
    document.getElementById('stopPidCalibration').disabled = false;
    document.getElementById('pidStatusSection').style.display = 'block';
    document.getElementById('pidCalibrationStatus').textContent = 'Running';
    document.getElementById('pidCalibrationStatus').className = 'badge bg-success status-badge';
    
    // Clear charts
    pidCharts[0].data.labels = [];
    pidCharts[0].data.datasets[0].data = [];
    pidCharts[1].data.labels = [];
    pidCharts[1].data.datasets[0].data = [];
    pidCharts[0].update();
    pidCharts[1].update();
    
    // Start data capture
    if (typeof startDataCapture === 'function') {
        await startDataCapture();
        console.log('Data capture started for PID calibration');
    }
    
    // Connect to WebSocket for real-time data
    connectPidWebSocket();
}

// Stop PID calibration
async function stopPidCalibration() {
    pidCalibrating = false;
    
    document.getElementById('startPidCalibration').disabled = false;
    document.getElementById('stopPidCalibration').disabled = true;
    document.getElementById('pidCalibrationStatus').textContent = 'Stopped';
    document.getElementById('pidCalibrationStatus').className = 'badge bg-warning status-badge';
    
    // Show download button if data is available
    const downloadBtn = document.getElementById('downloadPidCalibration');
    if (downloadBtn && pidCalibrationData.length > 0) {
        downloadBtn.style.display = 'inline-block';
    }
    
    // Stop data capture after stopping calibration
    if (typeof stopDataCapture === 'function') {
        await stopDataCapture();
        console.log('Data capture stopped after PID calibration');
    }
    
    if (pidWebSocket) {
        pidWebSocket.close();
    } 
    pidWebSocket = null;
}

// Clear PID calibration data
function clearPidCalibrationData() {
    pidCalibrationData = [];
    
    pidCharts[0].data.labels = [];
    pidCharts[0].data.datasets[0].data = [];
    pidCharts[1].data.labels = [];
    pidCharts[1].data.datasets[0].data = [];
    pidCharts[0].update();
    pidCharts[1].update();
    
    document.getElementById('pidDataPoints').textContent = 'Data Points: 0';
    
    // Hide download button
    const downloadBtn = document.getElementById('downloadPidCalibration');
    if (downloadBtn) {
        downloadBtn.style.display = 'none';
    }
}

// Download PID calibration data
async function downloadPidCalibrationData() {
    try {
        const response = await fetch('/api/data-capture/download');
        
        if (response.ok) {
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = response.headers.get('Content-Disposition')?.split('filename=')[1]?.replace(/"/g, '') || 'data_capture.csv';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
            
            showPidMessage('PID calibration data downloaded successfully', 'success');
        } else {
            showPidMessage('Failed to download PID calibration data', 'error');
        }
    } catch (e) {
        console.error('Error downloading PID calibration data:', e);
        showPidMessage('Error downloading PID calibration data', 'error');
    }
}

// Connect PID WebSocket
function connectPidWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/status`;
    
    pidWebSocket = new WebSocket(wsUrl);
    
    pidWebSocket.onopen = function() {
        console.log('PID calibration WebSocket connected');
    };
    
    pidWebSocket.onmessage = function(event) {
        if (!pidCalibrating) return;
        
        try {
            const data = JSON.parse(event.data);
            
            if (data.type === 'current_data' && data.data && data.data.length > 0) {
                const statusData = data.data[0];
                const timestamp = new Date(statusData.timestamp);
                const timeSeconds = (timestamp - pidCalibrationStartTime) / 1000;
                
                // Get hotplate temperatures
                const tempHotplate1 = statusData.temp_hotplate1;
                const tempHotplate2 = statusData.temp_hotplate2;
                
                if (tempHotplate1 !== null && tempHotplate2 !== null) {
                    // Add data to charts
                    pidCharts[0].data.labels.push(timeSeconds.toFixed(1));
                    pidCharts[0].data.datasets[0].data.push(tempHotplate1);
                    pidCharts[1].data.labels.push(timeSeconds.toFixed(1));
                    pidCharts[1].data.datasets[0].data.push(tempHotplate2);
                    
                    // Update charts
                    pidCharts[0].update('none');
                    pidCharts[1].update('none');
                    
                    // Store data
                    pidCalibrationData.push({
                        timestamp: statusData.timestamp,
                        timeSeconds: timeSeconds,
                        tempHotplate1: tempHotplate1,
                        tempHotplate2: tempHotplate2
                    });
                    
                    // Update data points counter
                    document.getElementById('pidDataPoints').textContent = `Data Points: ${pidCalibrationData.length}`;
                    
                    // Show download button when data is available
                    const downloadBtn = document.getElementById('downloadPidCalibration');
                    if (downloadBtn && pidCalibrationData.length > 0) {
                        downloadBtn.style.display = 'inline-block';
                    }
                }
            }
        } catch (error) {
            console.error('Error processing PID calibration data:', error);
        }
    };
    
    pidWebSocket.onclose = function() {
        console.log('PID calibration WebSocket disconnected');
        if (pidCalibrating) {
            setTimeout(connectPidWebSocket, 3000);
        }
    };
    
    pidWebSocket.onerror = function(error) {
        console.error('PID calibration WebSocket error:', error);
    };
}

let pidCalibrationStartTime = null;

// Initialize PID calibration on page load
document.addEventListener('DOMContentLoaded', function() {
    initPidCharts();
    loadPidSettings();
    
    document.getElementById('startPidCalibration').addEventListener('click', async function() {
        pidCalibrationStartTime = new Date();
        
        // Start data capture before starting calibration
        if (typeof startDataCapture === 'function') {
            await startDataCapture();
            console.log('Data capture started for PID calibration');
        }
        
        startPidCalibration();
    });
    
    document.getElementById('stopPidCalibration').addEventListener('click', stopPidCalibration);
});
