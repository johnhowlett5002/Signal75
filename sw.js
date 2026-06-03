// Signal 75 service worker emergency shutdown.
// The site is small and live-data driven, so a service worker is not worth
// the risk of stale or broken mobile data. This file clears old caches,
// unregisters itself, and never returns a null fetch response while old
// Safari/iPhone installs are being cleaned up.

var SHUTDOWN_VERSION = '20260603-1524';

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
        return self.clients.claim();
      })
      .then(function() {
        return self.clients.matchAll({ type: 'window', includeUncontrolled: true });
      })
      .then(function(clients) {
        clients.forEach(function(client) {
          if (client.url) client.navigate(client.url);
        });
      })
      .then(function() {
        return self.registration.unregister();
      })
  );
});

self.addEventListener('fetch', function(event) {
  event.respondWith(
    fetch(event.request)
      .catch(function() {
        if (event.request.mode === 'navigate') {
          return new Response(
            '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="2;url=/"><title>Signal 75</title><style>body{margin:0;background:#07080d;color:#f0c84a;font-family:Arial,sans-serif;padding:42px 28px;line-height:1.45}h1{font-size:40px;margin:0 0 24px}</style></head><body><h1>Signal 75</h1><p>Refreshing Signal 75. Please try again in a moment.</p><script>setTimeout(function(){location.replace("/")},1800)</script></body></html>',
            {
              status: 200,
              headers: { 'Content-Type': 'text/html; charset=utf-8' }
            }
          );
        }

        return new Response('', { status: 503, statusText: 'Signal 75 refreshing' });
      })
  );
});
