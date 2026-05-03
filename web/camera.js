// Camera Video Stream Module
// Video streaming variables
let videoWs = null;
let videoReconnectInterval = null;
let isVideoStreaming = false;
let videoClientId = null;
const currentVideoMode = 'video'; // Always video mode now

// Configuration
const VIDEO_CONFIG = {
    VIDEO_WS_URL: `ws://${window.location.host}/ws/video`,
    RECONNECT_DELAY: 3000
};

// Show notification (shared utility - defined in main.js, but defined here for camera module independence)
// Note: If this function is already defined in main.js, this definition won't override it
if (typeof showNotification === 'undefined') {
    function showNotification(message, type = 'info') {
        // Create a simple notification (you can enhance this with a proper notification library)
        const notification = document.createElement('div');
        notification.className = `alert alert-${type === 'error' ? 'danger' : type === 'success' ? 'success' : 'info'} alert-dismissible fade show position-fixed`;
        notification.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
        notification.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        document.body.appendChild(notification);
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 5000);
    }
}

// Initialize video streaming WebSocket
function initVideoWebSocket() {
    if (!videoClientId) {
        videoClientId = 'client_' + Math.random().toString(36).substr(2, 9);
    }
    
    try {
        const videoWsUrl = `${VIDEO_CONFIG.VIDEO_WS_URL}/${videoClientId}`;
        
        videoWs = new WebSocket(videoWsUrl);
        
        videoWs.onopen = function() {
            if (videoReconnectInterval) {
                clearInterval(videoReconnectInterval);
                videoReconnectInterval = null;
            }
            
            // Send ping to test connection
            videoWs.send('{"type":"ping"}');
        };
        
        videoWs.onmessage = function(event) {
            try {
                const data = JSON.parse(event.data);
                handleVideoWebSocketMessage(data);
            } catch (error) {
                // Silently handle parsing errors
            }
        };
        
        videoWs.onclose = function() {
            scheduleVideoReconnect();
        };
        
        videoWs.onerror = function(error) {
            scheduleVideoReconnect();
        };
        
    } catch (error) {
        scheduleVideoReconnect();
    }
}

// Handle video streaming WebSocket messages
function handleVideoWebSocketMessage(data) {
    switch (data.type) {
        case 'stream_status':
            updateVideoStreamStatus(data.status);
            break;
            
        case 'video_frame':
            displayVideoFrame(data.frame);
            break;
            
        case 'stream_response':
            if (data.action === 'start' && data.success) {
                isVideoStreaming = true;
            } else if (data.action === 'stop' && data.success) {
                isVideoStreaming = false;
            }
            break;
            
        case 'ping':
            videoWs.send('{"type":"pong"}');
            break;
            
        default:
            // Silently handle unknown message types
    }
}

// Display video frame in SVG
function displayVideoFrame(frameData) {
    const svgObject = document.querySelector('object[data="/static/main.svg"]');
    let svgDoc = null;
    
    if (svgObject && svgObject.contentDocument) {
        svgDoc = svgObject.contentDocument;
    } else if (svgObject && svgObject.getSVGDocument) {
        svgDoc = svgObject.getSVGDocument();
    }
    
    if (!svgDoc) {
        // Try alternative method - wait for SVG to load
        setTimeout(() => displayVideoFrame(frameData), 100);
        return;
    }
    
    // Find the video stream element in modal
    const svgVideoStreamElement = document.getElementById('svgVideoStream');
    const videoLoadingIndicator = document.getElementById('videoLoadingIndicator');
    const videoStatusIndicator = document.getElementById('videoStatusIndicator');
    
    if (svgVideoStreamElement && frameData) {
        // Create data URL from base64 frame data
        const dataUrl = `data:image/jpeg;base64,${frameData}`;
        svgVideoStreamElement.setAttribute('href', dataUrl);
        
        // Hide loading indicator and show streaming status
        if (videoLoadingIndicator) {
            videoLoadingIndicator.style.display = 'none';
        }
        if (videoStatusIndicator) {
            videoStatusIndicator.style.background = '#28a745'; // Green for active streaming
        }
    }
}

