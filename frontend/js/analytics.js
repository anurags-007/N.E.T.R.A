const token = localStorage.getItem('token');
let outgoingChart = null;
let hourlyChart = null;

if (!token) {
    window.location.href = 'index.html';
}

async function init() {
    try {
        const user = await API.getMe(token);

        // Fix Profile Display
        document.getElementById('userNameDisplay').textContent = user.username;
        const roleDisplay = document.getElementById('userRoleDisplay');
        if (roleDisplay) {
            roleDisplay.textContent = (user.rank || user.role).toUpperCase();
        }

        loadCases();
    } catch (err) {
        console.error(err);
        window.location.href = 'index.html';
    }
}

async function loadCases() {
    try {
        const cases = await API.getCases(token);
        const select = document.getElementById('caseSelect');
        cases.forEach(c => {
            const opt = document.createElement('option');
            opt.value = c.id;
            opt.innerText = `${c.fir_number} - ${c.police_station}`;
            select.appendChild(opt);
        });
    } catch (err) {
        console.error(err);
    }
}

// Case Select Change: Load Evidence
document.getElementById('caseSelect').addEventListener('change', async (e) => {
    const caseId = e.target.value;
    const evSelect = document.getElementById('evidenceSelect');
    evSelect.innerHTML = '<option value="">Loading...</option>';
    evSelect.disabled = true;

    if (!caseId) {
        evSelect.innerHTML = '<option value="">Choose...</option>';
        return;
    }

    try {
        const evidence = await API.getEvidence(token, caseId);
        // Filter for potential CDRs (CSV/Excel)
        const cdrs = evidence.filter(ev => ev.file_type === 'CDR_CSV');

        evSelect.innerHTML = '';
        if (cdrs.length === 0) {
            evSelect.innerHTML = '<option value="">No CDR files found</option>';
        } else {
            cdrs.forEach(ev => {
                const opt = document.createElement('option');
                opt.value = ev.id;
                opt.innerText = `${ev.original_filename} (${ev.uploaded_at})`;
                evSelect.appendChild(opt);
            });
            evSelect.disabled = false;
        }

    } catch (err) {
        console.error(err);
        evSelect.innerHTML = '<option value="">Error loading files</option>';
    }
});

// Run Analysis
document.getElementById('analysisForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const evidenceId = document.getElementById('evidenceSelect').value;
    if (!evidenceId) return;

    try {
        // Show Loading?
        const results = await API.analyzeCDR(token, evidenceId);
        renderResults(results);
    } catch (err) {
        showAlert('danger', err.message);
    }
});

function renderResults(data) {
    document.getElementById('resultsSection').classList.remove('d-none');

    // KPIs
    document.getElementById('totalCalls').innerText = data.total_calls;
    document.getElementById('totalDuration').innerText = (data.total_duration / 60).toFixed(1);

    // Active Hour Logic
    let maxCalls = 0;
    let maxHour = '-';
    for (const [hour, count] of Object.entries(data.hourly_stats)) {
        if (count > maxCalls) {
            maxCalls = count;
            maxHour = `${hour}:00`;
        }
    }
    const activeHourEl = document.getElementById('activeHour');
    if (activeHourEl) activeHourEl.innerText = maxHour;

    // Charts
    renderOutgoingChart(data.top_contacts_outgoing);
    renderHourlyChart(data.hourly_stats);
}

function renderOutgoingChart(data) {
    const ctx = document.getElementById('outgoingChart').getContext('2d');
    const labels = Object.keys(data);
    const values = Object.values(data);

    if (outgoingChart) outgoingChart.destroy();

    outgoingChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: '# of Calls',
                data: values,
                backgroundColor: 'rgba(54, 162, 235, 0.6)',
                borderColor: 'rgba(54, 162, 235, 1)',
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            scales: {
                y: { beginAtZero: true }
            }
        }
    });
}

function renderHourlyChart(data) {
    const ctx = document.getElementById('hourlyChart').getContext('2d');
    // Ensure all 24 hours exist
    const labels = Array.from({ length: 24 }, (_, i) => i);
    const values = labels.map(h => data[h] || 0);

    if (hourlyChart) hourlyChart.destroy();

    hourlyChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Calls per Hour',
                data: values,
                backgroundColor: 'rgba(255, 99, 132, 0.2)',
                borderColor: 'rgba(255, 99, 132, 1)',
                borderWidth: 2,
                fill: true,
                tension: 0.4
            }]
        },
        options: {
            responsive: true,
            scales: {
                y: { beginAtZero: true }
            }
        }
    });
}

