// Distill service worker: keeps the app shell available so the home-screen app opens
// instantly and offline. The API and thumbnails always come from the network.
const SHELL = 'distill-shell-v2'
const ASSETS = 'distill-assets-v2'

self.addEventListener('install', event => {
  // The page that registered this worker loaded its scripts before the worker existed, so
  // cache the shell and the hashed assets it references now, or the first offline open is blank.
  event.waitUntil((async () => {
    const shell = await caches.open(SHELL)
    await shell.addAll(['/', '/manifest.json', '/icon-192.png'])
    const html = await (await shell.match('/')).text()
    const assets = [...html.matchAll(/(?:src|href)="(\/assets\/[^"]+)"/g)].map(m => m[1])
    await (await caches.open(ASSETS)).addAll(assets)
  })())
  self.skipWaiting()
})

self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys =>
    Promise.all(keys.filter(k => k !== SHELL && k !== ASSETS).map(k => caches.delete(k)))))
  self.clients.claim()
})

self.addEventListener('fetch', event => {
  const url = new URL(event.request.url)
  if (event.request.method !== 'GET' || url.origin !== location.origin || url.pathname.startsWith('/api/')) return

  // Pages: network first, so a new build shows up right away; the cached shell when offline.
  if (event.request.mode === 'navigate') {
    event.respondWith(fetch(event.request)
      .then(res => { caches.open(SHELL).then(c => c.put('/', res.clone())); return res })
      .catch(() => caches.match('/')))
    return
  }

  // Built assets have content hashes in their names, so a cached copy never goes stale.
  if (url.pathname.startsWith('/assets/')) {
    event.respondWith(caches.match(event.request).then(hit => hit ?? fetch(event.request).then(res => {
      if (res.ok) caches.open(ASSETS).then(c => c.put(event.request, res.clone()))
      return res
    })))
  }
})
