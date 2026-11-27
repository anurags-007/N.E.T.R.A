document.addEventListener('DOMContentLoaded', async () => {
    try {
        const user = await API.getMe();
        document.getElementById('userNameDisplay').textContent = user.username;
        const roleDisplay = document.getElementById('userRoleDisplay');
        if (roleDisplay) {
            roleDisplay.textContent = (user.rank || user.role).toUpperCase();
        }
        if (typeof setRoleBasedNav === 'function') setRoleBasedNav(user.role);
    } catch (_err) {
        window.location.href = 'index.html';
        return;
    }

    document.getElementById('logoutBtn')?.addEventListener('click', async (e) => {
        e.preventDefault();
        await API.logout();
        window.location.href = 'index.html';
    });

    document.getElementById('selectTowerFilesBtn')?.addEventListener('click', () => {
        document.getElementById('towerFileInput')?.click();
    });

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
                const response = await apiFetch(`/tools/ip-lookup?query=${encodeURIComponent(input)}`);

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.detail || 'Lookup failed');
                }

                // Populate Results
                document.getElementById('resIP').textContent = data.resolved_ip || data.query;
                document.getElementById('resISP').textContent = data.isp || 'Unknown';
                document.getElementById('resCity').textContent = data.city || 'N/A';
                document.getElementById('resRegion').textContent = data.region || 'N/A';
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

    // Setup Tower Dump Analysis & Co-Location Engine
    setupTowerDump();
    setupTowerCoLocation();
});

async function setupTowerCoLocation() {
    const caseSel = document.getElementById('coLocCaseSelect');
    const winSel = document.getElementById('coLocWindowSelect');
    const runBtn = document.getElementById('runCoLocBtn');
    const statusEl = document.getElementById('coLocStatus');
    const wrapEl = document.getElementById('coLocTableWrap');
    const tbody = document.getElementById('coLocTableBody');
    if (!caseSel || !runBtn) return;

    try {
        const cases = await API.getCases();
        caseSel.innerHTML = '';
        if (cases.length === 0) {
            const opt = document.createElement('option');
            opt.value = '';
            opt.textContent = 'No accessible cases found';
            caseSel.appendChild(opt);
            runBtn.disabled = true;
            return;
        }
        cases.forEach(c => {
            const opt = document.createElement('option');
            opt.value = c.id;
            opt.textContent = `${c.fir_number} — ${c.police_station}`;
            caseSel.appendChild(opt);
        });
    } catch (_err) {
        caseSel.innerHTML = '<option value="">Failed to load cases</option>';
    }

    runBtn.addEventListener('click', async () => {
        const cid = caseSel.value;
        if (!cid) return;
        const winMin = parseInt(winSel?.value || '15', 10);
        runBtn.disabled = true;
        statusEl.textContent = 'Scanning encrypted CDR/tower files...';
        wrapEl.classList.add('d-none');
        tbody.innerHTML = '';

        try {
            const data = await API.analyzeTowerCoLocation(cid, winMin);
            statusEl.textContent = `Scanned ${data.files_scanned} file(s) | Found ${data.total_pairs} co-located pair(s) within ±${data.window_minutes} min.`;
            wrapEl.classList.remove('d-none');

            if (!data.pairs || data.pairs.length === 0) {
                const tr = document.createElement('tr');
                const td = document.createElement('td');
                td.colSpan = 5;
                td.className = 'text-center text-muted py-3';
                td.textContent = 'No co-located MSISDN pairs found in this time window.';
                tr.appendChild(td);
                tbody.appendChild(tr);
                return;
            }

            data.pairs.forEach(p => {
                const tr = document.createElement('tr');
                const tdA = document.createElement('td');
                tdA.className = 'font-monospace fw-bold';
                tdA.textContent = p.msisdn_a;
                const tdB = document.createElement('td');
                tdB.className = 'font-monospace fw-bold';
                tdB.textContent = p.msisdn_b;
                const tdTower = document.createElement('td');
                tdTower.textContent = `${p.tower_name} (Cell ${p.cell_id}, LAC ${p.lac})`;
                const tdHits = document.createElement('td');
                const badge = document.createElement('span');
                badge.className = 'badge bg-danger';
                badge.textContent = `${p.co_location_count} hit(s)`;
                tdHits.appendChild(badge);
                const tdDelta = document.createElement('td');
                tdDelta.textContent = `${p.min_delta_minutes} min`;
                tr.append(tdA, tdB, tdTower, tdHits, tdDelta);
                tbody.appendChild(tr);
            });
        } catch (err) {
            statusEl.textContent = `Error: ${err.message}`;
        } finally {
            runBtn.disabled = false;
        }
    });
}

function setupTowerDump() {
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

        fileList.innerHTML = '';
        selectedFiles.forEach(f => {
            const div = document.createElement('div');
            div.className = 'text-success';
            const icon = document.createElement('i');
            icon.className = 'bi bi-file-earmark-excel-fill me-1';
            div.appendChild(icon);
            div.appendChild(document.createTextNode(`${f.name} (${(f.size / 1024).toFixed(1)} KB)`));
            fileList.appendChild(div);
        });

        analyzeBtn.disabled = selectedFiles.length < 2;

        if (selectedFiles.length < 2 && selectedFiles.length > 0) {
            const warn = document.createElement('div');
            warn.className = 'text-danger mt-1 small';
            warn.innerHTML = '<i class="bi bi-exclamation-circle"></i> Please upload at least 2 files.';
            fileList.appendChild(warn);
        }
    }

    analyzeBtn.addEventListener('click', async () => {
        document.getElementById('towerLoading').classList.remove('d-none');
        document.getElementById('towerResults').classList.add('d-none');
        analyzeBtn.disabled = true;

        const formData = new FormData();
        selectedFiles.forEach(file => formData.append('files', file));

        try {
            const response = await apiFetch(`/tools/analyze-tower-dump`, {
                method: 'POST',
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
                    const tdVal = document.createElement('td');
                    tdVal.className = 'fw-bold text-dark font-monospace';
                    tdVal.textContent = val;

                    const tdAction = document.createElement('td');
                    const link = document.createElement('a');
                    link.href = `analytics.html?search=${encodeURIComponent(val)}`;
                    link.target = '_blank';
                    link.rel = 'noopener noreferrer';
                    link.className = 'btn btn-xs btn-outline-primary';
                    link.style.fontSize = '0.7rem';
                    link.innerHTML = '<i class="bi bi-graph-up"></i> Investigate';
                    tdAction.appendChild(link);

                    tr.appendChild(tdVal);
                    tr.appendChild(tdAction);
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
        if (!ph) {
            if (typeof showToast === 'function') showToast(msg, type);
            return;
        }
        ph.innerHTML = `
            <div class="alert alert-${escapeHtml(type)} alert-dismissible fade show" role="alert">
                <i class="bi bi-exclamation-triangle-fill me-2"></i><span class="alert-msg"></span>
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `;
        ph.querySelector('.alert-msg').textContent = msg;
        setTimeout(() => {
            ph.innerHTML = '';
        }, 5000);
    }
}
