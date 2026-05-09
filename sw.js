// Signal 75 Service Worker
// Forces fresh content on every deploy

const CACHE_NAME = 'signal75-v1';
const STATIC_ASSETS = [
  '/',
  '/index.html',
];

// On install — cache static assets
self.addEventListener('install', function(e) {
  self.skipWaiting();
});

// On activate — clean old caches
self.addEventListener('activate', function(e) {
  e.waitUntil(
    caches.keys().then(function(keys) {
      return Promise.all(
        keys.filter(function(key) {
          return key !== CACHE_NAME;
        }).map(function(key) {
          return caches.delete(key);
        })
      );
    })
  );
  self.clients.claim();
});

// On fetch — network first for picks.json and app.js
// Cache first for everything else
self.addEventListener('fetch', function(e) {
  var url = e.request.url;

  // Always fetch fresh from network for data files
  if (url.includes('picks.json') || 
      url.includes('performance.json') || 
      url.includes('app.js')) {
    e.respondWith(
      fetch(e.request).catch(function() {
        return caches.match(e.request);
      })
    );
    return;
  }

  // Network first for index.html
  if (url.includes('index.html') || url.endsWith('/')) {
    e.respondWith(
      fetch(e.request).catch(function() {
        return caches.match(e.request);
      })
    );
    return;
  }

  // Cache first for other assets
  e.respondWith(
    caches.match(e.request).then(function(cached) {
      return cached || fetch(e.request);
    })
  );
});
