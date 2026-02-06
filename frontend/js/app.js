const token = localStorage.getItem('token');

if (!token) {
    window.location.href = 'index.html';
}

// Logout
document.getElementById('logoutBtn').addEventListener('click', () => {
    localStorage.removeItem('token');
    window.location.href = 'index.html';
});

// ========== SECURITY: HTML SANITIZATION ==========
// ========== SECURITY: HTML SANITIZATION ==========
// Functions handled by security.js (loaded in HTML)

function setTextContent(elementId, text) {
    const element = document.getElementById(elementId);
    if (element) {
        element.textContent = text;
    }
}

// Disable console logging in production
if (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
    console.log = function () { };
    console.error = function () { };
    console.warn = function () { };
}

// Load Data
async function init() {
    try {
        const payload = JSON.parse(atob(token.split('.')[1]));
        const user = {
            username: payload.sub,
            role: payload.role,
            rank: payload.rank || payload.role,
            station: payload.station,
            district: payload.district,
            zone: payload.zone
        };

        // Display Scope info
        let scopeText = "";
        if (user.role === 'constable' || user.role === 'si' || user.role === 'sho') {
            scopeText = user.station ? `Station: ${user.station}` : "";
        } else if (user.role === 'sp' || user.role === 'dy_sp') {
            scopeText = user.district ? `District: ${user.district}` : "";
        } else if (user.role === 'dgp') {
            scopeText = "State: Uttar Pradesh";
        }

        // FIX: Use textContent to prevent XSS
        const userDisplay = document.getElementById('userNameDisplay');
        if (userDisplay) {
            // Clear existing content
            userDisplay.innerHTML = '';

            // Set Role/Rank
            const roleDisplay = document.getElementById('userRoleDisplay');
            if (roleDisplay) {
                roleDisplay.textContent = (user.rank || user.role).toUpperCase();
            }

            // Set Username
            userDisplay.textContent = user.username;

            // Add line break (optional, but block elements handle layout)
            // userDisplay.appendChild(document.createElement('br'));

            // Add scope text
            const scopeSpan = document.createElement('span');
            scopeSpan.className = 'small text-white-50';
            scopeSpan.textContent = scopeText;
            userDisplay.appendChild(scopeSpan);
        }

        // Hide "New Case" if not SI/Officer (and not SHO/Constable who cannot create)
        // Allowed creators: SI and Legacy Officer
        if (!['si', 'officer', 'sub_inspector'].includes(user.role.toLowerCase())) {
            const btn = document.querySelector('[data-bs-target="#newCaseModal"]');
            if (btn) {
                btn.classList.remove('d-flex');
                btn.classList.add('d-none');
            }
        }

        loadCases();

    } catch (err) {
        if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
            console.error(err);
        }
        localStorage.removeItem('token');
        window.location.href = 'index.html';
    }
}

// ========== FINANCIAL FRAUD MODULE: CASCADING DROPDOWNS ==========

// Case Type Classification Data
const CASE_TYPES = {
    financial: [
        { value: 'upi_fraud', label: 'UPI Fraud' },
        { value: 'bank_transfer_fraud', label: 'Bank Transfer Fraud' },
        { value: 'wallet_fraud', label: 'Wallet Fraud (Paytm/PhonePe)' },
        { value: 'loan_app_scam', label: 'Loan App Scam' },
        { value: 'investment_fraud', label: 'Investment/Crypto Fraud' },
        { value: 'fraud', label: 'General Financial Fraud (Legacy)' }
    ],
    non_financial: [
        { value: 'harassment', label: 'Online Harassment' },
        { value: 'sextortion', label: 'Sextortion/Blackmail' },
        { value: 'fake_profile', label: 'Fake Social Media Profile' },
        { value: 'email_hack', label: 'Email/Account Hacking' },
        { value: 'impersonation', label: 'Identity Impersonation' },
        { value: 'phishing', label: 'Phishing/Cyber Attack' },
        { value: 'other', label: 'Other Cyber Crime' }
    ]
};

// Handle Case Category Change
const caseCategorySelect = document.getElementById('caseCategory');
const caseTypeSelect = document.getElementById('caseType');
const financialEntitySection = document.getElementById('financialEntitySection');

if (caseCategorySelect) {
    caseCategorySelect.addEventListener('change', (e) => {
        const category = e.target.value;

        // Reset and populate case type dropdown
        caseTypeSelect.innerHTML = '<option value="">-- Select Type --</option>';

        if (category && CASE_TYPES[category]) {
            CASE_TYPES[category].forEach(type => {
                const option = document.createElement('option');
                option.value = type.value;
                option.textContent = type.label;
                caseTypeSelect.appendChild(option);
            });
            caseTypeSelect.disabled = false;
        } else {
            caseTypeSelect.disabled = true;
        }

        // Show/Hide Financial Entity Section
        if (category === 'financial') {
            financialEntitySection.classList.remove('d-none');
        } else {
            financialEntitySection.classList.add('d-none');
        }
    });
}

// Handle Entity Type Change (Bank Account vs UPI vs Wallet)
const entityTypeSelect = document.getElementById('entityType');
if (entityTypeSelect) {
    entityTypeSelect.addEventListener('change', (e) => {
        const entityType = e.target.value;

        // Hide all conditional fields first
        document.getElementById('bankAccountFields').classList.add('d-none');
        document.getElementById('upiIdField').classList.add('d-none');
        document.getElementById('walletField').classList.add('d-none');

        // Show relevant fields
        if (entityType === 'bank_account') {
            document.getElementById('bankAccountFields').classList.remove('d-none');
        } else if (entityType === 'upi_id') {
            document.getElementById('upiIdField').classList.remove('d-none');
        } else if (entityType === 'wallet') {
            document.getElementById('walletField').classList.remove('d-none');
        }
    });
}

