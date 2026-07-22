// Temperature group definitions for the trend chart
const TEMPERATURE_GROUPS = {
    'row1_0.5': [
        { key: 'temperatures', index: 0, label: 't1' },
        { key: 'temperatures', index: 1, label: 't2' }
    ],
    'row1_0.3': [
        { key: 'temperatures', index: 2, label: 't3' },
        { key: 'temperatures', index: 3, label: 't4' }
    ],
    'row2_0.5': [
        { key: 'temperatures', index: 5, label: 't6' },
        { key: 'temperatures', index: 6, label: 't7' }
    ],
    'row2_0.3': [
        { key: 'temperatures', index: 7, label: 't8' },
        { key: 'temperatures', index: 8, label: 't9' }
    ],
    'optical_axis': [
        { key: 'temperatures', index: 10, label: 't11' },
        { key: 'temperatures', index: 9, label: 't10' },
        { key: 'temperatures', index: 4, label: 't5' },
        { key: 'temperatures', index: 11, label: 't12' }
    ],
    'hotplate': [
        { key: 'temp_hotplate1', label: 'h1' },
        { key: 'temp_hotplate2', label: 'h2' }
    ]
};

const SENSOR_COLORS = [
    'rgb(75, 192, 192)',
    'rgb(255, 99, 132)',
    'rgb(54, 162, 235)',
    'rgb(153, 102, 255)',
    'rgb(255, 159, 64)',
    'rgb(255, 205, 86)',
    'rgb(83, 102, 255)',
    'rgb(40, 159, 64)',
    'rgb(210, 99, 132)',
    'rgb(199, 199, 199)',
    'rgb(75, 192, 192)',
    'rgb(255, 159, 64)'
];

const MAX_CHART_POINTS = 100;

// Temperature graph modal
const temperatureGraphOverlay = document.getElementById('temperatureGraphOverlay');
let temperatureModalInstance = null;
let temperatureTrendChart = null;

function getSelectedGroupItems() {
    const checked = document.querySelectorAll('input[name="temperatureGroup"]:checked');
    const items = [];
    checked.forEach(function(checkbox) {
        const group = TEMPERATURE_GROUPS[checkbox.value];
        if (group) {
            group.forEach(function(item, idx) {
                items.push({
                    key: item.key,
                    index: item.index,
                    label: item.label,
                    color: SENSOR_COLORS[(items.length + idx) % SENSOR_COLORS.length]
                });
            });
        }
    });
    return items;
}

document.getElementById('showTemperatureGraphBtn').addEventListener('click', function(e) {
    e.preventDefault();
    if (!temperatureModalInstance) {
        temperatureModalInstance = new bootstrap.Modal(temperatureGraphOverlay);
    }
    temperatureModalInstance.show();
});

if (temperatureGraphOverlay) {
    temperatureGraphOverlay.addEventListener('shown.bs.modal', function() {
        initTemperatureTrendChart();
    });

    temperatureGraphOverlay.addEventListener('hidden.bs.modal', function() {
        if (temperatureModalInstance) {
            temperatureModalInstance.dispose();
            temperatureModalInstance = null;
        }
        const backdrops = document.querySelectorAll('.modal-backdrop');
        backdrops.forEach(backdrop => backdrop.remove());
    });

    const groupCheckboxes = document.querySelectorAll('input[name="temperatureGroup"]');
    groupCheckboxes.forEach(function(checkbox) {
        checkbox.addEventListener('change', function() {
            initTemperatureTrendChart();
        });
    });
}

// Initialize camera overlay
document.getElementById('startVideoBtn').addEventListener('click', function(e) {
    e.preventDefault();
    // Initialize video WebSocket connection
    if (typeof initVideoWebSocket === 'function') {
        initVideoWebSocket();
    }
    const cameraModalElement = document.getElementById('cameraOverlay');
    const cameraModal = new bootstrap.Modal(cameraModalElement);
    cameraModal.show();
});

// Camera modal event listeners for video stream
const cameraModalElement = document.getElementById('cameraOverlay');
let cameraModalInstance = null;

if (cameraModalElement) {
    cameraModalElement.addEventListener('show.bs.modal', function() {
        // Get or create modal instance
        cameraModalInstance = bootstrap.Modal.getInstance(cameraModalElement);
        if (!cameraModalInstance) {
            cameraModalInstance = new bootstrap.Modal(cameraModalElement);
        }
        // Connect to video stream when modal opens
        startVideoStream();
    });

    cameraModalElement.addEventListener('hidden.bs.modal', function() {
        // Disconnect video stream when modal closes
        if (typeof stopVideoStream === 'function') {
            stopVideoStream();
        }
        // Dispose modal instance to remove backdrop
        if (cameraModalInstance) {
            cameraModalInstance.dispose();
            cameraModalInstance = null;
        }
        // Remove any remaining backdrops
        const backdrops = document.querySelectorAll('.modal-backdrop');
        backdrops.forEach(backdrop => backdrop.remove());
    });
}

// Temperature trend chart initialization
function initTemperatureTrendChart() {
    const canvas = document.getElementById('temperatureTrendChart');
    if (!canvas) return;

    if (temperatureTrendChart) {
        temperatureTrendChart.destroy();
    }

    const items = getSelectedGroupItems();
    const datasets = items.map(function(item) {
        return {
            label: item.label,
            data: [],
            borderColor: item.color,
            tension: 0.1,
            fill: false
        };
    });

    temperatureTrendChart = new Chart(canvas.getContext('2d'), {
        type: 'line',
        data: {
            labels: [],
            datasets: datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: false,
                    title: { display: true, text: 'Temperature (°C)' }
                },
                x: {
                    title: { display: true, text: 'Time' }
                }
            },
            plugins: {
                legend: { display: false }
            }
        }
    });
}

// Append new sensor data to the active temperature trend chart
function updateTemperatureTrendChart(data) {
    if (!temperatureTrendChart) return;

    const items = getSelectedGroupItems();
    const timestamp = data.timestamp ? new Date(data.timestamp).toLocaleTimeString() : new Date().toLocaleTimeString();

    const labels = temperatureTrendChart.data.labels;
    labels.push(timestamp);
    if (labels.length > MAX_CHART_POINTS) labels.shift();

    items.forEach(function(item, idx) {
        let value;
        if (item.key === 'temperatures') {
            value = (data.temperatures || [])[item.index];
        } else {
            value = data[item.key];
        }

        if (value === undefined || value < -100) {
            value = null;
        }

        const dataset = temperatureTrendChart.data.datasets[idx];
        if (dataset) {
            dataset.data.push(value);
            if (dataset.data.length > MAX_CHART_POINTS) dataset.data.shift();
        }
    });

    temperatureTrendChart.update('none');
}
