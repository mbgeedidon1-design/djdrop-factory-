// ============================================================
// SERVICE WORKER - Offline Cache for DJ Drop Factory PWA
// ============================================================

const CACHE_NAME = 'dj-drop-factory-v2-offline';
const URLS_TO_CACHE = [
  '/',
  '/static/manifest.json',
  '/static/icon.svg'
];

// Install: Cache the app shell
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(URLS_TO_CACHE))
      .then(() => self.skipWaiting())
  );
});

// Activate: Clean old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name !== CACHE_NAME)
          .map((name) => caches.delete(name))
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch: Serve from cache if offline, else fetch from network
self.addEventListener('fetch', (event) => {
  event.respondWith(
    caches.match(event.request).then((response) => {
      // Return cached version or fetch from network
      const fetchPromise = fetch(event.request).then((networkResponse) => {
        // Update cache with fresh version
        if (networkResponse && networkResponse.status === 200) {
          const clone = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        }
        return networkResponse;
      }).catch(() => {
        // Network failed - already returning cached response if available
      });

      return response || fetchPromise;
    })
  );
});
