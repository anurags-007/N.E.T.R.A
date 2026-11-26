const CACHE_NAME = 'netra-portal-v4';
const ASSETS_TO_CACHE = [
    '/frontend/index.html',
    '/frontend/dashboard.html',
    '/frontend/case_detail.html',
    '/frontend/requests.html',
    '/frontend/analytics.html',
    '/frontend/tools.html',
    '/frontend/admin.html',
    '/frontend/css/styles.css',
    '/frontend/js/app.js',
    '/frontend/js/api.js',
    '/frontend/js/security.js',
    '/frontend/js/lib/purify.min.js',
    '/frontend/vendor/bootstrap/css/bootstrap.min.css',
    '/frontend/vendor/bootstrap/js/bootstrap.bundle.min.js',
    '/frontend/vendor/bootstrap-icons/font/bootstrap-icons.min.css',
    '/frontend/vendor/bootstrap-icons/font/fonts/bootstrap-icons.woff2',
    '/frontend/vendor/bootstrap-icons/font/fonts/bootstrap-icons.woff',
    '/frontend/vendor/chartjs/chart.umd.min.js',
    '/frontend/vendor/vis-network/vis-network.min.js'
];

const API_PREFIXES = [
    '/auth/',
    '/cases/',
    '/requests/',
    '/files/',
    '/analysis/',
    '/admin/',
    '/tools/',
    '/bank/',
    '/npci/',
    '/freeze/',
    '/analytics/',
    '/financial-entities/'
];

self.addEventListener('install', (event) => {
    self.skipWaiting();
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS_TO_CACHE))
    );
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys()
            .then((keyList) =>
                Promise.all(
                    keyList.map((key) => {
                        if (key !== CACHE_NAME) {
                            return caches.delete(key);
                        }
                    })
                )
            )
            .then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', (event) => {
    const reqUrl = new URL(event.request.url);
    const isSameOrigin = reqUrl.origin === self.location.origin;
    const isApiRoute = API_PREFIXES.some((prefix) => reqUrl.pathname.startsWith(prefix));

    // Never intercept cross-origin CDNs, non-GET, authenticated, or API/evidence requests
    if (
        !isSameOrigin ||
        event.request.method !== 'GET' ||
        event.request.headers.has('Authorization') ||
        isApiRoute
    ) {
        return;
    }

    // Network-first for same-origin static files so updates take effect immediately
    event.respondWith(
        fetch(event.request)
            .then((response) => {
                if (response && response.ok) {
                    const copy = response.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
                }
                return response;
            })
            .catch(() => caches.match(event.request))
    );
});