async function loadCases() {
    try {
        const cases = await API.getCases(token);

        // Update Stats
        const countDisplay = document.getElementById('totalCasesCount');
        if (countDisplay) countDisplay.innerText = cases.length;

        // Render Table
        renderTable(cases);

        // Search Filter
        const searchInput = document.getElementById('searchCaseInput');
        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                const term = e.target.value.toLowerCase();
                const filtered = cases.filter(c =>
                    c.fir_number.toLowerCase().includes(term) ||
                    c.police_station.toLowerCase().includes(term) ||
                    c.case_type.toLowerCase().includes(term)
                );
                renderTable(filtered);
            });
        }

    } catch (err) {
        showAlert('danger', 'Failed to load cases');
    }
}

function renderTable(data) {
    const tbody = document.getElementById('casesTableBody');
    tbody.innerHTML = '';

    if (data.length === 0) {
        const emptyRow = document.createElement('tr');
        const emptyCell = document.createElement('td');
        emptyCell.setAttribute('colspan', '6');
        emptyCell.className = 'text-center text-muted py-4';
        emptyCell.textContent = 'No cases found. Register a new case to begin.';
        emptyRow.appendChild(emptyCell);
        tbody.appendChild(emptyRow);
        return;
    }

    data.forEach(c => {
        const tr = document.createElement('tr');

        // Status Colors
        let statusClass = 'secondary';
        if (c.status === 'active') statusClass = 'success';
        if (c.status === 'pending') statusClass = 'warning';

        // FIX: Build table cells safely without innerHTML for user data
        // Column 1: FIR Number
        const firCell = document.createElement('td');
        firCell.className = 'ps-4 fw-bold text-primary';
        firCell.textContent = '#' + c.fir_number;
        tr.appendChild(firCell);

        // Column 2: Police Station
        const stationCell = document.createElement('td');
        stationCell.textContent = c.police_station;
        tr.appendChild(stationCell);

        // Column 3: Case Type
        const typeCell = document.createElement('td');
        const typeBadge = document.createElement('span');
        typeBadge.className = 'badge bg-light text-dark border';
        typeBadge.textContent = c.case_type.toUpperCase();
        typeCell.appendChild(typeBadge);
        tr.appendChild(typeCell);

        // Column 4: Status
        const statusCell = document.createElement('td');
        const statusBadge = document.createElement('span');
        statusBadge.className = `badge bg-${statusClass}`;
        statusBadge.textContent = c.status.toUpperCase();
        statusCell.appendChild(statusBadge);
        tr.appendChild(statusCell);

        // Column 5: Created Date
        const dateCell = document.createElement('td');
        dateCell.textContent = new Date(c.created_at).toLocaleDateString();
        tr.appendChild(dateCell);

        // Column 6: Actions
        const actionCell = document.createElement('td');
        actionCell.className = 'text-end pe-4';
        const viewBtn = document.createElement('button');
        viewBtn.className = 'btn btn-sm btn-outline-primary';
        viewBtn.onclick = () => viewCase(c.id);
        const icon = document.createElement('i');
        icon.className = 'bi bi-eye';
        viewBtn.appendChild(icon);
        viewBtn.appendChild(document.createTextNode(' View'));
        actionCell.appendChild(viewBtn);
        tr.appendChild(actionCell);

        tbody.appendChild(tr);
    });
}

// New Case
document.getElementById('newCaseForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = e.target.querySelector('button[type="submit"]');
    const originalText = btn.innerHTML;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Processing...';
    btn.disabled = true;

    try {
        const formData = new FormData(e.target);
        const data = Object.fromEntries(formData.entries());

        // 1. Create the Case
        const caseRes = await API.createCase(token, {
            fir_number: data.fir_number,
            police_station: data.police_station,
            case_category: data.case_category,
            case_type: data.case_type,
            description: data.description,
            amount_involved: data.transaction_amount || "0"
        });

        // 2. If Financial, Create Financial Entity
        if (data.case_category === 'financial' && data.entity_type) {
            const entityData = {
                entity_type: data.entity_type,
                bank_name: data.bank_name || null,
                account_number: data.account_number || null,
                ifsc_code: data.ifsc_code || null,
                account_holder_name: data.account_holder_name || null,
                upi_id: data.upi_id || null,
                wallet_provider: data.wallet_provider || null,
                transaction_id: data.transaction_id || null,
                transaction_amount: data.transaction_amount || null
            };

            await API.createFinancialEntity(token, caseRes.id, entityData);
            console.log("Financial Entity Linked");
        }

        const modal = bootstrap.Modal.getInstance(document.getElementById('newCaseModal'));
        modal.hide();
        e.target.reset();
        showAlert('success', 'Case & Financial Data recorded successfully');
        loadCases();
    } catch (err) {
        showAlert('danger', err.message);
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
});

function showAlert(type, msg) {
    const ph = document.getElementById('alertPlaceholder');

    // FIX: Create alert safely without innerHTML
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
    alertDiv.setAttribute('role', 'alert');

    const icon = document.createElement('i');
    icon.className = 'bi bi-info-circle-fill me-2';
    alertDiv.appendChild(icon);

    // Use textContent for message to prevent XSS
    alertDiv.appendChild(document.createTextNode(' ' + msg));

    const closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.className = 'btn-close';
    closeBtn.setAttribute('data-bs-dismiss', 'alert');
    alertDiv.appendChild(closeBtn);

    ph.innerHTML = ''; // Clear existing
    ph.appendChild(alertDiv);

    setTimeout(() => {
        ph.innerHTML = '';
    }, 5000);
}

function viewCase(id) {
    window.location.href = `case_detail.html?id=${id}`;
}

init();
