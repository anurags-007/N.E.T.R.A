// Login page handler (HttpOnly cookie auth, strict CSP - no inline scripts)
document.getElementById('loginForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;

    try {
        const data = await API.login(username, password);
        if (data.is_first_login) {
            const modal = new bootstrap.Modal(document.getElementById('passwordChangeModal'));
            modal.show();
        } else {
            completeAuth(e.target);
        }
    } catch (err) {
        showAlert('danger', 'Authentication Failed: ' + err.message);
    }
});

document.getElementById('passwordChangeForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const oldPass = document.getElementById('oldPassword').value;
    const newPass = document.getElementById('newPassword').value;
    const confirmPass = document.getElementById('confirmPassword').value;

    if (newPass !== confirmPass) {
        showAlert('danger', 'Passwords do not match!');
        return;
    }

    try {
        await API.changePassword(null, oldPass, newPass);
        bootstrap.Modal.getInstance(document.getElementById('passwordChangeModal'))?.hide();
        showAlert('success', 'Security updated. Redirecting...');
        setTimeout(() => {
            window.location.href = 'dashboard.html';
        }, 1000);
    } catch (err) {
        showAlert('danger', 'Update Failed: ' + err.message);
    }
});

function completeAuth(form) {
    const btn = form.querySelector('button[type="submit"]');
    if (btn) {
        btn.innerHTML = '<i class="bi bi-shield-check"></i> AUTHENTICATED';
        btn.style.backgroundColor = 'var(--success-color)';
        btn.style.borderColor = 'var(--success-color)';
    }
    setTimeout(() => {
        window.location.href = 'dashboard.html';
    }, 600);
}

function showAlert(type, msg) {
    const ph = document.getElementById('alertPlaceholder');
    if (!ph) return;
    ph.innerHTML = '';
    const div = document.createElement('div');
    const safeType = ['danger', 'success', 'warning', 'info'].includes(type) ? type : 'info';
    div.className = `alert alert-${safeType} alert-dismissible fade show d-flex align-items-center mb-4`;
    div.setAttribute('role', 'alert');
    const icon = document.createElement('i');
    icon.className = `bi ${safeType === 'danger' ? 'bi-exclamation-octagon' : 'bi-check-circle'} me-2`;
    const span = document.createElement('div');
    span.textContent = String(msg ?? '');
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'btn-close';
    btn.setAttribute('data-bs-dismiss', 'alert');
    div.append(icon, span, btn);
    ph.appendChild(div);
}
