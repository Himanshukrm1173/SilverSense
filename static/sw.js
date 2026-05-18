const CACHE_NAME = 'silversense-v1';

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(clients.claim());
});

self.addEventListener('fetch', (event) => {
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request).catch(() => {
        return new Response(
          '<html><body style="background:#0f0f0f;color:#fff;font-family:sans-serif;text-align:center;padding:50px;"><h2>SilverSense</h2><p>You are offline. Live data requires an internet connection.</p></body></html>',
          { headers: { 'Content-Type': 'text/html' } }
        );
      })
    );
  }
});
