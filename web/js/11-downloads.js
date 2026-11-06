/* Offline downloads (DownloadManager.swift).  A video is saved as the playlists + segments of one HLS rendition (video and
   audio) in Cache Storage under /offline/<id>/...; the service worker answers those URLs from the cache, so the player
   plays a download exactly like a stream (hls.js and the native HLS player both fetch through the page). */
(function (PT) {
  'use strict';

  var CACHE = 'pt-offline';
  var supported = !!(window.caches && navigator.serviceWorker && window.fetch && window.Promise);
  var records = PT.ls.get('dl.records', []) || [];
  var pending = {};

  function base() { return location.pathname.replace(/[^\/]*$/, ''); }
  function prefix(id) { return base() + 'offline/' + id + '/'; }
  function saveRecords() { PT.ls.set('dl.records', records); }
  function changed() { PT.emit('downloads'); }

  function attrs(line) {
    var out = {}, re = /([A-Z0-9-]+)=("[^"]*"|[^,]*)/g, m;
    while ((m = re.exec(line)) !== null) out[m[1]] = m[2].charAt(0) === '"' ? m[2].slice(1, -1) : m[2];
    return out;
  }
  function text(url) {
    return fetch(url, { credentials: 'same-origin' }).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.text();
    });
  }
  function playlistResponse(body) {
    return new Response(body, { headers: { 'Content-Type': 'application/vnd.apple.mpegurl' } });
  }

  var D = PT.downloads = {
    supported: supported,
    records: records,
    pending: pending,

    record: function (id) {
      for (var i = 0; i < records.length; i++) if (records[i].video.id === id) return records[i];
      return null;
    },
    isDownloading: function (id) { return !!pending[id]; },
    /** 0...1 for a running download */
    fraction: function (id) {
      var p = pending[id];
      if (!p) return null;
      return p.total > 0 ? Math.min(1, p.done / p.total) : 0;
    },
    totalBytes: function () { return records.reduce(function (s, r) { return s + (r.bytes || 0); }, 0); },
    masterUrl: function (id) { return prefix(id) + 'master.m3u8'; },

    /** Downloads the rendition of `info` (a result of the play API) closest to `height`. */
    start: function (video, info, height) {
      var id = video.id;
      if (D.record(id) || pending[id] || !supported) return;
      var p = pending[id] = { video: PT.slimVideo(video), height: height, total: 0, done: 0, bytes: 0, cancelled: false };
      changed();
      run(p, video, info, height).then(function () {
        delete pending[id];
        records.unshift({ video: p.video, height: p.height, bytes: p.bytes, addedAt: Date.now() });
        saveRecords();
        changed();
        PT.toast(PT.t('downloads.done'));
      }, function (e) {
        delete pending[id];
        purge(id);
        changed();
        if (p.cancelled) return;
        PT.toast(e && (e.name === 'QuotaExceededError' || /quota/i.test(e.message || '')) ? PT.t('downloads.quota') : PT.t('downloads.failed'));
      });
    },

    cancel: function (id) {
      var p = pending[id];
      if (p) p.cancelled = true;
    },

    remove: function (id) {
      for (var i = records.length - 1; i >= 0; i--) if (records[i].video.id === id) records.splice(i, 1);
      saveRecords();
      purge(id).then(changed, changed);
    },

    /** Deletes what a download that never finished (the page was closed) left behind. */
    gc: function () {
      if (!supported) return;
      caches.open(CACHE).then(function (c) {
        return c.keys().then(function (reqs) {
          return Promise.all(reqs.map(function (r) {
            var m = new RegExp('/offline/([^/]+)/').exec(new URL(r.url).pathname);
            if (m && !D.record(m[1]) && !pending[m[1]]) return c.delete(r);
          }));
        });
      }).catch(PT.noop);
    }
  };

  function purge(id) {
    if (!supported) return Promise.resolve();
    return caches.open(CACHE).then(function (c) {
      return c.keys().then(function (reqs) {
        var pre = prefix(id);
        return Promise.all(reqs.filter(function (r) { return new URL(r.url).pathname.indexOf(pre) === 0; }).map(function (r) { return c.delete(r); }));
      });
    });
  }

  function run(p, video, info, height) {
    var id = video.id, off = prefix(id), cache;
    var masterUrl = PT.api.base + '/hls/' + info.sid + '/master.m3u8?maxh=' + height + '&hl=' + encodeURIComponent(PT.settings.hl()) +
      (PT.settings.preferredAudio ? '&audio=' + encodeURIComponent(PT.settings.preferredAudio) : '');
    var vSegs = [], aSegs = [];
    return caches.open(CACHE).then(function (c) { cache = c; return text(masterUrl); }).then(function (master) {
      // the variant closest to (not above) the wanted height, and the audio rendition of its group
      var lines = master.split('\n'), variants = [], medias = {};
      for (var i = 0; i < lines.length; i++) {
        var l = lines[i].trim();
        if (l.indexOf('#EXT-X-MEDIA:') === 0) { var m = attrs(l.slice(13)); if (m.TYPE === 'AUDIO') medias[m['GROUP-ID']] = m; }
        else if (l.indexOf('#EXT-X-STREAM-INF:') === 0) variants.push({ a: attrs(l.slice(18)), uri: (lines[i + 1] || '').trim() });
      }
      var best = null;
      variants.forEach(function (v) {
        var res = /(\d+)x(\d+)/.exec(v.a.RESOLUTION || ''), hh = res ? Math.min(+res[1], +res[2]) : 0;
        v.h = hh;
        if (hh <= height && (!best || hh > best.h || (hh === best.h && +v.a.BANDWIDTH > +best.a.BANDWIDTH))) best = v;
      });
      if (!best && variants.length) best = variants[0];
      if (!best) throw new Error('no variant');
      p.height = best.h || height;
      var audio = medias[best.a.AUDIO];
      var out = ['#EXTM3U', '#EXT-X-INDEPENDENT-SEGMENTS'];
      if (audio) out.push('#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="a",NAME="Default",DEFAULT=YES,AUTOSELECT=YES,URI="' + off + 'a.m3u8"');
      var si = ['BANDWIDTH', 'CODECS', 'RESOLUTION', 'FRAME-RATE'].filter(function (k) { return best.a[k]; }).map(function (k) {
        return k + '=' + (k === 'CODECS' ? '"' + best.a[k] + '"' : best.a[k]);
      });
      if (audio) si.push('AUDIO="a"');
      out.push('#EXT-X-STREAM-INF:' + si.join(','));
      out.push(off + 'v.m3u8');
      return Promise.all([text(best.uri), audio ? text(audio.URI) : Promise.resolve(null)]).then(function (pls) {
        function convert(src, tag, ext, list) {
          if (src === null) return null;
          if (src.indexOf('#EXT-X-ENDLIST') < 0) throw new Error('live');
          var n = 0, res = [];
          src.split('\n').forEach(function (l) {
            l = l.trim();
            if (!l) return;
            if (l.charAt(0) === '#') { res.push(l); return; }
            list.push(l);
            res.push(off + 's/' + tag + (n++) + '.' + ext);
          });
          return res.join('\n') + '\n';
        }
        var vPl = convert(pls[0], 'v', 'ts', vSegs);
        var aPl = convert(pls[1], 'a', 'aac', aSegs);
        p.total = vSegs.length + aSegs.length;
        var puts = [cache.put(off + 'master.m3u8', playlistResponse(out.join('\n') + '\n')), cache.put(off + 'v.m3u8', playlistResponse(vPl))];
        if (aPl) puts.push(cache.put(off + 'a.m3u8', playlistResponse(aPl)));
        return Promise.all(puts);
      });
    }).then(function () {
      var jobs = [];
      vSegs.forEach(function (u, n) { jobs.push({ url: u, key: off + 's/v' + n + '.ts' }); });
      aSegs.forEach(function (u, n) { jobs.push({ url: u, key: off + 's/a' + n + '.aac' }); });
      var next = 0, failed = null;
      function worker() {
        if (failed || p.cancelled || next >= jobs.length) return Promise.resolve();
        var job = jobs[next++];
        return fetch(job.url, { credentials: 'same-origin' }).then(function (r) {
          if (!r.ok) throw new Error('segment HTTP ' + r.status);
          p.bytes += parseInt(r.headers.get('Content-Length') || '0', 10) || 0;
          return cache.put(job.key, r);
        }).then(function () { p.done++; changed(); return worker(); }, function (e) { failed = e; });
      }
      return Promise.all([worker(), worker(), worker()]).then(function () {
        if (p.cancelled) throw new Error('cancelled');
        if (failed) throw failed;
      });
    });
  }

  D.gc();
})(window.PT);