// Enhanced Universal Search Logic
document.getElementById('globalSearchForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const query = document.getElementById('searchQuery').value.trim();
    const searchType = document.getElementById('searchType').value;
    const resDiv = document.getElementById('searchResults');

    resDiv.innerHTML = '<div class="text-center py-3"><div class="spinner-border text-light" role="status"></div><p class="mt-2">Searching across all databases...</p></div>';

    try {
        const response = await fetch(`http://localhost:8001/analysis/universal-search?query=${encodeURIComponent(query)}&search_type=${searchType}`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (!response.ok) throw new Error('Search failed');

        const data = await response.json();

        resDiv.innerHTML = ''; // Clear

        if (data.count === 0) {
            resDiv.innerHTML = `
                <div class="alert alert-light mt-3 mb-0 text-dark">
                    <i class="bi bi-info-circle"></i> No records found for "${query}"
                    <p class="small mb-0 mt-2 opacity-75">Try searching with a different identifier or check for typos.</p>
                </div>
            `;
        } else {
            // Results Header
            const header = document.createElement('div');
            header.className = 'alert alert-success mt-3 mb-3';
            header.innerHTML = `
                <div class="d-flex justify-content-between align-items-center">
                    <div>
                        <strong><i class="bi bi-check-circle-fill"></i> Match Found!</strong>
                        <span class="ms-2">${data.count} result(s) for "${query}"</span>
                    </div>
                    <div>
                        <span class="badge bg-white text-dark me-1">Search Type: ${data.search_type.toUpperCase()}</span>
                    </div>
                </div>
            `;
            resDiv.appendChild(header);

            // Summary Stats
            if (data.summary) {
                const summaryDiv = document.createElement('div');
                summaryDiv.className = 'row g-2 mb-3';

                const sources = [
                    { key: 'telecom_requests', label: 'Telecom Requests', icon: 'bi-telephone' },
                    { key: 'financial_entities', label: 'Financial Entities', icon: 'bi-currency-rupee' },
                    { key: 'case_records', label: 'Case Records', icon: 'bi-folder' },
                    { key: 'transaction_timeline', label: 'Timeline Mentions', icon: 'bi-clock-history' }
                ];

                sources.forEach(source => {
                    if (data.summary[source.key] > 0) {
                        summaryDiv.innerHTML += `
                            <div class="col-md-3">
                                <div class="bg-white text-dark p-2 rounded">
                                    <i class="bi ${source.icon}"></i> 
                                    <strong>${data.summary[source.key]}</strong> ${source.label}
                                </div>
                            </div>
                        `;
                    }
                });

                resDiv.appendChild(summaryDiv);
            }

            // Grouped Results
            const resultsContainer = document.createElement('div');
            resultsContainer.className = 'mt-3';

            // Group by source
            const grouped = {};
            data.matches.forEach(match => {
                if (!grouped[match.source]) {
                    grouped[match.source] = [];
                }
                grouped[match.source].push(match);
            });

            // Display each group
            for (const [source, matches] of Object.entries(grouped)) {
                const groupDiv = document.createElement('div');
                groupDiv.className = 'mb-3';

                const sourceIcons = {
                    'Telecom Request': 'bi-telephone',
                    'Financial Entity': 'bi-currency-rupee',
                    'Case Record': 'bi-folder',
                    'Transaction Timeline': 'bi-clock-history'
                };

                groupDiv.innerHTML = `
                    <h6 class="text-white mb-2">
                        <i class="bi ${sourceIcons[source] || 'bi-database'}"></i> 
                        ${source} (${matches.length})
                    </h6>
                `;

                const table = document.createElement('div');
                table.className = 'table-responsive';
                table.innerHTML = `
                    <table class="table table-sm table-light">
                        <thead>
                            <tr>
                                <th>FIR Number</th>
                                <th>Match Type</th>
                                <th>Matched Value</th>
                                <th>Case Type</th>
                                <th>Status</th>
                                <th>Action</th>
                            </tr>
                        </thead>
                        <tbody id="results-${source.replace(' ', '-')}"></tbody>
                    </table>
                `;

                groupDiv.appendChild(table);
                resultsContainer.appendChild(groupDiv);

                // Populate table
                const tbody = table.querySelector('tbody');
                matches.forEach(match => {
                    const row = document.createElement('tr');

                    const statusBadge = match.status === 'active' ? 'success' : 'secondary';

                    row.innerHTML = `
                        <td><strong>${match.fir_number || 'N/A'}</strong></td>
                        <td><span class="badge bg-info">${match.match_type}</span></td>
                        <td><small>${escapeHtml(match.matched_value || '')}</small></td>
                        <td>${formatCaseType(match.case_type || 'N/A')}</td>
                        <td><span class="badge bg-${statusBadge}">${match.status || 'N/A'}</span></td>
                        <td><a href="case_detail.html?id=${match.case_id}" class="btn btn-sm btn-primary" target="_blank">View Case</a></td>
                    `;

                    tbody.appendChild(row);
                });
            }

            resDiv.appendChild(resultsContainer);
        }
    } catch (err) {
        resDiv.innerHTML = `
            <div class="alert alert-danger mt-3 mb-0">
                <i class="bi bi-exclamation-triangle"></i> Error: ${escapeHtml(err.message)}
            </div>
        `;
    }
});

