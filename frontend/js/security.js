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

// Role-based sidebar navigation gating
function applyRoleBasedNav() {
    try {
        const token = localStorage.getItem('token');
        if (!token) return;
        const parts = token.split('.');
        if (parts.length !== 3) return;
        const payload = JSON.parse(atob(parts[1]));
        const role = (payload.role || '').toLowerCase();
        const allowedAdminNav = ['admin', 'sho', 'sp', 'dgp'];
        if (!allowedAdminNav.includes(role)) {
            document.querySelectorAll('a[href="admin.html"]').forEach((el) => {
                el.classList.add('d-none');
            });
        }
    } catch (_err) {
        // Ignore malformed token; page auth checks handle redirect
    }
}

document.addEventListener('DOMContentLoaded', applyRoleBasedNav);

// Expose globally
window.safeHTML = safeHTML;
window.escapeHtml = escapeHtml;
window.applyRoleBasedNav = applyRoleBasedNav;
