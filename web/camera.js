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

// Display video frame in modal
function displayVideoFrame(frameData) {
    const videoStreamElement = document.getElementById('svgVideoStream');
    const videoLoadingIndicator = document.getElementById('videoLoadingIndicator');
    const videoStatusIndicator = document.getElementById('videoStatusIndicator');
    
    if (videoStreamElement && frameData) {
        const dataUrl = `data:image/jpeg;base64,${frameData}`;
        videoStreamElement.setAttribute('src', dataUrl);
        
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
    
    // Always show video mode
    const cameraModeElement = document.getElementById('camera-mode');
    if (cameraModeElement) {
        cameraModeElement.textContent = 'Live Video';
    }
    
    // Update modal video status indicator
    const videoStatusIndicator = document.getElementById('videoStatusIndicator');
    const videoLoadingIndicator = document.getElementById('videoLoadingIndicator');

    if (videoStatusIndicator) {
        if (isVideoStreaming) {
            videoStatusIndicator.style.background = '#28a745'; // Green
        } else if (cameraConnected) {
            videoStatusIndicator.style.background = '#ffc107'; // Yellow for loading
        } else {
            videoStatusIndicator.style.background = '#dc3545'; // Red for disconnected
        }
    }

    if (videoLoadingIndicator) {
        if (cameraConnected) {
            videoLoadingIndicator.style.display = 'none';
        } else {
            videoLoadingIndicator.style.display = 'block';
        }
    }

    if (videoLoadingIndicator) {
        if (cameraConnected) {
            videoLoadingIndicator.textContent = 'Waiting for Stream...';
        } else {
            videoLoadingIndicator.textContent = 'Camera not connected';
        }
    }
}

// Initialize video display
async function initVideoDisplay() {
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
                videoStatusIndicator.style.background = '#28a745'; // Green for active streaming
            } else {
                videoStatusIndicator.style.background = '#dc3545'; // Red for disconnected
            }
        }
    } catch (e) {
        // On error, assume camera is not connected
        if (videoLoadingIndicator) {
            videoLoadingIndicator.textContent = 'Camera not connected';
            videoLoadingIndicator.style.display = 'block';
        }

        if (videoStatusIndicator) {
            videoStatusIndicator.style.background = '#dc3545'; // Red for disconnected
        }
    }
}

// ... rest of the code remains the same ...

// Start video stream
async function startVideoStream() {
    try {
        // Send start stream command via WebSocket
        if (videoWs && videoWs.readyState === WebSocket.OPEN) {
            videoWs.send('{"type":"start_stream"}');
            showNotification('Video stream started', 'success');
        } else {
            showNotification('WebSocket not connected', 'error');
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
            // Close WebSocket connection
            if (videoWs) {
                videoWs.close();
                videoWs = null;
            }
            // Clear reconnect interval
            if (videoReconnectInterval) {
                clearInterval(videoReconnectInterval);
                videoReconnectInterval = null;
            }
            isVideoStreaming = false;
            showNotification('Video stream stopped', 'info');
        } else {
            showNotification('Failed to stop video stream: ' + result.message, 'error');
        }
    } catch (e) {
        console.error('Error stopping video stream:', e);
        showNotification('Error stopping video stream', 'error');
    }
}


// Schedule video reconnection
function scheduleVideoReconnect() {
    if (!videoReconnectInterval) {
        videoReconnectInterval = setInterval(() => {
            if (videoWs && videoWs.readyState === WebSocket.OPEN) {
                videoWs.send('{"type":"ping"}');
            } else {
                initVideoWebSocket();
            }
        }, VIDEO_CONFIG.RECONNECT_DELAY);
    }
}
