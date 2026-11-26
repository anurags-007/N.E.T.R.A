const token = localStorage.getItem('token');

if (!token) {
    window.location.href = 'index.html';
}

document.getElementById('logoutBtn').addEventListener('click', async () => {
    await API.logout(token);
    localStorage.removeItem('token');
    window.location.href = 'index.html';
});

document.getElementById('verifyChainBtn')?.addEventListener('click', async () => {
    const banner = document.getElementById('chainVerifyAlert');
    if (!banner) return;
    banner.className = 'mb-3';
    banner.innerHTML = '';

    try {
        const res = await API.verifyAuditChain(token);
        const alertDiv = document.createElement('div');
        if (res.valid) {
            alertDiv.className = 'alert alert-success d-flex align-items-center mb-0 shadow-sm';
            alertDiv.setAttribute('role', 'alert');
            const icon = document.createElement('i');
            icon.className = 'bi bi-shield-fill-check fs-5 me-2';
            const text = document.createElement('span');
            text.textContent = `Audit Log Hash Chain VALID: ${res.checked_entries} consecutive SHA-256 entries verified cleanly.`;
            alertDiv.append(icon, text);
        } else {
            alertDiv.className = 'alert alert-danger d-flex align-items-center mb-0 shadow-sm';
            alertDiv.setAttribute('role', 'alert');
            const icon = document.createElement('i');
            icon.className = 'bi bi-exclamation-octagon-fill fs-5 me-2';
            const text = document.createElement('span');
            text.textContent = `TAMPER DETECTED at AuditLog #${res.broken_id ?? 'unknown'}: ${res.reason || 'Hash mismatch'}`;
            alertDiv.append(icon, text);
        }
        banner.appendChild(alertDiv);
    } catch (err) {
        const alertDiv = document.createElement('div');
        alertDiv.className = 'alert alert-danger mb-0';
        alertDiv.textContent = `Verification failed: ${err.message}`;
        banner.appendChild(alertDiv);
    }
});

async function init() {
    try {
        const user = await API.getMe(token);
        document.getElementById('userNameDisplay').textContent = user.username;
        const roleDisplay = document.getElementById('userRoleDisplay');
        if (roleDisplay) {
            roleDisplay.textContent = (user.rank || user.role).toUpperCase();
        }

        loadLogs();
    } catch (err) {
        console.error(err);
        localStorage.removeItem('token');
        window.location.href = 'index.html';
    }
}

async function loadLogs() {
    const tbody = document.getElementById('logsTableBody');
    tbody.innerHTML = '<tr><td colspan="4" class="text-center py-4">Loading logs...</td></tr>';

    try {
        const logs = await API.getAuditLogs(token);
        tbody.innerHTML = '';

        if (logs.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted py-4">No audit records found.</td></tr>';
            return;
        }

        logs.forEach(log => {
            const tr = document.createElement('tr');

            // Highlight critical actions
            let actionColor = 'text-dark';
            if (log.action === 'LOGIN') actionColor = 'text-success fw-bold';
            if (log.action === 'UPLOAD_EVIDENCE') actionColor = 'text-primary fw-bold';
            if (log.action.includes('REJECT')) actionColor = 'text-danger fw-bold';

            tr.innerHTML = `
                <td class="ps-4 text-muted small">${new Date(log.timestamp).toLocaleString()}</td>
                <td class="fw-bold log-user"></td>
                <td class="${actionColor} log-action"></td>
                <td class="log-details"></td>
            `;
            tr.querySelector('.log-user').textContent = log.user;
            tr.querySelector('.log-action').textContent = log.action;
            tr.querySelector('.log-details').textContent = log.details || '-';
            tbody.appendChild(tr);
        });

    } catch (err) {
        tbody.innerHTML = '';
        const tr = document.createElement('tr');
        const td = document.createElement('td');
        td.colSpan = 4;
        td.className = 'text-center text-danger py-4';
        td.textContent = `Error loading logs: ${err.message}`;
        tr.appendChild(td);
        tbody.appendChild(tr);
    }
}

// Register Officer
document.getElementById('registerOfficerForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const formData = new FormData(e.target);
    const data = Object.fromEntries(formData.entries());

    try {
        await API.register(data.username, data.email, data.password, data.role, token, {
            station_name: data.station_name?.trim() || null,
            sub_division: data.sub_division?.trim() || null,
            district_name: data.district_name?.trim() || null,
            range_name: data.range_name?.trim() || null,
            zone_name: data.zone_name?.trim() || null,
        });
        showAlert('success', 'Officer instance generated successfully');
        e.target.reset();
        loadLogs();
    } catch (err) {
        showAlert('danger', 'Generation Failed: ' + err.message);
    }
});

function showAlert(type, msg) {
    const ph = document.getElementById('alertPlaceholder');
    ph.innerHTML = `
        <div class="alert alert-${escapeHtml(type)} alert-dismissible fade show shadow-sm" role="alert">
            <i class="bi bi-info-circle-fill me-2"></i> <span class="alert-msg"></span>
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;
    ph.querySelector('.alert-msg').textContent = msg;
    setTimeout(() => {
        ph.innerHTML = '';
    }, 5000);
}

init();
