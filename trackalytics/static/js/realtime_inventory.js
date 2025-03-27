// trackalytics/static/js/realtime_inventory.js

// Initialize Toastr
toastr.options = {
    positionClass: "toast-bottom-right",
    preventDuplicates: true,
    showDuration: "300",
    hideDuration: "1000",
    timeOut: "5000",
    extendedTimeOut: "1000",
    closeButton: true,
    progressBar: true
};

// Connect to the SSE stream
function connectSSE() {
    const eventSource = new EventSource('/inventory/stream/');
    
    eventSource.onmessage = function(e) {
        const data = JSON.parse(e.data);
        
        // Update low stock alerts
        if (data.low_stock && data.low_stock.length > 0) {
            updateLowStockAlerts(data.low_stock);
        }
        
        // Show notifications
        if (data.notifications && data.notifications.length > 0) {
            showNotifications(data.notifications);
        }
    };
    
    eventSource.onerror = function() {
        // Try to reconnect after 5 seconds
        setTimeout(connectSSE, 5000);
    };
}

// Update low stock alerts display
function updateLowStockAlerts(lowStockItems) {
    const alertContainer = document.getElementById('low-stock-alerts');
    if (alertContainer) {
        alertContainer.innerHTML = lowStockItems.map(item => `
            <div class="alert alert-warning mb-2">
                <strong>${item.product_name}</strong><br>
                Current: ${item.total_quantity}<br>
                Threshold: ${item.low_stock_threshold}
            </div>
        `).join('');
    }
}

// Show notifications to user
function showNotifications(notifications) {
    notifications.forEach(notification => {
        toastr.warning(notification.message);
        
        // Mark as read when shown
        fetch(`/notifications/mark-read/${notification.id}/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCookie('csrftoken'),
                'Content-Type': 'application/json'
            },
            credentials: 'same-origin'
        });
    });
}

// Start the connection when page loads
document.addEventListener('DOMContentLoaded', connectSSE);