// Service worker minimal : ne fait pas de cache agressif, juste le strict
// nécessaire pour que le navigateur propose "Ajouter à l'écran d'accueil".
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", () => self.clients.claim());
self.addEventListener("fetch", (event) => {
  event.respondWith(fetch(event.request).catch(() => caches.match(event.request)));
});
