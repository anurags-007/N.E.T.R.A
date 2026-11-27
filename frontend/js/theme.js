// N.E.T.R.A. Persistent High-Contrast Dark/Light Theme Controller (Strict CSP)
(function () {
    const STORAGE_KEY = 'netra_theme';

    function getInitialTheme() {
        const saved = localStorage.getItem(STORAGE_KEY) || localStorage.getItem('theme');
        if (saved === 'dark' || saved === 'light') return saved;
        return (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) ? 'dark' : 'light';
    }

    function applyTheme(theme) {
        const next = theme === 'dark' ? 'dark' : 'light';
        document.documentElement.setAttribute('data-bs-theme', next);
        localStorage.setItem(STORAGE_KEY, next);
        localStorage.setItem('theme', next);
        if (document.body) {
            document.body.classList.toggle('dark-mode', next === 'dark');
        }
        updateToggleUI(next);
        window.dispatchEvent(new CustomEvent('netra:themechange', { detail: { theme: next } }));
    }

    function updateToggleUI(theme) {
        const isDark = theme === 'dark';
        const btn = document.getElementById('darkModeToggle') || document.getElementById('netraThemeToggle');
        if (!btn) return;
        btn.innerHTML = '';
        const icon = document.createElement('i');
        icon.className = isDark ? 'bi bi-sun-fill' : 'bi bi-moon-stars-fill';
        btn.appendChild(icon);
        if (btn.dataset.showLabel === 'true') {
            btn.appendChild(document.createTextNode(isDark ? ' Light Mode' : ' Dark Mode'));
        }
        btn.setAttribute('title', isDark ? 'Switch to Light Mode' : 'Switch to Dark Mode');
        btn.setAttribute('aria-label', isDark ? 'Switch to Light Mode' : 'Switch to Dark Mode');
    }

    function ensureToggleButton() {
        let btn = document.getElementById('darkModeToggle') || document.getElementById('netraThemeToggle');
        if (!btn) {
            btn = document.createElement('button');
            btn.type = 'button';
            btn.id = 'netraThemeToggle';
            btn.dataset.showLabel = 'true';
            const sidebarProfile = document.querySelector('.sidebar .user-profile');
            if (sidebarProfile) {
                btn.className = 'btn btn-sm btn-outline-light w-100 mt-3';
                sidebarProfile.appendChild(btn);
            } else {
                btn.className = 'btn btn-sm btn-outline-secondary netra-theme-fab shadow-sm';
                document.body.appendChild(btn);
            }
        }
        if (!btn.dataset.netraBound) {
            btn.dataset.netraBound = '1';
            btn.addEventListener('click', () => {
                const cur = document.documentElement.getAttribute('data-bs-theme') || 'light';
                applyTheme(cur === 'dark' ? 'light' : 'dark');
            });
        }
        updateToggleUI(document.documentElement.getAttribute('data-bs-theme') || 'light');
    }

    // Apply immediately in <head> to prevent FOUC
    const initial = getInitialTheme();
    document.documentElement.setAttribute('data-bs-theme', initial);

    document.addEventListener('DOMContentLoaded', () => {
        document.body.classList.toggle('dark-mode', initial === 'dark');
        ensureToggleButton();
    });

    window.getNetraTheme = () => document.documentElement.getAttribute('data-bs-theme') || 'light';
    window.setNetraTheme = applyTheme;
})();
