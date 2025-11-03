// Main JavaScript functionality for Customer Lookup Tool

// Global variables
let currentSessionId = null;
let progressInterval = null;

// Utility functions
function showNotification(message, type = 'info') {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
    notification.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
    notification.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;

    document.body.appendChild(notification);

    // Auto remove after 5 seconds
    setTimeout(() => {
        if (notification.parentNode) {
            notification.parentNode.removeChild(notification);
        }
    }, 5000);
}

function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// Form validation
function validateForm(formData) {
    const errors = [];

    if (!formData.address_line_1 || formData.address_line_1.trim() === '') {
        errors.push('Address is required');
    }

    if (!formData.county || formData.county.trim() === '') {
        errors.push('County is required');
    }

    // Validate ZIP code format if provided
    if (formData.zip_code && !/^\d{5}(-\d{4})?$/.test(formData.zip_code)) {
        errors.push('ZIP code must be in format 12345 or 12345-6789');
    }

    return errors;
}

// API functions
async function apiCall(url, options = {}) {
    try {
        const response = await fetch(url, {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            },
            ...options
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.error || `HTTP ${response.status}: ${response.statusText}`);
        }

        return await response.json();
    } catch (error) {
        console.error('API call failed:', error);
        throw error;
    }
}

// Lookup functions
async function startLookup(formData) {
    try {
        // Validate form data
        const errors = validateForm(formData);
        if (errors.length > 0) {
            throw new Error(errors.join(', '));
        }

        // Show loading state
        setFormLoading(true);

        // Start lookup
        const result = await apiCall('/api/lookup', {
            method: 'POST',
            body: JSON.stringify(formData)
        });

        currentSessionId = result.session_id;
        showNotification('Lookup started successfully!', 'success');

        // Start progress tracking
        startProgressTracking();

    } catch (error) {
        console.error('Error starting lookup:', error);
        showNotification('Error starting lookup: ' + error.message, 'danger');
        setFormLoading(false);
    }
}

function startProgressTracking() {
    let progress = 0;
    const progressBar = document.getElementById('progress-bar');
    const progressText = document.getElementById('progress-text');

    if (!progressBar || !progressText) return;

    progressInterval = setInterval(async () => {
        try {
            // Simulate progress
            progress += Math.random() * 5;
            if (progress > 85) progress = 85;

            progressBar.style.width = progress + '%';

            // Check actual status
            const session = await apiCall(`/api/lookup/${currentSessionId}`);

            if (session.error) {
                throw new Error(session.error);
            }

            updateStatusDisplay(session);

            if (session.status === 'completed') {
                progressBar.style.width = '100%';
                progressText.textContent = 'Lookup completed successfully!';

                setTimeout(() => {
                    hideProgressModal();
                    showResults(session);
                    setFormLoading(false);
                }, 1500);

            } else if (session.status === 'error') {
                throw new Error(session.error || 'Lookup failed');
            }

        } catch (error) {
            console.error('Error tracking progress:', error);
            progressText.textContent = 'Error: ' + error.message;

            setTimeout(() => {
                hideProgressModal();
                setFormLoading(false);
                showNotification('Lookup failed: ' + error.message, 'danger');
            }, 2000);
        }
    }, 2000);
}

function updateStatusDisplay(session) {
    const statusSection = document.getElementById('status-section');
    if (!statusSection) return;

    const statusBadge = getStatusBadge(session.status);

    statusSection.innerHTML = `
        <div class="d-flex justify-content-between align-items-center mb-3">
            <span class="fw-bold">Status:</span>
            ${statusBadge}
        </div>
        <div class="d-flex justify-content-between align-items-center mb-3">
            <span class="fw-bold">Address:</span>
            <span>${session.address}</span>
        </div>
        <div class="d-flex justify-content-between align-items-center mb-3">
            <span class="fw-bold">County:</span>
            <span>${session.county}</span>
        </div>
        <div class="d-flex justify-content-between align-items-center">
            <span class="fw-bold">Started:</span>
            <span>${formatDate(session.start_time)}</span>
        </div>
    `;
}

