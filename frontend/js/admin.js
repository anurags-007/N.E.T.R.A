document.getElementById('logoutBtn')?.addEventListener('click', async () => {
    await API.logout();
    window.location.href = 'index.html';
});

document.getElementById('refreshLogsBtn')?.addEventListener('click', () => loadLogs());

document.getElementById('verifyChainBtn')?.addEventListener('click', async () => {
    const banner = document.getElementById('chainVerifyAlert');
    if (!banner) return;
    banner.className = 'mb-3';
    banner.innerHTML = '';

    try {
        const res = await API.verifyAuditChain();
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
        const user = await API.getMe();
        document.getElementById('userNameDisplay').textContent = user.username;
        const roleDisplay = document.getElementById('userRoleDisplay');
        if (roleDisplay) {
            roleDisplay.textContent = (user.rank || user.role).toUpperCase();
        }
        if (typeof setRoleBasedNav === 'function') setRoleBasedNav(user.role);

        loadLogs();
    } catch (err) {
        console.error(err);
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

            let actionColor = 'text-dark';
            if (log.action === 'LOGIN') actionColor = 'text-success fw-bold';
            if (log.action === 'UPLOAD_EVIDENCE') actionColor = 'text-primary fw-bold';
            if (log.action.includes('REJECT')) actionColor = 'text-danger fw-bold';

            const tdTime = document.createElement('td');
            tdTime.className = 'ps-4 text-muted small';
            tdTime.textContent = new Date(log.timestamp).toLocaleString();

            const tdUser = document.createElement('td');
            tdUser.className = 'fw-bold log-user';
            tdUser.textContent = log.user;

            const tdAction = document.createElement('td');
            tdAction.className = `${actionColor} log-action`;
            tdAction.textContent = log.action;

            const tdDetails = document.createElement('td');
            tdDetails.className = 'log-details';
            tdDetails.textContent = log.details || '-';

            tr.append(tdTime, tdUser, tdAction, tdDetails);
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
    ph.replaceChildren();
    const allowedTypes = new Set(['success', 'danger', 'warning', 'info']);
    const safeType = allowedTypes.has(type) ? type : 'info';

    const wrapper = document.createElement('div');
    wrapper.className = `alert alert-${safeType} alert-dismissible fade show shadow-sm`;
    wrapper.setAttribute('role', 'alert');

    const icon = document.createElement('i');
    icon.className = 'bi bi-info-circle-fill me-2';

    const span = document.createElement('span');
    span.className = 'alert-msg';
    span.textContent = msg;

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'btn-close';
    btn.setAttribute('data-bs-dismiss', 'alert');

    wrapper.append(icon, span, btn);
    ph.appendChild(wrapper);
    setTimeout(() => {
        ph.replaceChildren();
    }, 5000);
}

init();
