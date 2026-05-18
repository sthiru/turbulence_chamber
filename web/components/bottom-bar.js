// Bottom Bar Shared Functionality

// Data capture variables
let isCapturing = false;
let capturedData = [];
let currentSessionId = null;
let userActionInProgress = false;

// Initialize bottom bar
function initializeBottomBar() {
    initDataCapture();
    console.log('Bottom bar initialized');
    
    // Start periodic status polling for data counter updates
    setInterval(checkCaptureStatus, 2000); // Poll every 2 seconds
}

// Initialize data capture event listeners
function initDataCapture() {
    const startBtn = document.getElementById('startCaptureBtn');
    const stopBtn = document.getElementById('stopCaptureBtn');
    const downloadIconBtn = document.getElementById('downloadIconBtn');
    
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

// Check capture status
async function checkCaptureStatus() {
    if (userActionInProgress) {
        return;
    }
    
    try {
        const response = await fetch('/api/data-capture/status');
        const status = await response.json();
        
        if (status.active) {
            isCapturing = true;
            currentSessionId = status.session?.id;
            updateCaptureUI(true);
            
            // Update data counter with actual count from server
            if (status.data_points_count !== undefined) {
                capturedData = Array(status.data_points_count).fill(null); // Update array length
                updateDataCounter();
            }
        } else {
            isCapturing = false;
            updateCaptureUI(false);
        }
    } catch (e) {
        console.error('Error checking capture status:', e);
    }
}

// Start data capture
async function startDataCapture() {
    userActionInProgress = true;
    
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
            capturedData = [];
            
            updateCaptureUI(true);
            showNotification('Data capture started', 'success');
            
            if (result.camera_available === false) {
                showNotification('Camera not available - data capture running without video streaming', 'warning');
            }
        } else {
            console.error('Failed to start data capture:', result.message);
            showNotification('Failed to start data capture: ' + result.message, 'error');
        }
    } catch (e) {
        console.error('Error starting data capture:', e);
        showNotification('Error starting data capture', 'error');
    } finally {
        setTimeout(() => {
            userActionInProgress = false;
        }, 2000);
    }
}

// Stop data capture
async function stopDataCapture() {
    userActionInProgress = true;
    
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
            showNotification(`Data capture stopped. ${result.session_info.total_data_points} data points captured.`, 'info');
        } else {
            console.error('Failed to stop data capture:', result.message);
            showNotification('Failed to stop data capture: ' + result.message, 'error');
        }
    } catch (e) {
        console.error('Error stopping data capture:', e);
        showNotification('Error stopping data capture', 'error');
    } finally {
        setTimeout(() => {
            userActionInProgress = false;
        }, 2000);
    }
}

// Update capture UI
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
        
        if (downloadIconBtn) {
            if (capturedData.length > 0) {
                downloadIconBtn.classList.remove('d-none');
            } else {
                downloadIconBtn.classList.add('d-none');
            }
        }
    }
}

// Update data counter
function updateDataCounter() {
    const dataCounter = document.getElementById('dataCounter');
    
    if (dataCounter) {
        dataCounter.textContent = capturedData.length;
        
        dataCounter.className = capturedData.length === 0 ? 'badge bg-secondary' : 
                              capturedData.length < 100 ? 'badge bg-primary' : 
                              capturedData.length < 500 ? 'badge bg-info' : 'badge bg-success';
    }
}

// Download captured data
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
            showNotification('Failed to download data', 'error');
        }
    } catch (e) {
        console.error('Error downloading data:', e);
        showNotification('Error downloading data', 'error');
    }
}

// Show notification
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `alert alert-${type === 'error' ? 'danger' : type === 'success' ? 'success' : 'info'} alert-dismissible fade show position-fixed`;
    notification.style.top = '20px';
    notification.style.right = '20px';
    notification.style.zIndex = '9999';
    notification.style.minWidth = '300px';
    notification.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.remove();
    }, 3000);
}
