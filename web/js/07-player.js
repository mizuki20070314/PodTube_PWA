/* The player (PlayerManager.swift, Subtitles.swift, AudioTracks.swift, PlaybackStats.swift, Chapters.swift, Storyboard.swift,
   PlayHistory.swift): one <video> element for the whole app (inline, mini player, full screen, lock screen). */
(function (PT) {
  'use strict';
  var h = PT.h;

  // ---------------------------------------------------------------------------------------------------------------
  // chapters: timestamps in the description ("0:00 Intro"); they count only when the list starts at 0:00, has at least
  // two entries and is ascending
  // ---------------------------------------------------------------------------------------------------------------
  function leadingTimestamp(line) {
    var s = line;
    if (s.charAt(0) === '[' || s.charAt(0) === '(') s = s.slice(1);
    var token = '', i = 0;
    while (i < s.length && /[0-9:]/.test(s.charAt(i))) { token += s.charAt(i); i++; }
    if (token.indexOf(':') < 0 || token.length > 8) return null;
    var secs = PT.fmt.parseDuration(token);
    if (secs === null) return null;
    var rest = s.slice(i);
    if (rest.charAt(0) === ']' || rest.charAt(0) === ')') rest = rest.slice(1);
    return { secs: secs, rest: rest };
  }
  PT.chapters = {
    parse: function (description) {
      var out = [];
      String(description || '').split('\n').forEach(function (raw) {
        var line = raw.trim();
        if (!line) return;
        var lt = leadingTimestamp(line);
        if (!lt) return;
        var title = lt.rest.replace(/^[\s\-–—:|・.)(]+|[\s\-–—:|・.)(]+$/g, '');
        out.push({ start: lt.secs, title: title || PT.fmt.duration(lt.secs) });
      });
      if (out.length < 2 || out[0].start !== 0) return [];
      for (var i = 1; i < out.length; i++) if (out[i].start <= out[i - 1].start) return [];
      return out;
    },
    current: function (list, t) {
      var cur = null;
      for (var i = 0; i < list.length; i++) { if (list[i].start <= t) cur = list[i]; else break; }
      return cur;
    }
  };

  // ---------------------------------------------------------------------------------------------------------------
  // storyboards: the small preview pictures YouTube keeps for every video, as sheets of frames.
  // spec = baseURL|w#h#count#columns#rows#intervalMs#name#sigh|...
  // ---------------------------------------------------------------------------------------------------------------
  PT.Storyboard = function (spec, duration) {
    var parts = String(spec || '').split('|');
    if (parts.length < 2 || !(duration > 0) || (parts[0].indexOf('$L') < 0 && parts[0].indexOf('$N') < 0)) return null;
    var levels = [];
    parts.slice(1).forEach(function (p) {
      var f = p.split('#');
      if (f.length !== 8) return;
      var w = parseInt(f[0], 10), hh = parseInt(f[1], 10), n = parseInt(f[2], 10), c = parseInt(f[3], 10), r = parseInt(f[4], 10), iv = parseInt(f[5], 10);
      if (!(w > 0 && hh > 0 && n > 0 && c > 0 && r > 0) || isNaN(iv)) return;
      levels.push({ index: 0, width: w, height: hh, count: n, columns: c, rows: r, intervalMs: iv, name: f[6], sigh: f[7] });
    });
    if (!levels.length) return null;
    levels.sort(function (a, b) { return a.width !== b.width ? a.width - b.width : a.height - b.height; });
    levels.forEach(function (l, i) { l.index = i; l.framesPerSheet = Math.max(1, l.columns * l.rows); l.sheetCount = Math.ceil(l.count / l.framesPerSheet); });
    this.baseURL = parts[0];
    this.levels = levels;
    this.duration = duration;
  };
  PT.Storyboard.prototype = {
    level: function (minWidth) {
      for (var i = 0; i < this.levels.length; i++) if (this.levels[i].width >= minWidth) return this.levels[i];
      return this.levels[this.levels.length - 1];
    },
    spacing: function (l) { return l.intervalMs > 0 ? l.intervalMs / 1000 : this.duration / Math.max(1, l.count); },
    frameIndex: function (l, t) { return PT.clamp(Math.floor(Math.max(0, t) / this.spacing(l)), 0, l.count - 1); },
    cell: function (l, frame) {
      var f = PT.clamp(frame, 0, l.count - 1), sheet = Math.floor(f / l.framesPerSheet), j = f % l.framesPerSheet;
      return { sheet: sheet, column: j % l.columns, row: Math.floor(j / l.columns), frame: f };
    },
    cellAt: function (l, t) { return this.cell(l, this.frameIndex(l, t)); },
    time: function (l, frame) { return Math.min(this.duration, frame * this.spacing(l)); },
    sheetURL: function (l, sheet) {
      var name = l.name.replace('$M', String(sheet));
      return this.baseURL.replace('$L', String(l.index)).replace('$N', name) + '&sigh=' + l.sigh;
    }
  };

  // ---------------------------------------------------------------------------------------------------------------
  // captions: timedtext cues fetched through the server (the URLs are bound to the server's IP)
  // ---------------------------------------------------------------------------------------------------------------
  var Sub = PT.subtitles = {
    tracks: [], current: null, translateTo: null, cues: [], loading: false, gen: 0, sid: '',
    get isEnabled() { return !!Sub.current; },

    setTracks: function (list, sid) {
      Sub.gen++;
      Sub.tracks = list || []; Sub.sid = sid || ''; Sub.current = null; Sub.translateTo = null; Sub.cues = []; Sub.loading = false;
      PT.emit('subtitles');
      if (PT.settings.captionsAlways) {
        var t = Sub.preferred(Sub.tracks);
        if (t) Sub.select(t);
      }
    },
    clear: function () { Sub.setTracks([], ''); },
    preferred: function (list) {
      var lang = PT.settings.hl(), i;
      for (i = 0; i < list.length; i++) if (list[i].languageCode.indexOf(lang) === 0 && !list[i].isAuto) return list[i];
      for (i = 0; i < list.length; i++) if (list[i].languageCode.indexOf(lang) === 0) return list[i];
      for (i = 0; i < list.length; i++) if (!list[i].isAuto) return list[i];
      return list[0] || null;
    },
    disable: function () { Sub.gen++; Sub.current = null; Sub.translateTo = null; Sub.cues = []; Sub.loading = false; PT.emit('subtitles'); },
    select: function (track, tlang) {
      var g = ++Sub.gen;
      Sub.current = track; Sub.translateTo = tlang || null; Sub.cues = []; Sub.loading = true;
      PT.emit('subtitles');
      PT.api.captions(Sub.sid, track.i, tlang).then(function (r) {
        if (g !== Sub.gen) return;
        Sub.cues = r.cues || []; Sub.loading = false;
        PT.emit('subtitles');
      }, function () { if (g === Sub.gen) { Sub.loading = false; PT.emit('subtitles'); } });
    },
    /** The cue on screen at `time` (cues are sorted by start; they may overlap slightly). */
    textAt: function (time) {
      var cues = Sub.cues;
      if (!cues.length) return null;
      var lo = 0, hi = cues.length - 1, found = -1;
      while (lo <= hi) {
        var mid = (lo + hi) >> 1;
        if (cues[mid][0] <= time) { found = mid; lo = mid + 1; } else hi = mid - 1;
      }
      if (found < 0) return null;
      for (var i = found; i >= 0 && i > found - 3; i--) {
        if (time >= cues[i][0] && time <= cues[i][1]) return cues[i][2];
      }
      return null;
    }
  };

  // ---------------------------------------------------------------------------------------------------------------
  // audio track choice: the same rules as the server (hls.py choose_audio), to show which track plays
  // ---------------------------------------------------------------------------------------------------------------
  function primary(tag) { return String(tag || '').toLowerCase().split('-')[0].split('.')[0]; }
  function chooseAudio(tracks, pref, hl) {
    if (!tracks || tracks.length < 2) return null;
    var original = tracks[0], i;
    for (i = 0; i < tracks.length; i++) if (tracks[i].isDefault) { original = tracks[i]; break; }
    pref = String(pref || '').toLowerCase();
    if (pref === 'original') return original.id;
    if (pref) {
      for (i = 0; i < tracks.length; i++) if (tracks[i].id.split('.')[0].toLowerCase() === pref) return tracks[i].id;
      var same = tracks.filter(function (t) { return primary(t.id) === primary(pref); });
      if (same.length === 1) return same[0].id;
    }
    var mine = tracks.filter(function (t) { return primary(t.id) === primary(hl); });
    if (mine.length) {
      for (i = 0; i < mine.length; i++) if (mine[i].isDefault) return mine[i].id;
      return mine[0].id;
    }
    return original.id;
  }

  // ---------------------------------------------------------------------------------------------------------------
  // recording plays in the account's watch history (PlayHistoryReporter): the playback ping when a video starts and the
  // watch-time ping when it ends; best effort: three refusals in a row stop it for ten minutes
  // ---------------------------------------------------------------------------------------------------------------
  var reporter = {
    failures: 0, lastFailure: 0, current: null,
    started: function (videoId, position, reportsWatchTime) {
      if (!PT.auth.signedIn) return;
      if (reporter.failures >= 3) {
        if (Date.now() - reporter.lastFailure < 600000) return;
        reporter.failures = 0;
      }
      var c = reporter.current;
      if (c && c.videoId === videoId && c.end === null) return;           // this play is already reported
      var s = { videoId: videoId, cpn: PT.newCpn(), start: Math.max(0, position || 0), reports: reportsWatchTime !== false, tracking: null, end: null };
      reporter.current = s;
      PT.api.post('acct/track/start', { v: videoId, cpn: s.cpn, position: s.start }, { auth: true }).then(function (r) {
        reporter.failures = 0;
        s.tracking = r;
        if (s.end !== null) reporter.sendWatched(s);                         // the play ended before the answer came
      }, function (e) {
        if (e && e.code !== 'network') { reporter.failures++; reporter.lastFailure = Date.now(); }
      });
    },
    finished: function (position) {
      var s = reporter.current;
      if (!s || s.end !== null) return;
      s.end = Math.max(0, isFinite(position) ? position : 0);
      reporter.current = null;
      if (s.tracking) reporter.sendWatched(s);
    },
    reset: function () { reporter.failures = 0; },
    sendWatched: function (s) {
      if (!s.reports || !s.tracking || s.end - s.start < 5) return;
      PT.api.post('acct/track/end', { wt: s.tracking.watchtimeURL, cpn: s.cpn, from: s.start, to: s.end }, { auth: true }).catch(PT.noop);
    }
  };

  // ---------------------------------------------------------------------------------------------------------------
  // the player
  // ---------------------------------------------------------------------------------------------------------------
  var video = document.createElement('video');
  video.setAttribute('playsinline', '');
  video.setAttribute('webkit-playsinline', '');
  video.setAttribute('x-webkit-airplay', 'allow');
  video.setAttribute('preload', 'auto');
  video.setAttribute('crossorigin', 'anonymous');
  video.className = 'pvideo';
  video.removeAttribute('crossorigin');           // media comes from our own origin

  var nativeHls = !!(video.canPlayType && video.canPlayType('application/vnd.apple.mpegurl'));
  function useHlsJs() { return !!(window.Hls && window.Hls.isSupported && window.Hls.isSupported() && !PT.isApple); }

  var gen = 0, hls = null, engine = '', ready = false, wantsPlay = true, candidates = [], candidateIndex = 0, lastError = '';
  var pendingSeek = null, loadedCap = 0, netRetries = 0, mediaRetries = 0, sessionRetries = 0, lastSave = 0;
  var stalls = 0, bytesLoaded = 0, primed = false, sleepTimer = 0;
  var scrubGen = 0, scrubResume = false, scrubTarget = null, scrubFine = false, scrubBusy = false, scrubbing = false;
  var storyboardCache = null;
  // YouTube's embedded player, while it is the engine (06b-embed.js): used when YouTube refuses the server's IP (HTTP 429 `botcheck`).
  // Once the server was refused, new videos go straight to the embed for a few minutes instead of asking the server again.
  var embedCtl = null, embedTimer = 0;
  var RESTRICTED_MS = 5 * 60 * 1000;
  var restrictedUntil = +PT.ls.get('restrictedUntil', 0) || 0;
  function restricted() { return Date.now() < restrictedUntil; }
  function setRestricted(on) {
    restrictedUntil = on ? Date.now() + RESTRICTED_MS : 0;
    PT.ls.set('restrictedUntil', restrictedUntil);
  }

  var P = PT.player = {
    video: video,
    state: 'idle',            // idle | loading | playing | paused | buffering | ended | failed
    current: null, info: null, errorMessage: null,
    restricted: false,        // this video was refused to the server: the embedded player is (or was) used for it
    queue: [], queueIndex: -1, playlistId: null, upNext: [], chapters: [],
    loops: false, speed: PT.settings.playbackSpeed, maxHeight: PT.settings.maxQuality, showsStats: false,
    sleepEndsAt: 0, sleepAtEnd: false,
    history: reporter,
    get isScrubbing() { return scrubbing; }
  };

  function setState(s) {
    if (P.state === s) return;
    P.state = s;
    PT.emit('player');
    updateMediaSession();
  }

  // derived values ------------------------------------------------------------------------------------------------
  Object.defineProperty(P, 'embedActive', { get: function () { return engine === 'embed' && !!embedCtl; } });
  Object.defineProperty(P, 'currentTime', {
    get: function () {
      if (engine === 'embed') return embedCtl ? embedCtl.time() : 0;
      var t = video.currentTime;
      return isFinite(t) ? Math.max(0, t) : 0;
    }
  });
  Object.defineProperty(P, 'duration', {
    get: function () {
      if (engine === 'embed') {
        var ed = embedCtl ? embedCtl.duration() : 0;
        return ed > 0 ? ed : ((P.info && P.info.duration) || 0);
      }
      var d = video.duration;
      if (isFinite(d) && d > 0) return d;
      if (P.info && P.info.duration > 0) return P.info.duration;
      return 0;
    }
  });
  Object.defineProperty(P, 'isLive', { get: function () { return !!(P.info && P.info.isLive); } });
  Object.defineProperty(P, 'bufferedEnd', {
    get: function () {
      if (engine === 'embed') return 0;
      var t = video.currentTime, b = video.buffered;
      for (var i = 0; i < b.length; i++) if (t >= b.start(i) - 0.5 && t <= b.end(i)) return b.end(i);
      return b.length ? b.end(b.length - 1) : 0;
    }
  });
  Object.defineProperty(P, 'sourceName', {
    get: function () {
      if (!candidates.length) return '-';
      if (candidates[candidateIndex] === 'embed') return 'YouTube embed';
      if (candidates[candidateIndex] === 'prog') return 'progressive';
      if (candidates[candidateIndex] === 'offline') return 'download';
      return engine === 'hlsjs' ? 'HLS (hls.js)' : 'HLS (native)';
    }
  });
  Object.defineProperty(P, 'storyboard', {
    get: function () {
      var i = P.info;
      if (!i || i.isLive || !i.storyboardSpec) return null;
      var d = P.duration;
      if (!(d > 0)) return null;
      if (storyboardCache && storyboardCache.id === i.videoId && storyboardCache.d === d) return storyboardCache.v;
      var sb = new PT.Storyboard(i.storyboardSpec, d);
      storyboardCache = { id: i.videoId, d: d, v: sb };
      return sb;
    }
  });
  Object.defineProperty(P, 'hasNext', { get: function () { return !!nextCandidate(); } });
  Object.defineProperty(P, 'hasPrevious', { get: function () { return P.queueIndex > 0; } });

  // starting playback inside a user gesture: browsers only let an element play later (after the network answered) once a
  // gesture has played it, so the first tap plays a silent clip
  var SILENT = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=';
  function prime() {
    if (primed) return;
    primed = true;
    try {
      video.src = SILENT;
      var p = video.play();
      if (p && p.catch) p.catch(PT.noop);
    } catch (e) { /* ignore */ }
  }
  P.prime = prime;
  // the silent clip of prime() fires the same events as a video: they must not be taken for the real one
  function silent() {
    var src = video.getAttribute('src') || '';
    return src === SILENT;
  }

  // ---------------------------------------------------------------------------------------------------------------
  // opening a video
  // ---------------------------------------------------------------------------------------------------------------
  function indexOfId(list, id) {
    for (var i = 0; i < list.length; i++) if (list[i].id === id) return i;
    return -1;
  }

  P.play = function (v, queue, playlistId) {
    prime();
    reporter.finished(P.currentTime);                 // the play that this one replaces
    if (queue) {
      P.queue = queue;
      P.queueIndex = indexOfId(queue, v.id);
    } else if (!P.current || P.current.id !== v.id) {
      // opening a plain video ends any previous queue unless it contains the video
      var idx = indexOfId(P.queue, v.id);
      if (idx >= 0) P.queueIndex = idx; else { P.queue = []; P.queueIndex = -1; }
    }
    if (playlistId) P.playlistId = playlistId; else if (queue) P.playlistId = null;

    var g = ++gen;
    cancelScrub();
    if (!P.current || P.current.id !== v.id) P.chapters = [];
    P.current = v; P.info = null; P.errorMessage = null; P.restricted = false;
    candidates = []; candidateIndex = 0; lastError = '';
    wantsPlay = true; ready = false; pendingSeek = null;
    netRetries = mediaRetries = sessionRetries = 0; stalls = 0; bytesLoaded = 0;
    teardown();
    setState('loading');
    PT.emit('playerItem');

    var rec = PT.downloads && PT.downloads.record(v.id);
    if (rec) {
      P.info = { videoId: v.id, title: v.title, author: v.channelName, duration: 0, isLive: false, hls: true, offline: true,
        sid: '', captions: [], audioTracks: [], maxHeight: rec.height, heights: [], storyboardSpec: '' };
      candidates = ['offline'];
      PT.emit('playerItem');
      startCandidate(g);
      return;
    }
    // YouTube refused the server lately: do not ask it again for a few minutes, let this device's own connection play it
    if (restricted() && PT.settings.embedFallback && PT.embed) { startEmbed(g, v); return; }
    PT.api.play(v.id).then(function (info) {
      if (g !== gen) return;
      if (restrictedUntil) setRestricted(false);                  // the server is let through again
      P.info = info;
      candidates = [];
      if (info.hls) candidates.push('hls');
      if (info.progressive) candidates.push('prog');
      candidateIndex = 0;
      Sub.setTracks(info.captions, info.sid);
      var sb = P.storyboard;
      if (sb) prefetchStoryboard(sb);
      PT.emit('playerItem');
      startCandidate(g);
    }, function (err) {
      if (g !== gen) return;
      if (err && err.code === 'botcheck') {
        setRestricted(true);
        if (PT.settings.embedFallback && PT.embed) { startEmbed(g, v); return; }
        P.restricted = true;
        fail(PT.t('video.botCheck'));
        return;
      }
      fail((err && err.message) || PT.t('video.unavailable'));
    });
  };

  function fail(message) {
    P.errorMessage = message;
    setState('failed');
  }

  /**
   * The server cannot get streams for this video (YouTube answers its IP with a bot check): play it in YouTube's own embedded
   * player, which goes out over this device's connection.  The player follows the embed's state; the controls come from YouTube.
   */
  function startEmbed(g, v) {
    P.restricted = true;
    engine = 'embed';
    P.info = { videoId: v.id, title: v.title || '', author: v.channelName || '', duration: 0, isLive: false, hls: false, embed: true,
      sid: '', captions: [], audioTracks: [], maxHeight: 0, heights: [], storyboardSpec: '' };
    candidates = ['embed']; candidateIndex = 0;
    Sub.setTracks([], '');
    var startAt = PT.store.resumePosition(v.id) || 0, logged = false;
    PT.emit('playerItem');
    embedCtl = PT.embed.open(v.id, {
      start: startAt,
      onState: function (code) {
        if (g !== gen) return;
        var E = PT.embed;
        if (code === E.PLAYING) {
          ready = true;
          if (!logged) { logged = true; PT.store.addHistory(v, startAt, 0); }
          setState('playing');
        } else if (code === E.PAUSED) {
          if (P.state !== 'ended') setState('paused');
        } else if (code === E.BUFFERING) {
          if (ready && P.state !== 'paused') setState('buffering');
        } else if (code === E.ENDED) {
          itemEnded(g);
        }
      },
      onError: function (code) {
        if (g !== gen) return;
        destroyEngine();
        fail(PT.embed.notEmbeddable(code) ? PT.t('embed.disabled') : (code === 100 ? PT.t('video.unavailable') : PT.t('embed.failed')));
      }
    });
    // the embed has no events for the clock: once a second, the length and (every five seconds) where the viewer is
    embedTimer = setInterval(function () {
      if (g !== gen || !embedCtl) return;
      var d = embedCtl.duration();
      if (d > 0 && P.info && P.info.duration !== d) { P.info.duration = d; PT.emit('playerItem'); }
      if (P.state === 'playing' || P.state === 'paused') {
        var now = Date.now();
        if (now - lastSave > 5000) { lastSave = now; PT.store.updateProgress(v.id, embedCtl.time(), d); }
      }
    }, 1000);
  }

  function masterUrl(info) {
    var u = PT.api.base + '/hls/' + info.sid + '/master.m3u8?maxh=' + (P.maxHeight || 0) +
      '&hl=' + encodeURIComponent(PT.settings.hl());
    var pref = PT.settings.preferredAudio;
    if (pref) u += '&audio=' + encodeURIComponent(pref);
    return u;
  }

  function startCandidate(g) {
    if (g !== gen) return;
    if (candidateIndex >= candidates.length) {
      fail(PT.t('video.unavailable') + (lastError ? '\n(' + lastError + ')' : ''));
      return;
    }
    var kind = candidates[candidateIndex];
    if (kind === 'hls') loadSource(masterUrl(P.info), null);
    else if (kind === 'offline') loadSource(PT.downloads.masterUrl(P.current.id), null);
    else if (kind === 'prog') loadSource(PT.api.base + '/hls/' + P.info.sid + '/prog', null, true);
  }

  function nextCandidateSource(g, why) {
    if (g !== gen) return;
    lastError = why || lastError;
    candidateIndex++;
    startCandidate(g);
  }

  // engine --------------------------------------------------------------------------------------------------------
  function destroyEngine() {
    if (hls) { try { hls.destroy(); } catch (e) { /* ignore */ } hls = null; }
    if (embedCtl) { try { embedCtl.destroy(); } catch (e) { /* ignore */ } embedCtl = null; }
    clearInterval(embedTimer); embedTimer = 0;
    engine = '';
  }
  function teardown() {
    destroyEngine();
    ready = false;
  }

  function loadSource(url, startPos, progressive) {
    var g = gen;
    destroyEngine();
    ready = false;
    pendingSeek = startPos || null;
    loadedCap = P.maxHeight || 0;
    if (!progressive && useHlsJs()) {
      engine = 'hlsjs';
      hls = new window.Hls({
        enableWorker: true, lowLatencyMode: false, maxBufferLength: 40, maxMaxBufferLength: 90,
        abrEwmaDefaultEstimate: 4000000, startFragPrefetch: true, capLevelToPlayerSize: false,
        manifestLoadingMaxRetry: 2, levelLoadingMaxRetry: 3, fragLoadingMaxRetry: 4,
        startPosition: startPos || -1
      });
      hls.on(window.Hls.Events.MANIFEST_PARSED, function () { applyHlsCap(); });
      hls.on(window.Hls.Events.FRAG_LOADED, function (ev, d) { if (d && d.frag && d.frag.stats) bytesLoaded += d.frag.stats.total || 0; });
      hls.on(window.Hls.Events.ERROR, function (ev, d) { onHlsError(g, d); });
      hls.loadSource(url);
      hls.attachMedia(video);
    } else {
      engine = 'native';
      video.src = url;
      try { video.load(); } catch (e) { /* ignore */ }
    }
    video.defaultPlaybackRate = P.speed;
    video.playbackRate = P.speed;
  }

  function onHlsError(g, d) {
    if (g !== gen || !d) return;
    if (!d.fatal) return;
    var code = d.response && d.response.code;
    if (d.type === window.Hls.ErrorTypes.NETWORK_ERROR) {
      if ((code === 410 || code === 403) && sessionRetries < 2) { recoverSession(g); return; }
      if (netRetries++ < 2 && hls) { hls.startLoad(); return; }
    } else if (d.type === window.Hls.ErrorTypes.MEDIA_ERROR) {
      if (mediaRetries++ < 2 && hls) { hls.recoverMediaError(); return; }
    }
    nextCandidateSource(g, 'hls ' + d.details + (code ? ' ' + code : ''));
  }

  /** The stream URLs behind a session expired (after hours): resolve the video again and go on where it was. */
  function recoverSession(g) {
    sessionRetries++;
    var t = P.currentTime, vid = P.current && P.current.id;
    if (!vid) return;
    PT.api.play(vid).then(function (info) {
      if (g !== gen) return;
      P.info = info;
      Sub.setTracks(info.captions, info.sid);
      loadSource(masterUrl(info), t);
    }, function (e) { if (g === gen) fail((e && e.message) || PT.t('video.unavailable')); });
  }

  function levelIndexForHeight(hgt) {
    if (!hls || !hls.levels) return -1;
    var best = -1;
    hls.levels.forEach(function (l, i) { if (l.height && l.height <= hgt && (best < 0 || l.height >= hls.levels[best].height)) best = i; });
    if (best < 0) {                              // nothing that low: the lowest one
      var lowest = 0;
      hls.levels.forEach(function (l, i) { if ((l.height || 99999) < (hls.levels[lowest].height || 99999)) lowest = i; });
      return lowest;
    }
    return best;
  }
  function applyHlsCap() {
    if (!hls) return;
    hls.autoLevelCapping = P.maxHeight > 0 ? levelIndexForHeight(P.maxHeight) : -1;
  }

  /** Reloads the current source (quality / audio track changed) and goes on where it was. */
  function reloadHere() {
    if (!P.info || !candidates.length) return;
    var kind = candidates[candidateIndex];
    if (kind !== 'hls') return;
    var t = P.currentTime, was = !video.paused && !video.ended;
    wantsPlay = was || wantsPlay;
    loadSource(masterUrl(P.info), t);
  }

  // events of the element ------------------------------------------------------------------------------------------
  video.addEventListener('loadedmetadata', function () {
    if (!P.current || !P.info || silent()) return;
    if (ready) return;
    ready = true;
    var v = P.current, startAt = P.currentTime;
    if (pendingSeek !== null) { try { video.currentTime = pendingSeek; } catch (e) { /* ignore */ } startAt = pendingSeek; pendingSeek = null; }
    else {
      var pos = PT.store.resumePosition(v.id);
      if (pos !== null && !P.isLive && video.currentTime < 1) { try { video.currentTime = pos; } catch (e) { /* ignore */ } startAt = pos; }
    }
    PT.store.addHistory(v, startAt, P.duration);
    if (!PT.settings.pauseHistory && !P.info.offline) reporter.started(v.id, startAt, !P.isLive);
    if (wantsPlay) P.resume();
    updateMediaSession();
    PT.emit('playerItem');
  });
  video.addEventListener('playing', function () { if (P.current && P.state !== 'failed' && !silent()) setState('playing'); });
  video.addEventListener('pause', function () {
    if (!P.current || silent() || video.ended || P.state === 'failed' || P.state === 'ended') return;
    if (P.state === 'loading' && !ready) return;
    if (scrubbing) return;
    setState('paused');
  });
  video.addEventListener('waiting', function () {
    if (!P.current || silent() || !ready || P.state === 'failed' || P.state === 'ended' || P.state === 'paused') return;
    stalls++;
    setState('buffering');
  });
  video.addEventListener('canplay', function () { if (P.state === 'buffering' && !video.paused) setState('playing'); });
  video.addEventListener('seeked', function () { if (P.state === 'buffering' && !video.paused) setState('playing'); });
  video.addEventListener('ended', function () { if (silent() || !ready) return; itemEnded(gen); });
  video.addEventListener('durationchange', function () { PT.emit('playerItem'); });
  video.addEventListener('timeupdate', function () {
    if (!P.current || silent() || (P.state !== 'playing' && P.state !== 'paused' && P.state !== 'buffering')) return;
    var now = Date.now();
    if (now - lastSave > 5000) {
      lastSave = now;
      PT.store.updateProgress(P.current.id, P.currentTime, P.duration);
      updateMediaSessionPosition();
    }
  });
  video.addEventListener('error', function () {
    var src = video.getAttribute('src') || '';
    if (!P.current || !src || src === SILENT || src.indexOf('data:') === 0) return;
    if (engine === 'hlsjs') return;                        // hls.js reports its own errors
    var code = video.error ? video.error.code : 0;
    nextCandidateSource(gen, 'media error ' + code);
  });

  function itemEnded(g) {
    if (g !== gen || !P.current) return;
    PT.store.updateProgress(P.current.id, 0, P.duration);
    if (P.loops) {
      if (engine === 'embed') { if (embedCtl) embedCtl.seek(0); } else video.currentTime = 0;
      P.resume();
      return;
    }
    reporter.finished(P.duration);
    setState('ended');
    if (P.sleepAtEnd) { P.sleepAtEnd = false; PT.emit('player'); return; }
    if (PT.settings.autoplay) P.playNext(true);
  }

  // transport ------------------------------------------------------------------------------------------------------
  P.resume = function () {
    wantsPlay = true;
    if (engine === 'embed') {
      if (embedCtl) {
        if (P.state === 'ended') { setState('paused'); embedCtl.seek(0); }
        embedCtl.play();
      }
      return;
    }
    if (P.state === 'ended') { setState('paused'); try { video.currentTime = 0; } catch (e) { /* ignore */ } }
    video.playbackRate = P.speed;
    var p = video.play();
    if (p && p.catch) p.catch(function (e) {
      if (e && e.name === 'NotAllowedError') { wantsPlay = false; if (P.state !== 'failed') setState('paused'); }
    });
  };
  P.pause = function () {
    wantsPlay = false; scrubResume = false;
    if (engine === 'embed') { if (embedCtl) embedCtl.pause(); return; }
    video.pause();
  };
  P.toggle = function () {
    if (engine === 'embed') { if (P.state === 'playing' || P.state === 'buffering') P.pause(); else P.resume(); return; }
    if (video.paused || P.state === 'ended') P.resume(); else P.pause();
  };
  P.seek = function (t) {
    if (engine === 'embed') { if (embedCtl) embedCtl.seek(t); return; }
    try { video.currentTime = Math.max(0, t); } catch (e) { /* ignore */ }
  };
  P.skip = function (d) {
    var t = P.currentTime + d;
    if (P.duration > 0) t = Math.min(t, P.duration - 0.5);
    P.seek(t);
  };

  // scrubbing: pause while a finger holds the seek bar, follow it with one seek at a time, resume at the end
  P.beginScrub = function () {
    scrubGen++; scrubBusy = false; scrubTarget = null; scrubFine = false;
    if (!scrubResume) scrubResume = !video.paused;
    scrubbing = true;
    video.pause();
  };
  P.scrub = function (t, fine) {
    if (!scrubbing) return;
    scrubTarget = Math.max(0, t); scrubFine = fine;
    nextScrubSeek();
  };
  function nextScrubSeek() {
    if (!scrubbing || scrubBusy || scrubTarget === null) return;
    var t = scrubTarget;
    scrubTarget = null;
    scrubBusy = true;
    var g = scrubGen;
    var done = function () { video.removeEventListener('seeked', done); if (g !== scrubGen) return; scrubBusy = false; nextScrubSeek(); };
    video.addEventListener('seeked', done);
    try {
      if (!scrubFine && video.fastSeek) video.fastSeek(t); else video.currentTime = t;
    } catch (e) { done(); }
    setTimeout(function () { if (g === scrubGen && scrubBusy) { scrubBusy = false; video.removeEventListener('seeked', done); nextScrubSeek(); } }, 700);
  }
  P.endScrub = function (t, cb) {
    if (!scrubbing) { if (cb) cb(); return; }
    scrubbing = false; scrubGen++; scrubBusy = false; scrubTarget = null;
    var g = scrubGen;
    var done = function () {
      video.removeEventListener('seeked', done);
      if (g !== scrubGen) return;
      if (P.state === 'ended') setState('paused');
      if (scrubResume) { scrubResume = false; P.resume(); } else if (video.paused && P.state !== 'failed') setState('paused');
      if (cb) cb();
    };
    video.addEventListener('seeked', done);
    try { video.currentTime = Math.max(0, t); } catch (e) { done(); }
    setTimeout(function () { if (g === scrubGen) done(); }, 1500);
  };
  function cancelScrub() { scrubbing = false; scrubResume = false; scrubBusy = false; scrubTarget = null; scrubGen++; }

  // queue ----------------------------------------------------------------------------------------------------------
  function nextCandidate() {
    if (P.queueIndex >= 0 && P.queueIndex + 1 < P.queue.length) return P.queue[P.queueIndex + 1];
    if (P.queueIndex < 0 || !P.queue.length) {
      for (var i = 0; i < P.upNext.length; i++) if (!P.current || P.upNext[i].id !== P.current.id) return P.upNext[i];
    }
    return null;
  }

  /** Replaces the bare item (e.g. opened from a pasted link) with the full metadata once the watch page has loaded. */
  P.updateMetadata = function (v) {
    if (!P.current || P.current.id !== v.id) return;
    P.current = v;
    updateMediaSession();
  };

  /** Adopts the queue returned by the watch page (playlist playback) without restarting the current video. */
  P.adoptQueue = function (list, currentId, playlistId) {
    var idx = indexOfId(list, currentId);
    if (idx < 0) return;
    P.queue = list; P.queueIndex = idx;
    if (playlistId) P.playlistId = playlistId;
    PT.emit('player');
  };

  P.playNext = function () {
    var next = nextCandidate();
    if (!next) return;
    if (P.queueIndex >= 0 && P.queueIndex + 1 < P.queue.length) P.play(next, P.queue, P.playlistId);
    else P.play(next);
  };
  P.playPrevious = function () {
    if (P.currentTime > 5) { P.seek(0); return; }
    if (P.queueIndex > 0) P.play(P.queue[P.queueIndex - 1], P.queue, P.playlistId);
    else P.seek(0);
  };

  P.stop = function () {
    reporter.finished(P.currentTime);
    gen++;
    cancelScrub();
    teardown();
    video.pause();
    video.removeAttribute('src');
    try { video.load(); } catch (e) { /* ignore */ }
    P.current = null; P.info = null; P.queue = []; P.queueIndex = -1; candidates = [];
    clearTimeout(sleepTimer);
    setState('idle');
    if (navigator.mediaSession) { try { navigator.mediaSession.metadata = null; } catch (e) { /* ignore */ } }
    PT.emit('playerItem');
  };

  P.retry = function () {
    if (!P.current) return;
    setRestricted(false);                      // a retry asks the server again
    P.play(P.current, P.queue.length ? P.queue : null, P.playlistId);
  };

  // quality / speed / audio / sleep timer -------------------------------------------------------------------------
  P.setMaxHeight = function (hgt) {
    P.maxHeight = hgt;
    if (candidates[candidateIndex] === 'hls' || candidates[candidateIndex] === 'offline') {
      // the server hands out only the variants up to the cap (master.m3u8?maxh=): a higher cap, or a cap below what is playing
      // now, needs the manifest again; otherwise hls.js can just be told not to go higher
      var cur = Math.min(video.videoWidth || 0, video.videoHeight || 0);
      var raises = hgt === 0 ? loadedCap !== 0 : (loadedCap !== 0 && hgt > loadedCap);
      var cuts = hgt > 0 && cur > hgt;
      if (candidates[candidateIndex] === 'hls' && (raises || cuts || !(engine === 'hlsjs' && hls))) reloadHere();
      else if (engine === 'hlsjs' && hls) applyHlsCap();
    }
    PT.emit('player');
  };

  P.setSpeed = function (s) {
    P.speed = s;
    video.defaultPlaybackRate = s;
    video.playbackRate = s;
    if (engine === 'embed' && embedCtl) embedCtl.setSpeed(s);
    PT.emit('player');
  };

  /** The audio tracks of the video, the original first (fewer than two: nothing to choose from). */
  P.audioOptions = function () {
    var tracks = (P.info && P.info.audioTracks) || [];
    if (tracks.length < 2) return [];
    var selected = chooseAudio(tracks, PT.settings.preferredAudio, PT.settings.hl());
    var out = tracks.map(function (t) {
      return { id: t.id, title: t.name || t.id, lang: t.id.split('.')[0], isOriginal: !!t.isDefault, isSelected: t.id === selected };
    });
    return out.filter(function (o) { return o.isOriginal; }).concat(out.filter(function (o) { return !o.isOriginal; }));
  };
  P.selectAudio = function (o) {
    PT.settings.preferredAudio = o.isOriginal ? 'original' : o.lang.toLowerCase();
    reloadHere();
    PT.emit('player');
  };
  P.selectAutomaticAudio = function () {
    PT.settings.preferredAudio = '';
    reloadHere();
    PT.emit('player');
  };

  P.setSleepTimer = function (minutes, atEnd) {
    clearTimeout(sleepTimer);
    P.sleepEndsAt = 0;
    P.sleepAtEnd = !!atEnd;
    if (minutes) {
      P.sleepEndsAt = Date.now() + minutes * 60000;
      sleepTimer = setTimeout(function () { P.pause(); P.sleepEndsAt = 0; PT.emit('player'); }, minutes * 60000);
    }
    PT.emit('player');
  };

  // storyboard sheets -------------------------------------------------------------------------------------------
  var sheetCache = {};
  P.loadSheet = function (url) {
    var e = sheetCache[url];
    if (e) return e;
    e = sheetCache[url] = { img: new Image(), loaded: false, failed: 0 };
    e.img.onload = function () { e.loaded = true; PT.emit('storyboardSheet'); };
    e.img.onerror = function () { e.failed = Date.now(); delete sheetCache[url]; };
    e.img.referrerPolicy = 'no-referrer';
    e.img.src = url;
    return e;
  };
  function prefetchStoryboard(sb) {
    var level = sb.levels[0];
    for (var i = 0; i < Math.min(level.sheetCount, 2); i++) P.loadSheet(sb.sheetURL(level, i));
  }
  P.warmStoryboard = function (sb, level, t) {
    var first = sb.cellAt(level, t).sheet;
    for (var s = first; s <= Math.min(level.sheetCount - 1, first + 1); s++) P.loadSheet(sb.sheetURL(level, s));
  };

  // ---------------------------------------------------------------------------------------------------------------
  // stats ("stats for nerds")
  // ---------------------------------------------------------------------------------------------------------------
  P.statsLines = function () {
    var out = [], q = video.getVideoPlaybackQuality ? video.getVideoPlaybackQuality() : null;
    var lvl = (hls && hls.levels && hls.currentLevel >= 0) ? hls.levels[hls.currentLevel] : null;
    out.push('ID    ' + (P.current ? P.current.id : '-') + '  ' + P.sourceName + (P.isLive ? '  LIVE' : ''));
    var res = '-';
    if (video.videoWidth > 0) {
      res = video.videoWidth + 'x' + video.videoHeight;
      if (lvl && lvl.attrs && lvl.attrs['FRAME-RATE']) res += ' @' + Math.round(parseFloat(lvl.attrs['FRAME-RATE']));
    }
    out.push('Res   ' + res + '  max ' + (P.maxHeight === 0 ? 'auto' : P.maxHeight + 'p'));
    var codecs = [];
    if (lvl) { if (lvl.videoCodec) codecs.push(lvl.videoCodec); if (lvl.audioCodec) codecs.push(lvl.audioCodec); }
    out.push('Codec ' + (codecs.length ? codecs.join(' / ') : '-'));
    var indicated = lvl ? PT.fmt.bitrate(lvl.bitrate) : '-';
    var observed = hls && hls.bandwidthEstimate ? PT.fmt.bitrate(hls.bandwidthEstimate) : '-';
    out.push('Rate  ' + indicated + '  net ' + observed);
    var ahead = Math.max(0, P.bufferedEnd - video.currentTime);
    out.push('Buf   ' + ahead.toFixed(1) + ' s  drop ' + (q ? q.droppedVideoFrames : 0) + '  stall ' + stalls);
    out.push('Data  ' + (bytesLoaded ? PT.fmt.bytes(bytesLoaded) : '-') + '  speed ' + P.speed + 'x  vol ' + Math.round(video.volume * 100) + '%' + (video.muted ? ' (muted)' : ''));
    var audio = P.audioOptions().filter(function (o) { return o.isSelected; })[0];
    out.push('Audio ' + (audio ? audio.title : '-'));
    out.push('App   ' + PT.version + '  ' + (PT.isIOS ? 'iOS' : PT.isAndroid ? 'Android' : 'web') + '  ' + (navigator.platform || ''));
    return out;
  };

  // ---------------------------------------------------------------------------------------------------------------
  // Picture in Picture / AirPlay
  // ---------------------------------------------------------------------------------------------------------------
  /** Whether WebKit's own answer (webkitSupportsPresentationMode) can be trusted yet: it needs a loaded video. */
  function webkitPipKnown() {
    return typeof video.webkitSupportsPresentationMode === 'function' && video.readyState >= 1 && video.videoWidth > 0;
  }
  function webkitPipOk() {
    try { return !!video.webkitSupportsPresentationMode('picture-in-picture'); } catch (e) { return false; }
  }
  var pip = P.pip = {
    /**
     * 'ready'   the browser offers Picture in Picture;
     * 'blocked' the page-level flag says yes but WebKit says no for this video: iOS does that in Home Screen apps (WebKit bug 303885:
     *           document.pictureInPictureEnabled is true there, video.webkitSupportsPresentationMode('picture-in-picture') is false,
     *           and requestPictureInPicture() fails with NotSupportedError);
     * 'none'    no Picture in Picture API at all (the button stays hidden, as in the original app).
     */
    get state() {
      var standard = !!(document.pictureInPictureEnabled && video.requestPictureInPicture);
      var hasLegacy = typeof video.webkitSupportsPresentationMode === 'function';
      if (hasLegacy && webkitPipKnown()) return webkitPipOk() ? 'ready' : (standard ? 'blocked' : 'none');
      if (standard) return 'ready';
      return hasLegacy && webkitPipOk() ? 'ready' : 'none';        // an older WebKit: it answers once a video is loaded
    },
    get supported() { return pip.state === 'ready'; },
    get active() {
      return !!(document.pictureInPictureElement === video || video.webkitPresentationMode === 'picture-in-picture');
    },
    /** What the browser answers, for the diagnostics screen. */
    info: function () {
      var legacy = typeof video.webkitSupportsPresentationMode !== 'function' ? 'n/a' : (webkitPipKnown() ? (webkitPipOk() ? 'yes' : 'no') : 'unknown until a video is loaded');
      return 'document.pictureInPictureEnabled=' + (document.pictureInPictureEnabled ? 'yes' : 'no') + ', webkitSupportsPresentationMode=' + legacy;
    },
    /** Tells why it did not work (iOS keeps Picture in Picture away from Home Screen apps: nothing the app can do about it). */
    explain: function () {
      PT.toast(PT.t(PT.isIOS && PT.standalone ? 'pip.homeScreen' : 'pip.failed'));
    },
    toggle: function () {
      if (pip.active) {
        try {
          if (document.exitPictureInPicture && document.pictureInPictureElement) return document.exitPictureInPicture().catch(PT.noop);
          if (video.webkitSetPresentationMode) video.webkitSetPresentationMode('inline');
        } catch (e) { PT.toast(PT.t('pip.failed')); }
        return null;
      }
      var st = pip.state;
      if (st === 'blocked' || st === 'none') { pip.explain(); return null; }
      // the older WebKit call: some Safari versions only have this one, and it is the second try where the standard one is refused
      function legacy() {
        if (video.webkitSetPresentationMode && webkitPipOk()) { video.webkitSetPresentationMode('picture-in-picture'); return true; }
        return false;
      }
      try {
        if (video.requestPictureInPicture && document.pictureInPictureEnabled) {
          return video.requestPictureInPicture().catch(function (e) {
            try {
              if (legacy()) { explainIfNothingHappens(); return; }
            } catch (e2) { /* fall through */ }
            pip.explain(e);
          });
        }
        if (legacy()) explainIfNothingHappens();
        else pip.explain();
      } catch (e) { pip.explain(e); }
      return null;
    }
  };
  // The WebKit call has no result: it accepts the request and, where iOS refuses, simply nothing happens.  So look again a moment later,
  // and speak up only if PiP neither started nor came and went in between.
  var pipEvents = 0;
  function explainIfNothingHappens() {
    var seen = pipEvents;
    setTimeout(function () { if (!pip.active && pipEvents === seen) pip.explain(); }, 1500);
  }
  function pipChanged() { pipEvents++; PT.emit('pip'); }
  video.addEventListener('enterpictureinpicture', pipChanged);
  video.addEventListener('leavepictureinpicture', pipChanged);
  video.addEventListener('webkitpresentationmodechanged', pipChanged);

  // ---------------------------------------------------------------------------------------------------------------
  // fullscreen of the <video> itself.  iPhone / iPod touch (and Home Screen apps on iPad) have no fullscreen for a web page:
  // the only real fullscreen there is the OS video player, which takes over the <video> element with its own controls.
  // ---------------------------------------------------------------------------------------------------------------
  var capTrack = null, capCues = null;
  /** The OS player shows only what the <video> itself knows, so the captions are mirrored into a TextTrack for it. */
  function syncNativeCaptions() {
    if (!(PT.isIOS && video.addTextTrack && window.VTTCue)) return;
    try {
      if (!capTrack) {
        if (!Sub.isEnabled) return;                                    // no track until captions are wanted (it would show up empty in the OS menu)
        capTrack = video.addTextTrack('captions', 'PodTube', 'und');
        capTrack.mode = 'hidden';
      }
      if (capCues !== Sub.cues) {
        capCues = Sub.cues;
        var old = capTrack.cues;
        if (old) for (var i = old.length - 1; i >= 0; i--) capTrack.removeCue(old[i]);
        if (Sub.isEnabled) {
          Sub.cues.forEach(function (c) {
            capTrack.addCue(new window.VTTCue(c[0], c[1], String(c[2]).replace(/&/g, '&amp;').replace(/</g, '&lt;')));
          });
        }
      }
      setNativeCaptions(!!video.webkitDisplayingFullscreen);
    } catch (e) { /* captions in the OS player are a bonus */ }
  }
  function setNativeCaptions(inFullscreen) {
    if (!capTrack) return;
    try { capTrack.mode = inFullscreen && Sub.isEnabled && Sub.cues.length ? 'showing' : 'hidden'; } catch (e) { /* ignore */ }
  }
  PT.on('subtitles', syncNativeCaptions);

  var vfs = P.videoFullscreen = {
    get supported() { return !!(PT.isIOS && typeof video.webkitEnterFullscreen === 'function' && video.webkitSupportsFullscreen); },
    get active() { return !!video.webkitDisplayingFullscreen; },
    /** Must run inside the tap of the fullscreen button (iOS refuses it otherwise).  Returns whether the OS player was asked for. */
    enter: function () {
      if (!vfs.supported) return false;
      try {
        syncNativeCaptions();
        setNativeCaptions(true);
        video.webkitEnterFullscreen();
        return true;
      } catch (e) { setNativeCaptions(false); return false; }
    },
    exit: function () { try { if (video.webkitExitFullscreen) video.webkitExitFullscreen(); } catch (e) { /* ignore */ } },
    info: function () {
      return 'webkitEnterFullscreen=' + (typeof video.webkitEnterFullscreen === 'function' ? 'yes' : 'no') +
        ', webkitSupportsFullscreen=' + (video.webkitSupportsFullscreen ? 'yes' : 'no (until a video is loaded)');
    }
  };
  video.addEventListener('webkitbeginfullscreen', function () { setNativeCaptions(true); PT.emit('videoFullscreen'); });
  video.addEventListener('webkitendfullscreen', function () { setNativeCaptions(false); PT.emit('videoFullscreen'); });

  var airplay = P.airplay = {
    available: false,
    get supported() { return !!video.webkitShowPlaybackTargetPicker; },
    show: function () { if (video.webkitShowPlaybackTargetPicker) video.webkitShowPlaybackTargetPicker(); }
  };
  video.addEventListener('webkitplaybacktargetavailabilitychanged', function (e) {
    airplay.available = e.availability === 'available';
    PT.emit('airplay');
  });

  // ---------------------------------------------------------------------------------------------------------------
  // lock screen / media keys (Media Session API)
  // ---------------------------------------------------------------------------------------------------------------
  function updateMediaSession() {
    var ms = navigator.mediaSession;
    if (!ms || !P.current) return;
    try {
      var v = P.current;
      if (window.MediaMetadata) {
        ms.metadata = new window.MediaMetadata({
          title: v.title || '', artist: v.channelName || '',
          artwork: v.id ? [{ src: 'https://i.ytimg.com/vi/' + v.id + '/hqdefault.jpg', sizes: '480x360', type: 'image/jpeg' }] : []
        });
      }
      ms.playbackState = P.state === 'playing' || P.state === 'buffering' ? 'playing' : (P.state === 'idle' ? 'none' : 'paused');
    } catch (e) { /* ignore */ }
  }
  function updateMediaSessionPosition() {
    var ms = navigator.mediaSession;
    if (!ms || !ms.setPositionState || !(P.duration > 0) || P.isLive) return;
    try { ms.setPositionState({ duration: P.duration, playbackRate: P.speed, position: Math.min(P.currentTime, P.duration) }); } catch (e) { /* ignore */ }
  }
  (function installActions() {
    var ms = navigator.mediaSession;
    if (!ms || !ms.setActionHandler) return;
    function set(name, fn) { try { ms.setActionHandler(name, fn); } catch (e) { /* unsupported action */ } }
    set('play', function () { P.resume(); });
    set('pause', function () { P.pause(); });
    set('previoustrack', function () { P.playPrevious(); });
    set('nexttrack', function () { if (P.hasNext) P.playNext(); });
    set('seekbackward', function () { P.skip(-10); });
    set('seekforward', function () { P.skip(10); });
    set('seekto', function (d) { if (d && typeof d.seekTime === 'number') P.seek(d.seekTime); });
  })();

  // background: the original keeps playing when the app goes away if "background playback" is on, else it pauses
  document.addEventListener('visibilitychange', function () {
    if (document.hidden && !pip.active && !vfs.active && !PT.settings.backgroundPlay && P.state === 'playing') P.pause();
  });
  window.addEventListener('pagehide', function () { reporter.finished(P.currentTime); });
})(window.PT);