// Update video streaming status display
function updateVideoStreamStatus(status) {
    isVideoStreaming = status.is_streaming || false;
    const cameraConnected = status.camera_connected !== undefined ? status.camera_connected : true;
    
    // Update UI elements based on streaming status
    const videoStatusElement = document.getElementById('video-stream-status');
    if (videoStatusElement) {
        videoStatusElement.textContent = isVideoStreaming ? 'Streaming' : 'Not Streaming';
        videoStatusElement.className = isVideoStreaming ? 'text-success' : 'text-muted';
    }
    
    // Update navbar video status text
    const videoStatusText = document.getElementById('videoStatusText');
    if (videoStatusText) {
        if (isVideoStreaming) {
            videoStatusText.textContent = 'Live Video Stream';
        } else if (!cameraConnected) {
            videoStatusText.textContent = 'Camera not connected';
        } else {
            videoStatusText.textContent = 'Stream stopped';
        }
    }
    
    // Update start/stop button visibility
    const startVideoBtn = document.getElementById('startVideoBtn');
    const stopVideoBtn = document.getElementById('stopVideoBtn');
    const refreshCameraBtn = document.getElementById('refreshCameraBtn');
    
    if (startVideoBtn && stopVideoBtn) {
        if (isVideoStreaming) {
            startVideoBtn.classList.add('d-none');
            stopVideoBtn.classList.remove('d-none');
        } else {
            startVideoBtn.classList.remove('d-none');
            stopVideoBtn.classList.add('d-none');
        }
    }
    
    // Show refresh button if camera is not connected
    if (refreshCameraBtn) {
        if (!cameraConnected) {
            refreshCameraBtn.classList.remove('d-none');
        } else {
            refreshCameraBtn.classList.add('d-none');
        }
    }
    
    // Update Start Stream button based on camera status
    updateStartStreamButton(cameraConnected);
    
    // Always show video mode
    const cameraModeElement = document.getElementById('camera-mode');
    if (cameraModeElement) {
        cameraModeElement.textContent = 'Live Video';
    }
    
    // Update SVG video status indicator
    const svgObject = document.querySelector('object[data="/static/main.svg"]');
    let svgDoc = null;
    
    if (svgObject && svgObject.contentDocument) {
        svgDoc = svgObject.contentDocument;
    } else if (svgObject && svgObject.getSVGDocument) {
        svgDoc = svgObject.getSVGDocument();
    }
    
    const videoStatusIndicator = document.getElementById('videoStatusIndicator');
    const videoLoadingIndicator = document.getElementById('videoLoadingIndicator');
    
    if (videoStatusIndicator) {
        if (isVideoStreaming) {
            videoStatusIndicator.style.background = '#28a745'; // Green
            if (videoLoadingIndicator) {
                videoLoadingIndicator.style.display = 'none';
            }
        } else {
            videoStatusIndicator.style.background = '#dc3545'; // Red
            if (videoLoadingIndicator) {
                videoLoadingIndicator.style.display = 'block';
                if (!cameraConnected) {
                    videoLoadingIndicator.textContent = 'Camera not connected';
                } else {
                    videoLoadingIndicator.textContent = 'Waiting for Stream...';
                }
            }
        }
    }
}

// Initialize video display
async function initVideoDisplay() {
    const svgObject = document.querySelector('object[data="/static/main.svg"]');
    
    // Wait for SVG to load
    if (svgObject) {
        await new Promise((resolve) => {
            if (svgObject.contentDocument) {
                resolve();
            } else {
                svgObject.addEventListener('load', resolve);
                // Also resolve after a timeout in case load event doesn't fire
                setTimeout(resolve, 1000);
            }
        });
    }
    
    let svgDoc = null;
    if (svgObject && svgObject.contentDocument) {
        svgDoc = svgObject.contentDocument;
    } else if (svgObject && svgObject.getSVGDocument) {
        svgDoc = svgObject.getSVGDocument();
    }
    
    const videoLoadingIndicator = document.getElementById('videoLoadingIndicator');
    const videoStatusIndicator = document.getElementById('videoStatusIndicator');
    
    // Check camera status on initialization
    try {
        const response = await fetch('/api/camera/status');
        const cameraStatus = await response.json();
        const cameraConnected = cameraStatus.connected || false;
        
        if (videoLoadingIndicator) {
            if (cameraConnected) {
                videoLoadingIndicator.textContent = 'Loading Video...';
            } else {
                videoLoadingIndicator.textContent = 'Camera not connected';
            }
            videoLoadingIndicator.style.display = 'block';
        }
        
        if (videoStatusIndicator) {
            if (cameraConnected) {
                videoStatusIndicator.style.background = '#ffc107'; // Yellow for loading
            } else {
                videoStatusIndicator.style.background = '#dc3545'; // Red for disconnected
            }
        }
        
        // Show refresh button if camera is not connected
        const refreshCameraBtn = document.getElementById('refreshCameraBtn');
        if (refreshCameraBtn) {
            if (!cameraConnected) {
                refreshCameraBtn.classList.remove('d-none');
            }
        }
        
        // Update Start Stream button based on camera status
        updateStartStreamButton(cameraConnected);
    } catch (e) {
        // On error, assume camera is not connected
        if (videoLoadingIndicator) {
            videoLoadingIndicator.textContent = 'Camera not connected';
            videoLoadingIndicator.style.display = 'block';
        }
        
        if (videoStatusIndicator) {
            videoStatusIndicator.style.background = '#dc3545'; // Red for disconnected
        }
        
        const refreshCameraBtn = document.getElementById('refreshCameraBtn');
        if (refreshCameraBtn) {
            refreshCameraBtn.classList.remove('d-none');
        }
        
        // Update Start Stream button
        updateStartStreamButton(false);
    }
}