// Helper function to update placeholder based on search type
function updateSearchPlaceholder() {
    const searchType = document.getElementById('searchType').value;
    const searchInput = document.getElementById('searchQuery');

    const placeholders = {
        'auto': 'Enter any identifier - system will detect type automatically',
        'mobile': 'Enter mobile number (e.g., 9876543210)',
        'upi': 'Enter UPI ID (e.g., user@paytm)',
        'account': 'Enter bank account number (e.g., 1234567890123)',
        'name': 'Enter suspect/victim name (e.g., Rahul Kumar)',
        'fir': 'Enter FIR number (e.g., FIR/123/2026)'
    };

    searchInput.placeholder = placeholders[searchType] || placeholders['auto'];
}

// Helper function to format case type
function formatCaseType(type) {
    if (!type || type === 'N/A') return 'N/A';
    return type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
}

// Helper function to escape HTML - Handled by security.js

// Get Comprehensive Investigation Report - ONE CLICK ALL DATA!
async function getComprehensiveReport(event) {
    event.preventDefault();
    const query = document.getElementById('searchQuery').value.trim();
    const resDiv = document.getElementById('searchResults');

    if (!query) {
        resDiv.innerHTML = '<div class="alert alert-warning">Please enter an identifier first</div>';
        return;
    }

    resDiv.innerHTML = '<div class="text-center py-4"><div class="spinner-border text-light"></div><p class="mt-3">Generating comprehensive investigation report...</p></div>';

    try {
        const response = await fetch(`http://localhost:8001/analysis/comprehensive-investigation-data?identifier=${encodeURIComponent(query)}`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (!response.ok) throw new Error('Failed to fetch investigation data');

        const data = await response.json();

        resDiv.innerHTML = '';

        // Header
        const header = document.createElement('div');
        header.className = 'alert alert-light border shadow-sm mt-3 mb-4';
        header.innerHTML = safeHTML(`
            <div class="d-flex justify-content-between align-items-center">
                <div>
                   <h5 class="fw-bold mb-1"><i class="bi bi-person-badge-fill text-primary"></i> Subject Intelligence Profile</h5>
                   <p class="mb-0 text-muted">Identifier: <strong class="font-monospace text-dark">${escapeHtml(query)}</strong></p>
                </div>
                <div class="text-end">
                    <span class="badge bg-secondary p-2">Generated: ${new Date().toLocaleString()}</span>
                </div>
            </div>
        `);
        resDiv.appendChild(header);

        // --- NEW: INTELLIGENCE RISK CARD ---
        if (data.risk_profile) {
            const risk = data.risk_profile;
            const riskCard = document.createElement('div');
            riskCard.className = `card mb-4 border-start border-5 border-${risk.color} shadow-sm`;
            // Add a subtle background tint based on risk
            riskCard.style.background = `linear-gradient(to right, var(--bs-${risk.color}-bg-subtle), #fff)`;

            let tagsHtml = '';
            risk.tags.forEach(tag => {
                tagsHtml += `<span class="badge bg-dark me-1 mb-1"><i class="bi bi-tag-fill"></i> ${tag}</span>`;
            });

            // Action advice based on priority
            let actionAdvice = "";
            if (risk.priority === "IMMEDIATE ACTION") {
                actionAdvice = "Recommended: Immediate freeze of linked accounts & issuance of NBW if identity verified.";
            } else if (risk.priority === "PRIORITY INVESTIGATION") {
                actionAdvice = "Recommended: Prioritize evidence collection and cross-referencing with other districts.";
            } else {
                actionAdvice = "Recommended: Routine monitoring.";
            }

            riskCard.innerHTML = `
                <div class="card-body">
                    <div class="row align-items-center">
                        <div class="col-md-3 text-center border-end">
                            <h6 class="text-muted fw-bold mb-2">RISK SCORE</h6>
                            <h1 class="display-3 fw-bold text-${risk.color} mb-0">${risk.score}</h1>
                            <span class="badge bg-${risk.color} px-3 py-2 mt-2 rounded-pill">${risk.level}</span>
                        </div>
                        <div class="col-md-6 px-4">
                            <h5 class="fw-bold text-${risk.color} mb-3"><i class="bi bi-exclamation-octagon-fill"></i> ${risk.priority}</h5>
                            <div class="mb-3">
                                ${tagsHtml}
                            </div>
                            <div class="p-2 bg-white rounded border border-${risk.color}-subtle">
                                <small class="text-secondary fw-bold"><i class="bi bi-shield-check"></i> SYSTEM ADVICE:</small><br>
                                <span class="text-dark">${actionAdvice}</span>
                            </div>
                        </div>
                        <div class="col-md-3 text-secondary small">
                            <ul class="list-unstyled mb-0">
                                <li class="mb-2 d-flex justify-content-between">
                                    <span>Repeat Offense:</span> <strong>${risk.breakdown.repeat_offense_score}%</strong>
                                </li>
                                <li class="mb-2 d-flex justify-content-between">
                                    <span>Money Flow:</span> <strong>${risk.breakdown.money_flow_score}%</strong>
                                </li>
                                <li class="d-flex justify-content-between">
                                    <span>Network Link:</span> <strong>${risk.breakdown.network_score}%</strong>
                                </li>
                            </ul>
                        </div>
                    </div>
                </div>
            `;
            resDiv.appendChild(riskCard);
        }

        // Summary Statistics (Updated visualization)
        const stats = document.createElement('div');
        stats.className = 'row g-3 mb-4';
        stats.innerHTML = `
            <div class="col-md-2">
                <div class="card border-0 shadow-sm text-center p-3 h-100" style="background: #e3f2fd;">
                    <h3 class="fw-bold text-primary mb-0">${data.summary_stats.total_cases}</h3>
                    <small class="text-primary fw-bold">CASES MATCHED</small>
                </div>
            </div>
            <div class="col-md-2">
                <div class="card border-0 shadow-sm text-center p-3 h-100" style="background: #e0f7fa;">
                    <h3 class="fw-bold text-info mb-0">${data.summary_stats.total_evidence_files}</h3>
                    <small class="text-info fw-bold">EVIDENCE FILES</small>
                </div>
            </div>
            <div class="col-md-2">
                <div class="card border-0 shadow-sm text-center p-3 h-100" style="background: #fff3e0;">
                    <h3 class="fw-bold text-warning mb-0">${data.summary_stats.total_financial_entities}</h3>
                    <small class="text-warning fw-bold">FINANCIAL ACCTS</small>
                </div>
            </div>
            <div class="col-md-2">
                <div class="card border-0 shadow-sm text-center p-3 h-100" style="background: #ffebee;">
                    <h3 class="fw-bold text-danger mb-0">${data.summary_stats.total_telecom_requests}</h3>
                    <small class="text-danger fw-bold">REQ. SENT</small>
                </div>
            </div>
            <div class="col-md-2">
                <div class="card border-0 shadow-sm text-center p-3 h-100" style="background: #f3e5f5;">
                    <h3 class="fw-bold text-purple mb-0" style="color: #6a1b9a;">${data.summary_stats.total_timeline_events}</h3>
                    <small style="color: #6a1b9a;" class="fw-bold">TIMELINE EVENTS</small>
                </div>
            </div>
            <div class="col-md-2">
                <div class="card border-0 shadow-sm text-center p-3 h-100" style="background: #e8f5e9;">
                    <h5 class="fw-bold text-success mb-0">₹${(Number(data.summary_stats.total_transaction_amount || 0) / 1000).toFixed(1)}k</h5>
                    <small class="text-success fw-bold">FRAUD VALUE</small>
                </div>
            </div>
        `;
        stats.innerHTML = safeHTML(stats.innerHTML); // Sanitize the constructed string
        resDiv.appendChild(stats);

        // Cases Section
        if (data.cases.length > 0) {
            const casesCard = document.createElement('div');
            casesCard.className = 'card bg-white text-dark mb-3';
            casesCard.innerHTML = safeHTML(`
                <div class="card-header bg-primary text-white"><strong>📋 Cases (${data.cases.length})</strong></div>
                <div class="card-body">
                    <table class="table table-sm table-striped">
                        <thead><tr><th>FIR</th><th>Station</th><th>Type</th><th>Status</th><th>Created</th><th>Action</th></tr></thead>
                        <tbody id="casesTable"></tbody>
                    </table>
                </div>
            `);
            resDiv.appendChild(casesCard);

            const tbody = casesCard.querySelector('#casesTable');
            data.cases.forEach(c => {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td><strong>${escapeHtml(c.fir_number)}</strong></td>
                    <td>${escapeHtml(c.police_station)}</td>
                    <td><span class="badge bg-secondary">${escapeHtml(c.case_type)}</span></td>
                    <td><span class="badge bg-success">${escapeHtml(c.status)}</span></td>
                    <td>${new Date(c.created_at).toLocaleDateString()}</td>
                    <td><a href="case_detail.html?id=${c.id}" class="btn btn-sm btn-primary" target="_blank">View</a></td>
                `;
                tbody.appendChild(row);
            });
        }

        // Evidence Files Section (MOST IMPORTANT!)
        if (data.evidence_files.length > 0) {
            const evidenceCard = document.createElement('div');
            evidenceCard.className = 'card bg-white text-dark mb-3';
            evidenceCard.innerHTML = `
                <div class="card-header bg-info text-white"><strong>📁 Evidence Files - CAF/CDR/Documents (${data.evidence_files.length})</strong></div>
                <div class="card-body">
                    <table class="table table-sm table-striped">
                        <thead><tr><th>File Name</th><th>Type</th><th>FIR</th><th>Uploaded</th><th>Status</th><th>Action</th></tr></thead>
                        <tbody id="evidenceTable"></tbody>
                    </table>
                </div>
            `;
            resDiv.appendChild(evidenceCard);

            const tbody = evidenceCard.querySelector('#evidenceTable');
            data.evidence_files.forEach(e => {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td><i class="bi bi-file-earmark-pdf"></i> ${escapeHtml(e.original_filename)}</td>
                    <td><span class="badge bg-primary">${escapeHtml(e.file_type)}</span></td>
                    <td>${escapeHtml(e.fir_number)}</td>
                    <td>${new Date(e.uploaded_at).toLocaleDateString()}</td>
                    <td><span class="badge bg-success">${escapeHtml(e.verification_status)}</span></td>
                    <td><a href="/files/download/${e.id}" class="btn btn-sm btn-success" target="_blank"><i class="bi bi-download"></i> Download</a></td>
                `;
                tbody.appendChild(row);
            });
        }

        // Financial Entities Section
        if (data.financial_entities.length > 0) {
            const finCard = document.createElement('div');
            finCard.className = 'card bg-white text-dark mb-3';
            finCard.innerHTML = `
                <div class="card-header bg-warning text-dark"><strong>💰 Financial Entities (${data.financial_entities.length})</strong></div>
                <div class="card-body">
                    <table class="table table-sm table-striped">
                        <thead><tr><th>Type</th><th>Bank/UPI</th><th>Account/ID</th><th>Holder Name</th><th>Amount</th><th>FIR</th></tr></thead>
                        <tbody id="financialTable"></tbody>
                    </table>
                </div>
            `;
            resDiv.appendChild(finCard);

            const tbody = finCard.querySelector('#financialTable');
            data.financial_entities.forEach(f => {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td><span class="badge bg-info">${escapeHtml(f.entity_type)}</span></td>
                    <td>${escapeHtml(f.bank_name || f.upi_id || 'N/A')}</td>
                    <td>${escapeHtml(f.account_number || f.upi_id || 'N/A')}</td>
                    <td>${escapeHtml(f.account_holder_name || 'N/A')}</td>
                    <td>₹${(Number(f.transaction_amount) || 0).toFixed(2)}</td>
                    <td>${escapeHtml(f.fir_number)}</td>
                `;
                tbody.appendChild(row);
            });
        }

        // Telecom Requests Section
        if (data.telecom_requests.length > 0) {
            const telecomCard = document.createElement('div');
            telecomCard.className = 'card bg-white text-dark mb-3';
            telecomCard.innerHTML = `
                <div class="card-header bg-danger text-white"><strong>📞 Telecom Requests (${data.telecom_requests.length})</strong></div>
                <div class="card-body">
                    <table class="table table-sm table-striped">
                        <thead><tr><th>Mobile</th><th>Type</th><th>Status</th><th>FIR</th><th>Created</th></tr></thead>
                        <tbody id="telecomTable"></tbody>
                    </table>
                </div>
            `;
            resDiv.appendChild(telecomCard);

            const tbody = telecomCard.querySelector('#telecomTable');
            data.telecom_requests.forEach(t => {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td><strong>${escapeHtml(t.mobile_number)}</strong></td>
                    <td>${escapeHtml(t.request_type)}</td>
                    <td><span class="badge bg-warning">${escapeHtml(t.status)}</span></td>
                    <td>${escapeHtml(t.fir_number)}</td>
                    <td>${new Date(t.created_at).toLocaleDateString()}</td>
                `;
                tbody.appendChild(row);
            });
        }

        // Transaction Timeline Section
        if (data.transaction_timeline.length > 0) {
            const timelineCard = document.createElement('div');
            timelineCard.className = 'card bg-white text-dark mb-3';
            timelineCard.innerHTML = `<div class="card-header bg-secondary text-white"><strong>📅 Transaction Timeline (${data.transaction_timeline.length})</strong></div>
                <div class="card-body">
                    <table class="table table-sm table-striped">
                        <thead><tr><th>Date</th><th>Event</th><th>Narrative</th><th>Amount</th><th>FIR</th></tr></thead>
                        <tbody id="timelineTable"></tbody>
                    </table>
                </div>
            `;
            resDiv.appendChild(timelineCard);

            const tbody = timelineCard.querySelector('#timelineTable');
            data.transaction_timeline.forEach(t => {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td>${new Date(t.event_timestamp).toLocaleString()}</td>
                    <td><span class="badge bg-primary">${escapeHtml(t.event_type)}</span></td>
                    <td>${escapeHtml(t.narrative).substring(0, 100)}...</td>
                    <td>₹${(Number(t.amount) || 0).toFixed(2)}</td>
                    <td>${escapeHtml(t.fir_number)}</td>
                `;
                tbody.appendChild(row);
            });
        }

        // No Data Found
        if (data.summary_stats.total_cases === 0) {
            resDiv.innerHTML = '<div class="alert alert-info mt-3">No investigation data found for this identifier.</div>';
        }

    } catch (err) {
        resDiv.innerHTML = `<div class="alert alert-danger mt-3"><i class="bi bi-exclamation-triangle"></i> Error: ${escapeHtml(err.message)}</div>`;
    }
}

// VISUALIZE NETWORK GRAPH
async function visualizeNetwork(event) {
    event.preventDefault();
    const query = document.getElementById('searchQuery').value.trim();
    const graphSection = document.getElementById('networkGraphSection');
    const container = document.getElementById('networkMapCanvas');

    if (!query) {
        alert('Please enter an identifier first');
        return;
    }

    graphSection.classList.remove('d-none');
    container.innerHTML = '<div class="h-100 d-flex flex-column align-items-center justify-content-center text-muted"><div class="spinner-border mb-2"></div><div>Building Intelligence Graph...</div></div>';

    try {
        const response = await fetch(`http://localhost:8001/analysis/network-graph?identifier=${encodeURIComponent(query)}`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (!response.ok) throw new Error('Failed to fetch graph data');
        const data = await response.json();

        if (data.nodes.length === 0) {
            container.innerHTML = '<div class="h-100 d-flex align-items-center justify-content-center text-muted">No connections found for this identifier.</div>';
            return;
        }

        const visNodes = new vis.DataSet(data.nodes);
        const visEdges = new vis.DataSet(data.edges);

        const options = {
            nodes: {
                shape: 'dot',
                font: { size: 14, color: '#343a40', face: 'Inter' },
                borderWidth: 2,
                shadow: true
            },
            edges: {
                width: 2,
                color: { inherit: 'from' },
                smooth: { type: 'continuous' },
                arrows: { to: { enabled: true, scaleFactor: 0.5 } }
            },
            physics: {
                enabled: true,
                forceAtlas2Based: {
                    gravitationalConstant: -100, // Stronger repulsion
                    centralGravity: 0.005,
                    springLength: 200,
                    springConstant: 0.05
                },
                maxVelocity: 50,
                solver: 'forceAtlas2Based',
                stabilization: {
                    enabled: true,
                    iterations: 200,
                    updateInterval: 25
                }
            },
            groups: {
                case: { color: { background: '#4CAF50', border: '#388E3C' }, size: 30 },
                mobile: { color: { background: '#FF9800', border: '#F57C00' } },
                financial: { color: { background: '#f44336', border: '#d32f2f' } },
                search: { color: { background: '#6c757d', border: '#343a40' }, size: 25 }
            },
            interaction: {
                hover: true,
                tooltipDelay: 200,
                zoomView: true
            }
        };

        const network = new vis.Network(container, { nodes: visNodes, edges: visEdges }, options);

        // Add double-click interaction to open Case or Expand
        network.on("doubleClick", function (params) {
            if (params.nodes.length > 0) {
                const nodeId = params.nodes[0];
                if (nodeId.startsWith('CASE_')) {
                    const id = nodeId.split('_')[1];
                    window.open(`case_detail.html?id=${id}`, '_blank');
                }
            }
        });

        // Stabilize event
        network.on("stabilizationIterationsDone", function () {
            network.fit();
        });

    } catch (err) {
        container.innerHTML = `<div class="alert alert-danger m-3">Error: ${err.message}</div>`;
    }
}

// Expose to global scope
window.visualizeNetwork = visualizeNetwork;

// File Upload Search Handler
document.getElementById('fileSearchForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const fileInput = document.getElementById('searchFile');
    const resDiv = document.getElementById('searchResults');

    if (!fileInput.files || fileInput.files.length === 0) {
        resDiv.innerHTML = '<div class="alert alert-warning">Please select a file</div>';
        return;
    }

    const file = fileInput.files[0];
    const formData = new FormData();
    formData.append('file', file);

    resDiv.innerHTML = `
        <div class="text-center py-4">
            <div class="spinner-border text-light" role="status"></div>
            <p class="mt-3">Processing file: ${file.name}...</p>
            <small class="opacity-75">Extracting identifiers and searching databases...</small>
        </div>
    `;

    try {
        const response = await fetch('http://localhost:8001/analysis/file-search', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`
            },
            body: formData
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'File processing failed');
        }

        const data = await response.json();

        resDiv.innerHTML = '';

        // File Processing Summary
        const summaryCard = document.createElement('div');
        summaryCard.className = 'alert alert-success mt-3 mb-3';
        summaryCard.innerHTML = `
            <h6><i class="bi bi-file-check"></i> File Processed Successfully</h6>
            <div class="row g-2 mt-2">
                <div class="col-md-3">
                    <strong>Filename:</strong> ${data.filename}
                </div>
                <div class="col-md-3">
                    <strong>Total Identifiers:</strong> ${data.summary.total_identifiers}
                </div>
                <div class="col-md-3">
                    <strong>Matches Found:</strong> <span class="badge bg-danger">${data.summary.total_matches}</span>
                </div>
                <div class="col-md-3">
                    <strong>File Type:</strong> ${data.file_type.toUpperCase()}
                </div>
            </div>
        `;
        resDiv.appendChild(summaryCard);

        // Extracted Data Summary
        if (data.extracted_data) {
            const extractedCard = document.createElement('div');
            extractedCard.className = 'card bg-white text-dark mb-3';
            extractedCard.innerHTML = `
                <div class="card-body">
                    <h6 class="card-title"><i class="bi bi-list-check"></i> Extracted Identifiers</h6>
                    <div class="row g-2">
                        <div class="col-md-4">
                            <div class="p-2 bg-light rounded">
                                <strong>📱 Mobile Numbers:</strong> ${data.extracted_data.mobile_numbers.length}
                                ${data.extracted_data.mobile_numbers.length > 0 ? '<br><small class="text-muted">' + data.extracted_data.mobile_numbers.slice(0, 3).join(', ') + (data.extracted_data.mobile_numbers.length > 3 ? '...' : '') + '</small>' : ''}
                            </div>
                        </div>
                        <div class="col-md-4">
                            <div class="p-2 bg-light rounded">
                                <strong>💸 UPI IDs:</strong> ${data.extracted_data.upi_ids.length}
                                ${data.extracted_data.upi_ids.length > 0 ? '<br><small class="text-muted">' + data.extracted_data.upi_ids.slice(0, 3).join(', ') + (data.extracted_data.upi_ids.length > 3 ? '...' : '') + '</small>' : ''}
                            </div>
                        </div>
                        <div class="col-md-4">
                            <div class="p-2 bg-light rounded">
                                <strong>🏦 Accounts:</strong> ${data.extracted_data.account_numbers.length}
                                ${data.extracted_data.account_numbers.length > 0 ? '<br><small class="text-muted">' + data.extracted_data.account_numbers.slice(0, 3).join(', ') + (data.extracted_data.account_numbers.length > 3 ? '...' : '') + '</small>' : ''}
                            </div>
                        </div>
                    </div>
                </div>
            `;
            resDiv.appendChild(extractedCard);
        }

        // Intelligence Matches
        if (data.count === 0) {
            resDiv.innerHTML += `
                <div class="alert alert-info">
                    <i class="bi bi-info-circle"></i> No intelligence matches found for extracted identifiers.
                    <p class="mb-0 mt-2 small">This indicates none of the identifiers from the file match any records in the database.</p>
                </div>
            `;
        } else {
            // Matches Header
            const matchesHeader = document.createElement('div');
            matchesHeader.className = 'alert alert-warning mt-3 mb-3';
            matchesHeader.innerHTML = `
                <h6><i class="bi bi-exclamation-triangle-fill"></i> Intelligence Alerts - Matches Found!</h6>
                <p class="mb-0">${data.count} identifier(s) from the uploaded file match existing case records.</p>
            `;
            resDiv.appendChild(matchesHeader);

            // Group results by searched identifier
            const grouped = {};
            data.matches.forEach(match => {
                const identifier = match.searched_identifier || 'Unknown';
                if (!grouped[identifier]) {
                    grouped[identifier] = [];
                }
                grouped[identifier].push(match);
            });

            // Display grouped results
            for (const [identifier, matches] of Object.entries(grouped)) {
                const groupCard = document.createElement('div');
                groupCard.className = 'card bg-white text-dark mb-3';
                groupCard.innerHTML = `
                    <div class="card-header bg-danger text-white">
                        <strong>⚠️ Alert:</strong> Identifier "${identifier}" found in ${matches.length} case(s)
                    </div>
                    <div class="card-body">
                        <table class="table table-sm table-striped">
                            <thead>
                                <tr>
                                    <th>FIR Number</th>
                                    <th>Source</th>
                                    <th>Match Type</th>
                                    <th>Case Type</th>
                                    <th>Status</th>
                                    <th>Action</th>
                                </tr>
                            </thead>
                            <tbody id="matches-${identifier.replace(/[^a-zA-Z0-9]/g, '_')}"></tbody>
                        </table>
                    </div>
                `;
                resDiv.appendChild(groupCard);

                const tbody = groupCard.querySelector('tbody');
                matches.forEach(match => {
                    const row = document.createElement('tr');
                    const statusBadge = match.status === 'active' ? 'success' : 'secondary';

                    row.innerHTML = `
                        <td><strong>${match.fir_number || 'N/A'}</strong></td>
                        <td><span class="badge bg-info">${match.source}</span></td>
                        <td>${match.match_type}</td>
                        <td>${formatCaseType(match.case_type || 'N/A')}</td>
                        <td><span class="badge bg-${statusBadge}">${match.status || 'N/A'}</span></td>
                        <td><a href="case_detail.html?id=${match.case_id}" class="btn btn-sm btn-primary" target="_blank">View</a></td>
                    `;
                    tbody.appendChild(row);
                });
            }
        }

        // Reset file input
        fileInput.value = '';

    } catch (err) {
        resDiv.innerHTML = `
            <div class="alert alert-danger mt-3">
                <i class="bi bi-exclamation-triangle"></i> <strong>Error:</strong> ${escapeHtml(err.message)}
                <p class="mb-0 mt-2 small">Please check the file format and try again. Supported formats: Excel (.xlsx, .xls), CSV (.csv), PDF (.pdf)</p>
            </div>
        `;
    }
});

function showAlert(type, msg) {
    const ph = document.getElementById('alertPlaceholder');
    ph.innerHTML = `
        <div class="alert alert-${type} alert-dismissible fade show" role="alert">
            ${msg}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;
}

// ========== FINANCIAL FRAUD MODULE: Dashboard Logic ==========

async function loadFinancialDashboard() {
    const amountAtRiskElem = document.getElementById('amountAtRisk');
    if (!amountAtRiskElem) return; // Not on the right page

    try {
        // Fetch financial fraud dashboard metrics
        const response = await fetch('http://localhost:8001/analytics/financial-dashboard', {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (!response.ok) throw new Error('Failed to load financial dashboard');

        const data = await response.json();

        // Check for new alerts (live notification)
        if (typeof checkForNewAlerts === 'function') {
            checkForNewAlerts(data);
        }

        // Update metrics
        amountAtRiskElem.textContent = data.amount_at_risk || '₹0';
        if (document.getElementById('bankRequestsSent')) document.getElementById('bankRequestsSent').textContent = data.bank_requests_sent || 0;
        if (document.getElementById('freezeConfirmed')) document.getElementById('freezeConfirmed').textContent = data.freeze_requests?.confirmed || 0;
        if (document.getElementById('freezeTotal')) document.getElementById('freezeTotal').textContent = data.freeze_requests?.total || 0;
        if (document.getElementById('avgResponseTime')) document.getElementById('avgResponseTime').textContent = data.avg_bank_response_time || '-';

        // Render fraud type breakdown
        const fraudBreakdown = document.getElementById('fraudTypeBreakdown');
        if (fraudBreakdown) {
            if (data.top_fraud_types && Object.keys(data.top_fraud_types).length > 0) {
                fraudBreakdown.innerHTML = '<ul class="list-unstyled">';
                for (const [type, count] of Object.entries(data.top_fraud_types)) {
                    fraudBreakdown.innerHTML += `
                        <li class="mb-2">
                            <span class="badge bg-primary">${count}</span>
                            <strong class="ms-2">${formatFraudType(type)}</strong>
                        </li>
                    `;
                }
                fraudBreakdown.innerHTML += '</ul>';
            } else {
                fraudBreakdown.innerHTML = '<p class="text-muted">No fraud data available</p>';
            }
        }

        // Load repeat entities
        await loadRepeatEntities();

    } catch (err) {
        console.error('Dashboard load error:', err);
        if (amountAtRiskElem) amountAtRiskElem.textContent = 'Error';
    }
}

async function loadRepeatEntities() {
    try {
        const response = await fetch('http://localhost:8001/analytics/repeat-entities', {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (!response.ok) throw new Error('Failed to load repeat entities');

        const data = await response.json();

        // Check for new alerts (live notification)
        if (typeof checkForNewAlerts === 'function') {
            checkForNewAlerts(data);
        }

        const alertsDiv = document.getElementById('repeatEntitiesAlert');

        if (data.total_repeat_entities === 0) {
            alertsDiv.innerHTML = '<p class="text-muted">No repeat fraud entities detected</p>';
        } else {
            alertsDiv.innerHTML = `
                <div class="alert alert-warning">
                    <strong>⚠️ ${data.total_repeat_entities} Repeat Entity(ies) Detected</strong>
                </div>
            `;

            data.alerts.forEach(alert => {
                const alertBadge = alert.alert_level === 'HIGH' ? 'danger' : 'warning';
                alertsDiv.innerHTML += `
                    <div class="card-custom p-3 mb-2">
                        <div class="d-flex justify-content-between align-items-start">
                            <div>
                                <span class="badge bg-${alertBadge}">${alert.alert_level}</span>
                                <strong class="ms-2">${alert.type}</strong>: ${alert.identifier}
                            </div>
                            <span class="badge bg-secondary">${alert.linked_cases_count} cases</span>
                        </div>
                        <small class="text-muted d-block mt-2">Linked FIRs: ${alert.fir_numbers.join(', ')}</small>
                    </div>
                `;
            });
        }

    } catch (err) {
        console.error('Repeat entities error:', err);
        document.getElementById('repeatEntitiesAlert').innerHTML = '<p class="text-danger">Error loading alerts</p>';
    }
}

function formatFraudType(type) {
    const formatted = type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    return formatted;
}

// Load financial dashboard on page load
loadFinancialDashboard();

init();

// Start auto-refresh if enabled
setTimeout(() => {
    if (typeof startAutoRefresh === 'function') {
        startAutoRefresh();
    }
}, 1000);
