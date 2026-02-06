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

// Expose globally
window.safeHTML = safeHTML;
window.escapeHtml = escapeHtml;
