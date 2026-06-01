// Signal 75 service worker shutdown.
// The site is small and live-data driven, so a service worker is not worth
// the risk of stale or broken mobile data. This file clears old caches and
// unregisters itself.

self.addEventListener('install', function(event) {
  self.skipWaiting();
});

self.addEventListener('activate', function(event) {
  event.waitUntil(
    caches.keys()
      .then(function(keys) {
        return Promise.all(keys.map(function(key) {
          return caches.delete(key);
        }));
      })
      .then(function() {
        return self.registration.unregister();
      })
      .then(function() {
        return self.clients.matchAll({ type: 'window', includeUncontrolled: true });
      })
      .then(function(clients) {
        clients.forEach(function(client) {
          if (client.url) client.navigate(client.url);
        });
      })
  );
});

// Deliberately do not intercept fetch requests.
