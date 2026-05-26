/**
 * Configuration constants for web frontend
 * Centralizes all magic numbers and configuration values
 */

// WebSocket Configuration
const WEBSOCKET = {
    RECONNECT_DELAY: 3000,
    STATUS_URL: `ws://${window.location.host}/ws/status`,
    VIDEO_URL: `ws://${window.location.host}/ws/video`
};

// API Endpoints
const API = {
    BASE: '/api',
    STATUS: '/api/status',
    TEMPERATURE_SET: '/api/temperature/set',
    FAN_SET: '/api/fan/set',
    HOTPLATE_TOGGLE: '/api/hotplate',
    SETTINGS: '/api/settings',
    SETTINGS_APPLY: '/api/settings/apply',
    CAMERA_STATUS: '/api/camera/status',
    CAMERA_VIDEO_STOP: '/api/camera/video/stop',
    CALIBRATION_WINDFLOW_START: '/api/calibration/windflow/start',
    CALIBRATION_CONTROL: '/api/calibration/control',
    CALIBRATION_SESSION: '/api/calibration/session',
    CALIBRATION_SESSION_CLEAR: '/api/calibration/session/clear',
    CALIBRATION_HOTPLATE_START: '/api/calibration/hotplate/start',
    CALIBRATION_LOOKUP_TABLE: '/api/calibration/lookup-table',
    CALIBRATION_LOOKUP_TABLE_INTERPOLATE: '/api/calibration/lookup-table/interpolate',
    CALIBRATION_WINDFLOW_POLYNOMIALS: '/api/calibration/windflow-polynomials'
};

// Temperature Thresholds
const TEMPERATURE = {
    WARNING: 60,
    DANGER: 80,
    SENSOR_NORMAL: 20,
    SENSOR_WARNING: 30,
    INVALID: -100
};

// Fan Configuration
const FAN = {
    SPEED_MIN: 0,
    SPEED_MAX: 255,
    DURATION_MIN: 0.5,
    DURATION_MAX: 5.0,
    DURATION_CALCULATION_FACTOR: 4.5,
    SLIDER_MIN: -20,
    SLIDER_MAX: 40,
    SLIDER_RANGE: 60,
    SLIDER_CENTER: 40
};

// Hot Plate Configuration
const HOTPLATE = {
    ID_MIN: 0,
    ID_MAX: 1,
    SWITCH_KNOB_OFF: 10,
    SWITCH_KNOB_ON: 30
};

// Color Constants
const COLORS = {
    SUCCESS: '#28a745',
    DANGER: '#dc3545',
    WARNING: '#ffc107',
    INFO: '#17a2b8',
    HOTPLATE_ON: '#ff6b6b',
    HOTPLATE_ON_STROKE: '#ff4444',
    HOTPLATE_OFF: '#c0c0c0',
    HOTPLATE_OFF_STROKE: '#333',
    SWITCH_ON: '#28a745',
    SWITCH_ON_STROKE: '#1e7e34',
    SWITCH_OFF: '#fff',
    SWITCH_OFF_STROKE: '#999'
};

// UI Configuration
const UI = {
    NOTIFICATION_TIMEOUT: 5000,
    CLIENT_ID_LENGTH: 36,
    CLIENT_ID_START: 2,
    CLIENT_ID_SUBSTR: 9
};

// Message Types
const MESSAGE_TYPES = {
    SYSTEM_STATUS: 'system_status',
    HISTORICAL_DATA: 'historical_data',
    CURRENT_DATA: 'current_data',
    VIDEO_FRAME: 'video_frame',
    STREAM_STATUS: 'stream_status',
    STREAM_RESPONSE: 'stream_response',
    PING: 'ping',
    PONG: 'pong',
    START_STREAM: 'start_stream',
    STOP_STREAM: 'stop_stream',
    FAN_SPEED_CHANGE: 'fan_speed_change'
};

// Device Status
const DEVICE_STATUS = {
    ONLINE: 'online',
    OFFLINE: 'offline',
    ERROR: 'error',
    UNKNOWN: 'unknown'
};

// Export configuration
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        WEBSOCKET,
        API,
        TEMPERATURE,
        FAN,
        HOTPLATE,
        COLORS,
        UI,
        MESSAGE_TYPES,
        DEVICE_STATUS
    };
}
