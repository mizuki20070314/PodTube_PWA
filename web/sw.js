/* PodTube service worker.
 *  - the app shell is cached (so PodTube starts offline); pages are fetched fresh when the network is there
 *  - /offline/<id>/... is answered from Cache Storage: the downloaded videos (HLS playlists + segments)
 *  - api.cgi (and with it every media relay URL) is never touched
 */
var VERSION = '__VERSION__';
var SHELL = 'pt-shell-' + VERSION;
var OFFLINE = 'pt-offline';
var PRECACHE = __PRECACHE__;
var SCOPE = self.registration.scope;                      // https://host/podtube/
var OFFLINE_PREFIX = new URL('offline/', SCOPE).pathname;
var DEV = VERSION === 'dev';                               // the local dev server: only the offline downloads are served

self.addEventListener('install', function (event) {
  event.waitUntil(caches.open(SHELL).then(function (cache) {
    return Promise.all(PRECACHE.map(function (u) { return cache.add(new Request(u, { cache: 'reload' })).catch(function () { /* best effort */ }); });
  }).then(function () { return self.skipWaiting(); }));
});

self.addEventListener('activate', function (event) {
  event.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (k) { return /^pt-shell-/.test(k) && k !== SHELL; }).map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});

function rangeResponse(res, rangeHeader) {
  var m = /^bytes=(\d*)-(\d*)$/.exec(rangeHeader || '');
  if (!m) return res;
  return res.blob().then(function (blob) {
    var size = blob.size, start = m[1] === '' ? Math.max(0, size - parseInt(m[2], 10)) : parseInt(m[1], 10);
    var end = m[1] === '' || m[2] === '' ? size - 1 : Math.min(size - 1, parseInt(m[2], 10));
    if (start >= size) return new Response('', { status: 416, headers: { 'Content-Range': 'bytes */' + size } });
    return new Response(blob.slice(start, end + 1), { status: 206, headers: {
      'Content-Type': res.headers.get('Content-Type') || 'application/octet-stream',
      'Content-Range': 'bytes ' + start + '-' + end + '/' + size, 'Accept-Ranges': 'bytes' } });
  });
}

function offlineResponse(request) {
  return caches.open(OFFLINE).then(function (c) { return c.match(request.url, { ignoreSearch: true }); }).then(function (res) {
    if (!res) return new Response('', { status: 404 });
    var type = res.headers.get('Content-Type');
    if (!type) {
      var p = new URL(request.url).pathname;
      type = /\.m3u8$/.test(p) ? 'application/vnd.apple.mpegurl' : /\.aac$/.test(p) ? 'audio/aac' : 'video/mp2t';
      res = new Response(res.body, { status: 200, headers: { 'Content-Type': type } });
    }
    return request.headers.get('range') ? rangeResponse(res, request.headers.get('range')) : res;
  });
}

self.addEventListener('fetch', function (event) {
  var req = event.request;
  if (req.method !== 'GET') return;
  var url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.indexOf(OFFLINE_PREFIX) === 0) { event.respondWith(offlineResponse(req)); return; }
  if (DEV || url.pathname.indexOf('/api.cgi') >= 0) return;
  var isPage = req.mode === 'navigate' || /\/(index\.html)?$/.test(url.pathname);
  if (isPage) {
    // the page itself: the network first (a new version shows up at once), the cached copy when offline
    event.respondWith(fetch(req).then(function (res) {
      var copy = res.clone();
      caches.open(SHELL).then(function (c) { c.put(new URL('index.html', SCOPE).href, copy); });
      return res;
    }).catch(function () {
      return caches.match(new URL('index.html', SCOPE).href).then(function (r) { return r || Response.error(); });
    }));
    return;
  }
  // everything else of the shell has a content hash in its name (or changes rarely): cache first
  event.respondWith(caches.match(req).then(function (hit) {
    if (hit) return hit;
    return fetch(req).then(function (res) {
      if (res && res.ok && (url.pathname.indexOf(SCOPE.replace(location.origin, '')) === 0)) {
        var copy = res.clone();
        caches.open(SHELL).then(function (c) { c.put(req, copy); });
      }
      return res;
    });
  }));
});
