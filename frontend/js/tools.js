document.addEventListener('DOMContentLoaded', () => {
    // Check Auth
    const token = localStorage.getItem('token');
    if (!token) {
        window.location.href = 'index.html';
        return;
    }

    // Set Username
    // Set Username and Role
    const payload = JSON.parse(atob(token.split('.')[1]));
    const username = payload.sub;
    const role = payload.role;
    const rank = payload.rank || role;

    // Display
    document.getElementById('userNameDisplay').textContent = username;
    const roleDisplay = document.getElementById('userRoleDisplay');
    if (roleDisplay) {
        roleDisplay.textContent = rank.toUpperCase();
    }

    // Setup IP Lookup
    const form = document.getElementById('ipLookupForm');
    if (form) {
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const input = document.getElementById('ipInput').value;

            // UI States
            document.getElementById('loadingSpinner').classList.remove('d-none');
            document.getElementById('resultContainer').classList.add('d-none');
            document.getElementById('errorContainer').classList.add('d-none');

            try {
                const response = await fetch(`${API_URL}/tools/ip-lookup?query=${encodeURIComponent(input)}`, {
                    headers: {
                        'Authorization': `Bearer ${token}`
                    }
                });

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.detail || 'Lookup failed');
                }

                // Populate Results
                document.getElementById('resIP').textContent = data.resolved_ip || data.query;
                document.getElementById('resISP').textContent = data.isp || 'Unknown';
                document.getElementById('resCity').textContent = data.city || 'N/A';
                document.getElementById('resRegion').textContent = data.country || 'N/A';
                document.getElementById('resCountry').textContent = data.country || 'N/A';

                document.getElementById('mapLink').href = data.map_url;

                // Handle Mobile Warning
                if (data.is_mobile) {
                    document.getElementById('mobileWarning').classList.remove('d-none');
                } else {
                    document.getElementById('mobileWarning').classList.add('d-none');
                }

                // Handle Private IP / App Note
                if (data.note) {
                    document.getElementById('privateIpNote').textContent = data.note;
                    document.getElementById('privateIpWarning').classList.remove('d-none');
                } else {
                    document.getElementById('privateIpWarning').classList.add('d-none');
                }

                // Show Result
                document.getElementById('resultContainer').classList.remove('d-none');

            } catch (error) {
                document.getElementById('errorMessage').textContent = error.message;
                document.getElementById('errorContainer').classList.remove('d-none');
            } finally {
                document.getElementById('loadingSpinner').classList.add('d-none');
            }
        });
    }

    // Setup Tower Dump Analysis
    setupTowerDump(token);
});

function setupTowerDump(token) {
    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('towerFileInput');
    const fileList = document.getElementById('fileList');
    const analyzeBtn = document.getElementById('analyzeBtn');
    let selectedFiles = [];

    if (!dropZone) return;

    // Drag & Drop Handlers
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('bg-white', 'border-primary');
    });

    dropZone.addEventListener('dragleave', (e) => {
        e.preventDefault();
        dropZone.classList.remove('bg-white', 'border-primary');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('bg-white', 'border-primary');
        handleFiles(e.dataTransfer.files);
    });

    fileInput.addEventListener('change', (e) => {
        handleFiles(e.target.files);
    });

    function handleFiles(files) {
        selectedFiles = Array.from(files).filter(f => f.name.match(/\.(xlsx|xls|csv)$/i));

        fileList.innerHTML = selectedFiles.map(f =>
            `<div class="text-success"><i class="bi bi-file-earmark-excel-fill"></i> ${f.name} (${(f.size / 1024).toFixed(1)} KB)</div>`
        ).join('');

        analyzeBtn.disabled = selectedFiles.length < 2;

        if (selectedFiles.length < 2 && selectedFiles.length > 0) {
            fileList.innerHTML += `<div class="text-danger mt-1 small"><i class="bi bi-exclamation-circle"></i> Please upload at least 2 files.</div>`;
        }
    }

    analyzeBtn.addEventListener('click', async () => {
        document.getElementById('towerLoading').classList.remove('d-none');
        document.getElementById('towerResults').classList.add('d-none');
        analyzeBtn.disabled = true;

        const formData = new FormData();
        selectedFiles.forEach(file => formData.append('files', file));

        try {
            const response = await fetch(`${API_URL}/tools/analyze-tower-dump`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`
                },
                body: formData
            });

            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.detail || 'Analysis Failed');
            }

            const data = await response.json();

            // Render Results
            // Render Counts
            const total = (data.counts.mobile) + (data.counts.account) + (data.counts.upi);
            document.getElementById('commonCount').textContent = total;
            document.getElementById('countMobile').textContent = data.counts.mobile;
            document.getElementById('countAccount').textContent = data.counts.account;
            document.getElementById('countUPI').textContent = data.counts.upi;

            // Helper to render tables
            const renderTable = (tbodyId, list, type) => {
                const tbody = document.getElementById(tbodyId);
                tbody.innerHTML = '';
                if (list.length === 0) {
                    tbody.innerHTML = `<tr><td colspan="2" class="text-center text-muted">No common ${type}s found.</td></tr>`;
                    return;
                }
                list.forEach(val => {
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td class="fw-bold text-dark font-monospace">${val}</td>
                        <td>
                            <a href="analytics.html?search=${val}" target="_blank" class="btn btn-xs btn-outline-primary" style="font-size: 0.7rem;">
                                <i class="bi bi-graph-up"></i> Investigate
                            </a>
                        </td>
                    `;
                    tbody.appendChild(tr);
                });
            };

            renderTable('commonNumbersBody', data.common_numbers, 'Mobile');
            renderTable('commonAccountsBody', data.common_accounts, 'Account');
            renderTable('commonUPIBody', data.common_upis, 'UPI');

            document.getElementById('towerResults').classList.remove('d-none');

        } catch (err) {
            showAlert('danger', 'Error: ' + err.message);
        } finally {
            document.getElementById('towerLoading').classList.add('d-none');
            analyzeBtn.disabled = false;
        }
    });

    function showAlert(type, msg) {
        const ph = document.getElementById('alertPlaceholder');
        if (!ph) { alert(msg); return; }
        ph.innerHTML = `
            <div class="alert alert-${type} alert-dismissible fade show" role="alert">
                <i class="bi bi-exclamation-triangle-fill me-2"></i>${msg}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `;
        setTimeout(() => {
            ph.innerHTML = '';
        }, 5000);
    }
}
