const token = localStorage.getItem('token');

if (!token) {
    window.location.href = 'index.html';
}

document.getElementById('logoutBtn').addEventListener('click', () => {
    localStorage.removeItem('token');
    window.location.href = 'index.html';
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
        tbody.innerHTML = `<tr><td colspan="4" class="text-center text-danger py-4">Error loading logs: ${err.message}</td></tr>`;
    }
}

// Register Officer
document.getElementById('registerOfficerForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const formData = new FormData(e.target);
    const data = Object.fromEntries(formData.entries());

    try {
        await API.register(data.username, data.email, data.password, data.role, token);
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
        <div class="alert alert-${type} alert-dismissible fade show shadow-sm" role="alert">
            <i class="bi bi-info-circle-fill me-2"></i> ${msg}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;
    setTimeout(() => {
        ph.innerHTML = '';
    }, 5000);
}

init();
