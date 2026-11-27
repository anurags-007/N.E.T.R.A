// ========== N.E.T.R.A. SECURITY MODULE ==========
// Provides centralized HTML sanitization to prevent XSS.
// Depends on DOMPurify.

/**
 * Sanitizes HTML content using DOMPurify.
 * Falls back to basic text escaping if DOMPurify is not loaded.
 * @param {string} html - The HTML string to sanitize.
 * @returns {string} - The sanitized HTML.
 */
function safeHTML(html) {
    if (window.DOMPurify) {
        return DOMPurify.sanitize(html);
    }
    console.warn('DOMPurify not loaded. Falling back to text escaping.');
    return escapeHtml(html);
}

/**
 * Escapes special characters to prevent HTML injection.
 * Legacy alias and fallback.
 * @param {string} text - The text to escape.
 * @returns {string} - The escaped text safe for innerHTML.
 */
function escapeHtml(text) {
    if (typeof text !== 'string') return text;
    return text
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// Role-based sidebar navigation gating (cookie-authenticated, zero localStorage token)
function setRoleBasedNav(roleStr) {
    const role = (roleStr || '').toLowerCase();
    const allowedAdminNav = ['admin', 'sho', 'sp', 'dgp'];
    if (role && !allowedAdminNav.includes(role)) {
        document.querySelectorAll('a[href="admin.html"]').forEach((el) => {
            el.classList.add('d-none');
        });
    }
}

async function applyRoleBasedNav() {
    if (window.location.pathname.endsWith('index.html') || window.location.pathname.endsWith('/')) return;
    try {
        const base = (typeof API_URL !== 'undefined')
            ? API_URL
            : ((window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
                ? `${window.location.protocol}//${window.location.hostname}:8001`
                : window.location.origin);
        const resp = await fetch(`${base}/auth/me`, { credentials: 'include' });
        if (!resp.ok) return;
        const user = await resp.json();
        setRoleBasedNav(user.role);
    } catch (_err) {
        // Ignore network errors; page auth checks handle redirect
    }
}

document.addEventListener('DOMContentLoaded', applyRoleBasedNav);
window.setRoleBasedNav = setRoleBasedNav;

// Non-blocking Bootstrap toast notification helper (DOM-safe)
function showToast(msg, type = 'info') {
    const allowed = ['primary', 'secondary', 'success', 'danger', 'warning', 'info', 'dark'];
    const safeType = allowed.includes(type) ? type : 'info';

    let container = document.getElementById('netraToastContainer');
    if (!container) {
        container = document.createElement('div');
        container.id = 'netraToastContainer';
        container.className = 'toast-container position-fixed top-0 end-0 p-3';
        container.style.zIndex = '1090';
        document.body.appendChild(container);
    }

    const toastEl = document.createElement('div');
    toastEl.className = `toast align-items-center text-bg-${safeType} border-0 shadow`;
    toastEl.setAttribute('role', 'alert');
    toastEl.setAttribute('aria-live', 'assertive');
    toastEl.setAttribute('aria-atomic', 'true');

    const flex = document.createElement('div');
    flex.className = 'd-flex';

    const body = document.createElement('div');
    body.className = 'toast-body fw-medium';
    body.textContent = String(msg ?? '');

    const closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.className = 'btn-close btn-close-white me-2 m-auto';
    closeBtn.setAttribute('data-bs-dismiss', 'toast');
    closeBtn.setAttribute('aria-label', 'Close');

    flex.append(body, closeBtn);
    toastEl.appendChild(flex);
    container.appendChild(toastEl);

    if (window.bootstrap && window.bootstrap.Toast) {
        const bsToast = new window.bootstrap.Toast(toastEl, { delay: 4000 });
        toastEl.addEventListener('hidden.bs.toast', () => toastEl.remove(), { once: true });
        bsToast.show();
    } else {
        toastEl.classList.add('show');
        setTimeout(() => toastEl.remove(), 4000);
    }
}

// Expose globally
window.safeHTML = safeHTML;
window.escapeHtml = escapeHtml;
window.applyRoleBasedNav = applyRoleBasedNav;
window.showToast = showToast;
