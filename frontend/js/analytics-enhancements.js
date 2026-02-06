// PDF Export using jsPDF
async function exportToPDF() {
    const { jsPDF } = window.jspdf;

    // Show loading state
    const btn = document.querySelector('button[onclick="exportToPDF()"]');
    const originalText = btn.innerHTML;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Generating...';
    btn.disabled = true;

    try {
        const doc = new jsPDF();

        // Colors
        const primaryColor = [13, 110, 253]; // #0d6efd
        const secondaryColor = [108, 117, 125]; // #6c757d

        // --- HEADER ---
        // Blue Top Bar
        doc.setFillColor(...primaryColor);
        doc.rect(0, 0, 210, 20, 'F');

        // Title
        doc.setTextColor(255, 255, 255);
        doc.setFont("helvetica", "bold");
        doc.setFontSize(16);
        doc.text("POLICE INTELLIGENCE REPORT", 105, 13, { align: "center" });

        // Report Info
        doc.setTextColor(0, 0, 0);
        doc.setFontSize(10);
        doc.text(`Generated: ${new Date().toLocaleString()}`, 15, 30);
        doc.text("Classification: CONFIDENTIAL / INTERNAL USE ONLY", 15, 35);

        doc.setDrawColor(...secondaryColor);
        doc.line(15, 38, 195, 38);

        let yPos = 45;

        // --- SECTION 1: FINANCIAL FRAUD DASHBOARD SUMMARY ---
        doc.setFontSize(14);
        doc.setFont("helvetica", "bold");
        doc.text("1. Financial Fraud Snapshot", 15, yPos);
        yPos += 10;

        // KPI Grid simulation
        const headers = [["Amount at Risk", "Bank Requests", "Frozen Amount", "Avg Response"]];
        const data = [[
            document.getElementById('amountAtRisk')?.innerText || 'N/A',
            document.getElementById('bankRequestsSent')?.innerText || '0',
            document.getElementById('freezeConfirmed')?.innerText || '0',
            document.getElementById('avgResponseTime')?.innerText || '-'
        ]];

        doc.autoTable({
            startY: yPos,
            head: headers,
            body: data,
            theme: 'grid',
            headStyles: { fillColor: primaryColor, textColor: 255, fontStyle: 'bold' },
            styles: { fontSize: 11, cellPadding: 5 }
        });

        yPos = doc.lastAutoTable.finalY + 15;

        // --- SECTION 2: TOP FRAUD TYPES ---
        doc.text("2. Fraud Pattern Analysis", 15, yPos);
        yPos += 8;

        // We can grab text content from the breakdown list
        const breakdownDiv = document.getElementById('fraudTypeBreakdown');
        if (breakdownDiv) {
            const listItems = breakdownDiv.innerText.split('\n').filter(l => l.trim().length > 0);
            const breakdownData = listItems.map(item => [item]);

            doc.autoTable({
                startY: yPos,
                body: breakdownData,
                theme: 'plain',
                styles: { fontSize: 10, cellPadding: 2 }
            });
            yPos = doc.lastAutoTable.finalY + 10;
        }

        // --- SECTION 3: REPEAT ENTITIES ---
        doc.setTextColor(220, 53, 69); // Red
        doc.text("3. Critical Repeat Offenders (Alerts)", 15, yPos);
        doc.setTextColor(0, 0, 0);
        yPos += 8;

        const alertsDiv = document.getElementById('repeatEntitiesAlert');
        if (alertsDiv) {
            const alertItems = alertsDiv.innerText.split('\n').filter(l => l.trim().length > 0);
            const alertData = alertItems.map(item => [item]);

            doc.autoTable({
                startY: yPos,
                body: alertData,
                theme: 'striped',
                bodyStyles: { textColor: [220, 53, 69] }, // Red Text
                styles: { fontSize: 10 }
            });
        }

        // Footer
        const pageCount = doc.internal.getNumberOfPages();
        for (let i = 1; i <= pageCount; i++) {
            doc.setPage(i);
            doc.setFontSize(8);
            doc.setTextColor(150);
            doc.text(`Page ${i} of ${pageCount} - N.E.T.R.A. System`, 105, 290, { align: "center" });
        }

        doc.save(`NETRA_Intel_Report_${new Date().toISOString().slice(0, 10)}.pdf`);

    } catch (err) {
        showNotification("Failed to generate PDF report: " + err.message, 'danger');
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}

// CSV Export
function exportToCSV() {
    // Export repeat entities as CSV
    fetch('http://localhost:8001/analytics/repeat-entities', {
        headers: {
            'Authorization': `Bearer ${token}`
        }
    })
        .then(res => res.json())
        .then(data => {
            if (data.alerts && data.alerts.length > 0) {
                let csv = 'Alert Level,Entity Type,Identifier,Linked Cases,FIR Numbers\n';
                data.alerts.forEach(alert => {
                    csv += `${alert.alert_level},${alert.type},${alert.identifier},${alert.linked_cases_count},"${alert.fir_numbers.join(', ')}"\n`;
                });

                const blob = new Blob([csv], { type: 'text/csv' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `RepeatEntities_${new Date().toISOString().split('T')[0]}.csv`;
                a.click();
            } else {
                showNotification('No repeat entities to export', 'info');
            }
        })
        .catch(err => {
            showNotification('Failed to export CSV', 'danger');
        });
}

// Filter Management
let currentFilters = {
    dateRange: '7',
    fraudType: 'all',
    amountRange: 'all',
    zone: 'all'
};

// Date range filter change handler
document.getElementById('dateRangeFilter')?.addEventListener('change', function (e) {
    const customRange = document.getElementById('customDateRange');
    if (e.target.value === 'custom') {
        customRange.style.display = 'flex';
    } else {
        customRange.style.display = 'none';
    }
});

function applyFilters() {
    currentFilters = {
        dateRange: document.getElementById('dateRangeFilter').value,
        fraudType: document.getElementById('fraudTypeFilter').value,
        amountRange: document.getElementById('amountRangeFilter').value,
        zone: document.getElementById('zoneFilter').value
    };

    // If custom date range
    if (currentFilters.dateRange === 'custom') {
        currentFilters.fromDate = document.getElementById('fromDate').value;
        currentFilters.toDate = document.getElementById('toDate').value;
    }

    // Reload dashboard with filters
    loadFinancialDashboard();

    // Show notification
    showNotification('Filters applied successfully', 'success');
}

function resetFilters() {
    document.getElementById('dateRangeFilter').value = '7';
    document.getElementById('fraudTypeFilter').value = 'all';
    document.getElementById('amountRangeFilter').value = 'all';
    document.getElementById('zoneFilter').value = 'all';
    document.getElementById('customDateRange').style.display = 'none';

    currentFilters = {
        dateRange: '7',
        fraudType: 'all',
        amountRange: 'all',
        zone: 'all'
    };

    loadFinancialDashboard();
    showNotification('Filters reset', 'info');
}

// Auto-refresh functionality
let autoRefreshInterval = null;
let lastRepeatEntityCount = 0;

function startAutoRefresh() {
    const toggle = document.getElementById('autoRefreshToggle');
    if (toggle && toggle.checked) {
        // Refresh every 30 seconds
        autoRefreshInterval = setInterval(() => {
            loadFinancialDashboard();
        }, 30000);
    }
}

function stopAutoRefresh() {
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
        autoRefreshInterval = null;
    }
}

// Toggle auto-refresh
document.getElementById('autoRefreshToggle')?.addEventListener('change', function (e) {
    if (e.target.checked) {
        startAutoRefresh();
        showNotification('Auto-refresh enabled (30s)', 'info');
    } else {
        stopAutoRefresh();
        showNotification('Auto-refresh disabled', 'info');
    }
});

// Notification system
function showNotification(message, type = 'info') {
    const notifDiv = document.createElement('div');
    notifDiv.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
    notifDiv.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
    notifDiv.innerHTML = `
        <i class="bi bi-info-circle-fill me-2"></i>${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    document.body.appendChild(notifDiv);

    setTimeout(() => {
        notifDiv.remove();
    }, 5000);
}

// Check for new repeat entities (for live notifications)
function checkForNewAlerts(data) {
    if (data.total_repeat_entities > lastRepeatEntityCount && lastRepeatEntityCount > 0) {
        const newCount = data.total_repeat_entities - lastRepeatEntityCount;
        showNotification(`⚠️ ${newCount} NEW repeat entity alert(s) detected!`, 'warning');

        // Play alert sound (optional)
        // new Audio('/sounds/alert.mp3').play();
    }
    lastRepeatEntityCount = data.total_repeat_entities;
}
