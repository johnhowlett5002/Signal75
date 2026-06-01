// Signal 75 Service Worker
// Fail-safe network-first worker. It must never return null to Safari.

const CACHE_NAME = 'signal75-v202606011310';
const STATIC_ASSETS = [
  '/',
  '/index.html',
];

// On install — cache static assets
self.addEventListener('install', function(e) {
  self.skipWaiting();
  e.waitUntil(
    caches.open(CACHE_NAME).then(function(cache) {
      return cache.addAll(STATIC_ASSETS).catch(function() {
        return undefined;
      });
    })
  );
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

function plainResponse(message, status, contentType) {
  return new Response(message, {
    status: status || 200,
    headers: {
      'Content-Type': contentType || 'text/plain; charset=utf-8',
      'Cache-Control': 'no-store'
    }
  });
}

function offlinePage() {
  return plainResponse(
    '<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Signal 75</title></head><body style="font-family:system-ui;padding:32px;background:#08090d;color:#f4d35e"><h1>Signal 75</h1><p>Connection changed or dropped. Please reopen Signal 75 in a moment.</p></body></html>',
    503,
    'text/html; charset=utf-8'
  );
}

function jsonFallback(url) {
  var body = url.includes('performance.json')
    ? '{"days":[],"summary":{},"offline":true}'
    : '{"flat":[],"jumps":[],"topRatedFlat":[],"topRatedJumps":[],"offline":true}';
  return plainResponse(body, 200, 'application/json; charset=utf-8');
}

function networkFirst(request, fallbackKey, fallbackResponse) {
  return fetch(request, { cache: 'no-store' }).then(function(response) {
    if (response && response.ok) {
      var copy = response.clone();
      caches.open(CACHE_NAME).then(function(cache) {
        cache.put(fallbackKey || request, copy).catch(function() {
          return undefined;
        });
      });
    }
    return response || fallbackResponse();
  }).catch(function() {
    return caches.match(fallbackKey || request).then(function(cached) {
      return cached || fallbackResponse();
    });
  });
}

// On fetch — network first for live data and shell.
// Every branch returns a real Response so Safari never gets null.
self.addEventListener('fetch', function(e) {
  var url = e.request.url;
  var requestUrl = new URL(url);

  if (e.request.method !== 'GET') {
    return;
  }

  if (requestUrl.origin !== self.location.origin) {
    e.respondWith(
      fetch(e.request).catch(function() {
        return plainResponse('', 204);
      })
    );
    return;
  }

  // Always fetch fresh from network for data files
  if (url.includes('picks.json') || 
      url.includes('performance.json')) {
    e.respondWith(
      networkFirst(e.request, requestUrl.pathname, function() {
        return jsonFallback(url);
      })
    );
    return;
  }

  // Network first for the app shell and main JavaScript
  if (e.request.mode === 'navigate' ||
      url.includes('index.html') ||
      url.includes('app.js') ||
      url.endsWith('/')) {
    e.respondWith(
      networkFirst(e.request, requestUrl.pathname === '/' ? '/index.html' : requestUrl.pathname, function() {
        return requestUrl.pathname.includes('app.js')
          ? plainResponse('/* Signal 75 temporarily offline */', 503, 'application/javascript; charset=utf-8')
          : offlinePage();
      })
    );
    return;
  }

  // Cache first for other assets
  e.respondWith(
    caches.match(e.request).then(function(cached) {
      return cached || fetch(e.request).catch(function() {
        return plainResponse('', 204);
      });
    })
  );
});
