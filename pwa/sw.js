/**
 * Service Worker para Accident & Fire Tactical Detector PWA
 * Soporta instalación offline de la shell, bypass para video streams y WebSockets,
 * y despacho de notificaciones del sistema (Push / Web Notifications).
 */

const CACHE_NAME = 'accident-detector-pwa-v4';
const ASSETS_TO_CACHE = [
  '/',
  '/manifest.json',
  '/static/style.css',
  '/static/app.js',
  '/static/lucide.min.js',
  '/static/icon.svg',
  '/static/icon-192.png',
  '/static/icon-512.png'
];

self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      console.log('[SW] Precargando shell de la aplicación PWA...');
      return cache.addAll(ASSETS_TO_CACHE);
    })
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            console.log('[SW] Eliminando caché obsoleta:', key);
            return caches.delete(key);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Excluir streams de video en tiempo real y endpoints de API/WebSocket del caché
  if (
    url.pathname.startsWith('/api/') ||
    url.pathname.startsWith('/ws/') ||
    event.request.method !== 'GET'
  ) {
    return;
  }

  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      if (cachedResponse) {
        // Retornar caché y revalidar en segundo plano (Stale-While-Revalidate)
        fetch(event.request).then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, networkResponse));
          }
        }).catch(() => {});
        return cachedResponse;
      }
      return fetch(event.request);
    })
  );
});

// Soporte para Notificaciones del Sistema y Push API
self.addEventListener('push', (event) => {
  let data = { title: '[ALERTA] Incidente Detectado', body: 'Se ha detectado una anomalía crítica.' };
  if (event.data) {
    try {
      data = event.data.json();
    } catch (e) {
      data.body = event.data.text();
    }
  }

  const options = {
    body: data.body,
    icon: '/static/icon-192.png',
    badge: '/static/icon-192.png',
    vibrate: [250, 100, 250, 100, 500],
    data: { url: '/' },
    actions: [
      { action: 'open', title: 'Abrir Monitor' },
      { action: 'dismiss', title: 'Entendido' }
    ]
  };

  event.waitUntil(self.registration.showNotification(data.title, options));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  if (event.action !== 'dismiss') {
    event.waitUntil(
      clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
        if (clientList.length > 0) {
          return clientList[0].focus();
        }
        return clients.openWindow('/');
      })
    );
  }
});