function getStatusBadge(status) {
    const badges = {
        'waiting': '<span class="badge bg-info"><i class="fas fa-hourglass-half me-1"></i>Waiting</span>',
        'running': '<span class="badge bg-warning"><i class="fas fa-spinner fa-spin me-1"></i>Running</span>',
        'completed': '<span class="badge bg-success"><i class="fas fa-check me-1"></i>Completed</span>',
        'error': '<span class="badge bg-danger"><i class="fas fa-exclamation-triangle me-1"></i>Error</span>',
        'cancelled': '<span class="badge bg-secondary"><i class="fas fa-times me-1"></i>Cancelled</span>'
    };
    return badges[status] || '<span class="badge bg-secondary">Unknown</span>';
}

function showResults(session) {
    const resultsSection = document.getElementById('results-section');
    const resultsContent = document.getElementById('results-content');

    if (!resultsSection || !resultsContent) return;

    let resultsHtml = '<h6 class="mb-3"><i class="fas fa-file-alt me-2"></i>Lookup Results:</h6>';

    if (session.results) {
        // Property Reports
        if (session.results.pdf_urls && session.results.pdf_urls.length > 0) {
            resultsHtml += `
                <div class="mb-4">
                    <h6 class="text-primary"><i class="fas fa-file-pdf me-2"></i>Property Reports (${session.results.pdf_urls.length})</h6>
                    <div class="row">
            `;

            session.results.pdf_urls.forEach((url, index) => {
                resultsHtml += `
                    <div class="col-md-6 mb-3">
                        <div class="card border-primary">
                            <div class="card-body">
                                <h6 class="card-title">Report ${index + 1}</h6>
                                <p class="card-text text-muted small">Property inspection report</p>
                                <a href="${url}" target="_blank" class="btn btn-primary btn-sm">
                                    <i class="fas fa-download me-1"></i>Download PDF
                                </a>
                            </div>
                        </div>
                    </div>
                `;
            });

            resultsHtml += '</div></div>';
        }

        // Location Code
        if (session.results.location_code) {
            resultsHtml += `
                <div class="mb-4">
                    <h6 class="text-success"><i class="fas fa-map-marker-alt me-2"></i>Location Code</h6>
                    <div class="alert alert-success">
                        <code>${session.results.location_code}</code>
                    </div>
                </div>
            `;
        }

        // Tacoma Reports
        if (session.results.tacoma_reports && session.results.tacoma_reports.length > 0) {
            resultsHtml += `
                <div class="mb-4">
                    <h6 class="text-info"><i class="fas fa-city me-2"></i>TPCHD REPORTS (${session.results.tacoma_reports.length})</h6>
                    <ul class="list-group">
            `;

            session.results.tacoma_reports.forEach((report, index) => {
                resultsHtml += `
                    <li class="list-group-item d-flex justify-content-between align-items-center">
                        <span>Report ${index + 1}</span>
                        <a href="${report}" target="_blank" class="btn btn-sm btn-outline-info">
                            <i class="fas fa-external-link-alt me-1"></i>View
                        </a>
                    </li>
                `;
            });

            resultsHtml += '</ul></div>';
        }
    }

    if (resultsHtml === '<h6 class="mb-3"><i class="fas fa-file-alt me-2"></i>Lookup Results:</h6>') {
        resultsHtml += '<div class="alert alert-info"><i class="fas fa-info-circle me-2"></i>No results found for this address.</div>';
    }

    resultsContent.innerHTML = resultsHtml;
    resultsSection.style.display = 'block';
    resultsSection.scrollIntoView({ behavior: 'smooth' });
}

