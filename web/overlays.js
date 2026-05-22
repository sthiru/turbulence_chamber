// Initialize temperature graph overlay
document.getElementById('showTemperatureGraphBtn').addEventListener('click', function(e) {
    e.preventDefault();
    const modal = new bootstrap.Modal(document.getElementById('temperatureGraphOverlay'));
    modal.show();
    
    // Initialize chart when modal is shown
    document.getElementById('temperatureGraphOverlay').addEventListener('shown.bs.modal', function() {
        initTemperatureTrendChart();
    }, { once: true });
});

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
let temperatureTrendChart = null;
function initTemperatureTrendChart() {
    const ctx = document.getElementById('temperatureTrendChart').getContext('2d');
    
    if (temperatureTrendChart) {
        temperatureTrendChart.destroy();
    }
    
    const sensorColors = [
        'rgb(75, 192, 192)',
        'rgb(255, 99, 132)',
        'rgb(54, 162, 235)',
        'rgb(153, 102, 255)',
        'rgb(255, 159, 64)',
        'rgb(255, 205, 86)',
        'rgb(75, 192, 192)',
        'rgb(199, 199, 199)',
        'rgb(83, 102, 255)',
        'rgb(40, 159, 64)',
        'rgb(210, 99, 132)',
        'rgb(255, 159, 64)'
    ];
    
    const datasets = [];
    for (let i = 0; i < 12; i++) {
        datasets.push({
            label: `Sensor ${i + 1}`,
            data: [],
            borderColor: sensorColors[i],
            tension: 0.1
        });
    }
    
    temperatureTrendChart = new Chart(ctx, {
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
                    title: {
                        display: true,
                        text: 'Temperature (°C)'
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
                    position: 'top'
                }
            }
        }
    });
}