// ... rest of the code remains the same ...
function updateStartStreamButton(cameraConnected) {
    const startVideoBtn = document.getElementById('startVideoBtn');
    if (!startVideoBtn) return;
    
    if (!cameraConnected) {
        // Change to refresh icon and disable
        startVideoBtn.innerHTML = '<i class="fas fa-sync-alt me-1"></i> Refresh Camera';
        startVideoBtn.classList.remove('btn-outline-success');
        startVideoBtn.classList.add('btn-outline-primary');
        startVideoBtn.disabled = true;
        
        // Update click handler to refresh camera instead of start stream
        startVideoBtn.onclick = function() {
            refreshCamera();
        };
    } else {
        // Reset to start stream button
        startVideoBtn.innerHTML = '<i class="fas fa-play me-1"></i> Start Stream';
        startVideoBtn.classList.remove('btn-outline-primary');
        startVideoBtn.classList.add('btn-outline-success');
        startVideoBtn.disabled = false;
        
        // Reset click handler to start stream
        startVideoBtn.onclick = function() {
            startVideoStream();
        };
    }
}

// Initialize video control buttons
function initVideoControls() {
    const stopVideoBtn = document.getElementById('stopVideoBtn');
    const refreshCameraBtn = document.getElementById('refreshCameraBtn');
    
    // Start Stream button is handled dynamically based on camera status
    // Don't add event listener here
    
    if (stopVideoBtn) {
        stopVideoBtn.addEventListener('click', stopVideoStream);
    }
    
    if (refreshCameraBtn) {
        refreshCameraBtn.addEventListener('click', refreshCamera);
    }
}

// Start video stream
async function startVideoStream() {
    try {
        const response = await fetch('/api/camera/video/start', {
            method: 'POST'
        });
        
        const result = await response.json();
        
        if (result.status === 'success') {
            // Send start stream command via WebSocket
            if (videoWs && videoWs.readyState === WebSocket.OPEN) {
                videoWs.send('{"type":"start_stream"}');
            }
            showNotification('Video stream started', 'success');
        } else {
            showNotification('Failed to start video stream: ' + result.message, 'error');
        }
    } catch (e) {
        console.error('Error starting video stream:', e);
        showNotification('Error starting video stream', 'error');
    }
}

// Stop video stream
async function stopVideoStream() {
    try {
        const response = await fetch('/api/camera/video/stop', {
            method: 'POST'
        });
        
        const result = await response.json();
        
        if (result.status === 'success') {
            // Send stop stream command via WebSocket
            if (videoWs && videoWs.readyState === WebSocket.OPEN) {
                videoWs.send('{"type":"stop_stream"}');
            }
            showNotification('Video stream stopped', 'info');
        } else {
            showNotification('Failed to stop video stream: ' + result.message, 'error');
        }
    } catch (e) {
        console.error('Error stopping video stream:', e);
        showNotification('Error stopping video stream', 'error');
    }
}

// Refresh camera connection
async function refreshCamera() {
    try {
        const refreshCameraBtn = document.getElementById('refreshCameraBtn');
        if (refreshCameraBtn) {
            refreshCameraBtn.disabled = true;
            refreshCameraBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i> Connecting...';
        }
        
        const response = await fetch('/api/camera/diagnose', {
            method: 'POST'
        });
        
        const result = await response.json();
        
        if (result.status === 'success' && result.camera_connected) {
            showNotification('Camera connected successfully', 'success');
            
            // Update video status
            updateVideoStreamStatus({ is_streaming: false, camera_connected: true });
            
            // Reconnect video WebSocket
            if (videoWs) {
                videoWs.close();
            }
            initVideoWebSocket();
        } else {
            showNotification('Camera connection failed: ' + (result.message || 'Camera not found'), 'error');
            updateVideoStreamStatus({ is_streaming: false, camera_connected: false });
        }
    } catch (e) {
        console.error('Error refreshing camera:', e);
        showNotification('Error refreshing camera connection', 'error');
        updateVideoStreamStatus({ is_streaming: false, camera_connected: false });
    } finally {
        const refreshCameraBtn = document.getElementById('refreshCameraBtn');
        if (refreshCameraBtn) {
            refreshCameraBtn.disabled = false;
            refreshCameraBtn.innerHTML = '<i class="fas fa-sync-alt me-1"></i> Refresh Camera';
        }
    }
}

// Schedule video reconnection
function scheduleVideoReconnect() {
    if (!videoReconnectInterval) {
        videoReconnectInterval = setInterval(() => {
            initVideoWebSocket();
        }, VIDEO_CONFIG.RECONNECT_DELAY);
    }
}
