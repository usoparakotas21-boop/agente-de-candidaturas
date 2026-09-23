// Service Worker para PWA do Candidatura Certa
const CACHE_NAME = "candidatura-certa-v1";
const STATIC_ASSETS = [
  "/",
  "/dashboard",
  "/vagas",
  "/curriculos",
  "/simulador-voz",
  "/static/theme.css",
  "/favicon.svg"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS).catch(() => {});
    })
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) return caches.delete(key);
        })
      );
    })
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  // Pass network requests through, falling back to cache if offline
  if (event.request.method !== "GET") return;
  event.respondWith(
    fetch(event.request).catch(() => {
      return caches.match(event.request).then((res) => res || Response.error());
    })
  );
});