// Form management
function setFormLoading(loading) {
    const submitBtn = document.getElementById('submit-btn');
    const form = document.getElementById('lookup-form');

    if (!submitBtn || !form) return;

    if (loading) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Starting...';

        // Disable form inputs
        const inputs = form.querySelectorAll('input, select');
        inputs.forEach(input => input.disabled = true);

        // Show progress modal
        const modal = new bootstrap.Modal(document.getElementById('progressModal'));
        modal.show();

    } else {
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<i class="fas fa-search me-2"></i>Start Lookup';

        // Enable form inputs
        const inputs = form.querySelectorAll('input, select');
        inputs.forEach(input => input.disabled = false);

        // Reset status section
        const statusSection = document.getElementById('status-section');
        if (statusSection) {
            statusSection.innerHTML = `
                <div class="text-center text-muted">
                    <i class="fas fa-search fa-3x mb-3"></i>
                    <p>No lookup in progress</p>
                </div>
            `;
        }

        // Hide results
        const resultsSection = document.getElementById('results-section');
        if (resultsSection) {
            resultsSection.style.display = 'none';
        }
    }
}

function hideProgressModal() {
    const modal = bootstrap.Modal.getInstance(document.getElementById('progressModal'));
    if (modal) {
        modal.hide();
    }

    if (progressInterval) {
        clearInterval(progressInterval);
        progressInterval = null;
    }
}

// Mobile sidebar toggle
function toggleSidebar() {
    const sidebar = document.querySelector('.sidebar');
    const overlay = document.querySelector('.mobile-overlay');

    sidebar.classList.toggle('show');
    overlay.classList.toggle('show');
}

function closeSidebar() {
    const sidebar = document.querySelector('.sidebar');
    const overlay = document.querySelector('.mobile-overlay');

    sidebar.classList.remove('show');
    overlay.classList.remove('show');
}

// Close sidebar when clicking outside on mobile
document.addEventListener('click', function (event) {
    const sidebar = document.querySelector('.sidebar');
    const mobileToggle = document.querySelector('.mobile-menu-toggle');
    const overlay = document.querySelector('.mobile-overlay');

    if (window.innerWidth <= 768 &&
        !sidebar.contains(event.target) &&
        !mobileToggle.contains(event.target) &&
        sidebar.classList.contains('show')) {
        closeSidebar();
    }
});

// Close sidebar when window is resized to desktop size
window.addEventListener('resize', function () {
    if (window.innerWidth > 768) {
        closeSidebar();
    }
});

// Close sidebar when navigation link is clicked on mobile
document.addEventListener('DOMContentLoaded', function () {
    const navLinks = document.querySelectorAll('.sidebar .nav-link');
    navLinks.forEach(link => {
        link.addEventListener('click', function () {
            if (window.innerWidth <= 768) {
                closeSidebar();
            }
        });
    });
});

// Event listeners
document.addEventListener('DOMContentLoaded', function () {
    // Form submission is handled directly in lookup.html template
    // to avoid conflicts with multiple event handlers

    // Cancel button
    const cancelBtn = document.getElementById('cancel-btn');
    if (cancelBtn) {
        cancelBtn.addEventListener('click', async function () {
            if (currentSessionId) {
                try {
                    await apiCall(`/api/lookup/${currentSessionId}/cancel`, {
                        method: 'POST'
                    });

                    hideProgressModal();
                    setFormLoading(false);
                    currentSessionId = null;

                    showNotification('Lookup cancelled successfully', 'warning');

                } catch (error) {
                    console.error('Error cancelling lookup:', error);
                    showNotification('Error cancelling lookup: ' + error.message, 'danger');
                }
            }
        });
    }

    // Auto-refresh dashboard if on dashboard page
    if (window.location.pathname === '/' || window.location.pathname === '/dashboard') {
        // Dashboard-specific functionality will be handled by dashboard.html
    }
});

// Export functions for use in templates
window.LookupTool = {
    startLookup,
    showNotification,
    formatDate,
    validateForm
};
