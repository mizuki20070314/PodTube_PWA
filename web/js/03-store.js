/* Settings, theme and the local data (Store.swift, HomeSeen.swift, ChannelDirectory.swift). */
(function (PT) {
  'use strict';

  // ---------------------------------------------------------------------------------------------------------------
  // settings
  // ---------------------------------------------------------------------------------------------------------------
  var DEFAULTS = {
    theme: 'dark',            // the original starts dark (iOS 12 has no system dark mode)
    autoplay: true,
    backgroundPlay: true,
    pauseHistory: false,
    captionsAlways: false,
    maxQuality: 0,            // 0 = automatic, else the maximum height in pixels
    playbackSpeed: 1,
    preferredAudio: '',       // '' automatic, 'original', or a language tag
    uiLanguage: 'auto',       // 'auto' | 'ja' | 'en'
    contentRegion: ''         // '' = decided from the language of the browser
  };
  var saved = PT.ls.get('settings', {}) || {};

  function persist() { PT.ls.set('settings', saved); }

  var S = PT.settings = {};
  Object.keys(DEFAULTS).forEach(function (key) {
    Object.defineProperty(S, key, {
      enumerable: true,
      get: function () { return key in saved ? saved[key] : DEFAULTS[key]; },
      set: function (v) {
        saved[key] = v;
        persist();
        if (key === 'theme') { applyTheme(); PT.emit('theme'); }
        if (key === 'uiLanguage' || key === 'contentRegion') PT.emit('settings', key);
      }
    });
  });

  S.isDark = function () { return S.theme !== 'light'; };

  S.region = function () {
    if (saved.contentRegion) return saved.contentRegion;
    return PT.isJapanese() ? 'JP' : 'US';
  };

  var LANG_OF_REGION = { JP: 'ja', KR: 'ko', DE: 'de', FR: 'fr', ES: 'es', BR: 'pt' };
  S.hl = function () { return LANG_OF_REGION[S.region()] || 'en'; };
  S.gl = function () { return S.region(); };

  S.regions = [
    ['JP', '日本 / Japan'], ['US', 'United States'], ['GB', 'United Kingdom'], ['KR', '한국 / Korea'],
    ['DE', 'Deutschland'], ['FR', 'France'], ['ES', 'España'], ['BR', 'Brasil'], ['IN', 'India'], ['AU', 'Australia']
  ];

  function applyTheme() {
    var dark = S.isDark();
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', dark ? '#0f0f0f' : '#ffffff');
  }
  PT.applyTheme = applyTheme;
  applyTheme();

  // ---------------------------------------------------------------------------------------------------------------
  // the local store: history, subscriptions, watch later, likes, playlists, searches
  // ---------------------------------------------------------------------------------------------------------------
  var history = PT.ls.get('history', []) || [];
  var subs = PT.ls.get('subs', []) || [];
  var watchLater = PT.ls.get('watchlater', []) || [];
  var liked = PT.ls.get('liked', []) || [];
  var playlists = PT.ls.get('playlists', []) || [];
  var searches = PT.ls.get('searches', []) || [];

  function changed() { PT.emit('store'); }

  function idx(list, id) {
    for (var i = 0; i < list.length; i++) if (list[i].id === id) return i;
    return -1;
  }
  function hidx(videoId) {
    for (var i = 0; i < history.length; i++) if (history[i].video.id === videoId) return i;
    return -1;
  }
  function slim(v) {
    return { id: v.id, title: v.title || '', channelName: v.channelName || '', channelId: v.channelId || '',
      channelAvatar: v.channelAvatar || '', thumbnail: v.thumbnail || '', duration: v.duration || '', views: v.views || '',
      published: v.published || '', isLive: !!v.isLive, isUpcoming: !!v.isUpcoming, isShort: !!v.isShort };
  }
  PT.slimVideo = slim;

  var St = PT.store = {
    get history() { return history; },
    get subscriptions() { return subs; },
    get watchLater() { return watchLater; },
    get liked() { return liked; },
    get playlists() { return playlists; },
    get searches() { return searches; },

    // history ------------------------------------------------------------------------------------------------------
    addHistory: function (video, position, duration) {
      if (S.pauseHistory) return;
      var i = hidx(video.id);
      if (i >= 0) history.splice(i, 1);
      history.unshift({ video: slim(video), watchedAt: Date.now(), position: position || 0, duration: duration || 0 });
      if (history.length > 500) history.length = 500;
      PT.saveLater('history', function () { return history; });
      changed();
    },
    /** Fills in title / channel of an entry that was created from a bare id. */
    updateHistoryVideo: function (video) {
      var i = hidx(video.id);
      if (i < 0) return;
      var v = history[i].video;
      if (video.title) v.title = video.title;
      if (video.channelName) v.channelName = video.channelName;
      if (video.channelId) v.channelId = video.channelId;
      if (video.channelAvatar) v.channelAvatar = video.channelAvatar;
      if (video.thumbnail) v.thumbnail = video.thumbnail;
      PT.saveLater('history', function () { return history; });
    },
    updateProgress: function (videoId, position, duration) {
      var i = hidx(videoId);
      if (i < 0) return;
      history[i].position = position;
      if (duration > 0) history[i].duration = duration;
      PT.saveLater('history', function () { return history; }, 1500);
    },
    /** Watched fraction 0...1 (null when never watched). */
    progress: function (videoId) {
      var i = hidx(videoId);
      if (i < 0 || !(history[i].duration > 0)) return null;
      return PT.clamp(history[i].position / history[i].duration, 0, 1);
    },
    resumePosition: function (videoId) {
      var i = hidx(videoId);
      if (i < 0 || !(history[i].duration > 0)) return null;
      var e = history[i];
      if (e.position < 5 || e.position > e.duration - 10) return null;
      return e.position;
    },
    removeHistory: function (videoId) {
      var i = hidx(videoId);
      if (i >= 0) { history.splice(i, 1); PT.saveLater('history', function () { return history; }); changed(); }
    },
    clearHistory: function () {
      history.length = 0;
      PT.ls.set('history', history);
      changed();
    },

    // subscriptions ------------------------------------------------------------------------------------------------
    isSubscribed: function (cid) { return idx(subs, cid) >= 0; },
    subscribe: function (ch) {
      if (St.isSubscribed(ch.id)) return;
      subs.unshift({ id: ch.id, name: ch.name || '', handle: ch.handle || '', avatar: ch.avatar || '',
        subscribers: ch.subscribers || '', videoCount: ch.videoCount || '' });
      PT.saveLater('subs', function () { return subs; });
      changed();
    },
    unsubscribe: function (cid) {
      var i = idx(subs, cid);
      if (i >= 0) { subs.splice(i, 1); PT.saveLater('subs', function () { return subs; }); changed(); }
    },
    replaceSubscriptions: function (list) {
      subs.length = 0;
      for (var i = 0; i < list.length; i++) subs.push(list[i]);
      PT.saveLater('subs', function () { return subs; });
      changed();
    },
    /** Adds the channels that are not stored yet (mirrors the account's subscriptions). Silent when nothing is new. */
    mergeSubscriptions: function (list) {
      var added = false;
      for (var i = 0; i < list.length; i++) {
        if (!St.isSubscribed(list[i].id)) { subs.push(list[i]); added = true; }
      }
      if (added) { PT.saveLater('subs', function () { return subs; }); changed(); }
    },

    // watch later / liked ------------------------------------------------------------------------------------------
    isWatchLater: function (id) { return idx(watchLater, id) >= 0; },
    toggleWatchLater: function (video) {
      var i = idx(watchLater, video.id);
      if (i >= 0) watchLater.splice(i, 1); else watchLater.unshift(slim(video));
      PT.saveLater('watchlater', function () { return watchLater; });
      changed();
    },
    isLiked: function (id) { return idx(liked, id) >= 0; },
    setLiked: function (video, on) { if (St.isLiked(video.id) !== on) St.toggleLike(video); },
    toggleLike: function (video) {
      var i = idx(liked, video.id);
      if (i >= 0) liked.splice(i, 1); else liked.unshift(slim(video));
      PT.saveLater('liked', function () { return liked; });
      changed();
    },

    // playlists ----------------------------------------------------------------------------------------------------
    createPlaylist: function (name, video) {
      var p = { id: PT.uuid(), name: name, videos: video ? [slim(video)] : [] };
      playlists.unshift(p);
      PT.saveLater('playlists', function () { return playlists; });
      changed();
      return p;
    },
    deletePlaylist: function (id) {
      var i = idx(playlists, id);
      if (i >= 0) { playlists.splice(i, 1); PT.saveLater('playlists', function () { return playlists; }); changed(); }
    },
    togglePlaylist: function (video, id) {
      var i = idx(playlists, id);
      if (i < 0) return;
      var j = idx(playlists[i].videos, video.id);
      if (j >= 0) playlists[i].videos.splice(j, 1); else playlists[i].videos.push(slim(video));
      PT.saveLater('playlists', function () { return playlists; });
      changed();
    },
    removeFromPlaylist: function (videoId, id) {
      var i = idx(playlists, id);
      if (i < 0) return;
      var j = idx(playlists[i].videos, videoId);
      if (j >= 0) { playlists[i].videos.splice(j, 1); PT.saveLater('playlists', function () { return playlists; }); changed(); }
    },

    // search history -----------------------------------------------------------------------------------------------
    addSearch: function (q) {
      var t = (q || '').trim();
      if (!t || S.pauseHistory) return;
      var i = searches.indexOf(t);
      if (i >= 0) searches.splice(i, 1);
      searches.unshift(t);
      if (searches.length > 50) searches.length = 50;
      PT.saveLater('searches', function () { return searches; });
    },
    removeSearch: function (q) {
      var i = searches.indexOf(q);
      if (i >= 0) { searches.splice(i, 1); PT.saveLater('searches', function () { return searches; }); }
    },
    clearSearches: function () { searches.length = 0; PT.ls.set('searches', searches); }
  };

  // ---------------------------------------------------------------------------------------------------------------
  // HomeSeen: the Home videos that were shown on screen (newest last); a refresh moves these behind new videos
  // ---------------------------------------------------------------------------------------------------------------
  var seenOrder = (PT.ls.get('homeseen', []) || []).slice(-600);
  var seenSet = {};
  seenOrder.forEach(function (id) { seenSet[id] = true; });

  PT.homeSeen = {
    /** Everything shown before, plus the videos that were played (they are in the history). */
    ids: function () {
      var all = seenOrder.slice();
      for (var i = 0; i < history.length; i++) if (!seenSet[history[i].video.id]) all.push(history[i].video.id);
      return all;
    },
    mark: function (id) {
      if (!id || seenSet[id]) return;
      seenSet[id] = true;
      seenOrder.push(id);
      if (seenOrder.length > 600) delete seenSet[seenOrder.shift()];
      PT.saveLater('homeseen', function () { return seenOrder; }, 2000);
    }
  };

  // ---------------------------------------------------------------------------------------------------------------
  // ChannelDirectory: channel name -> (id, icon).  The signed-in account's feeds name the channel of a video but give
  // neither its id nor its icon, so list rows get them from here: remembered from every screen that does know them or,
  // failing that, asked from the video's watch data.
  // ---------------------------------------------------------------------------------------------------------------
  var MAX_ENTRIES = 800, MAX_RUNNING = 2, MAX_PENDING = 40, RETRY_AFTER = 120000;
  var byName = {}, byId = {}, order = [], inflight = {}, failed = {}, pending = [], running = 0;
  var seeded = false, seededSubs = -1;

  function nkey(name) { return String(name || '').trim().toLowerCase(); }

  (PT.ls.get('chdir', []) || []).forEach(function (e) { put(e, nkey(e.name)); });

  function put(e, key) {
    if (!byName[key]) order.push(key);
    byName[key] = e;
    if (e.id) byId[e.id] = e;
    while (order.length > MAX_ENTRIES) {
      var oldest = order.shift(), gone = byName[oldest];
      delete byName[oldest];
      if (gone && gone.id && byId[gone.id] && byId[gone.id].name === gone.name) delete byId[gone.id];
    }
  }
  function saveDir() {
    PT.saveLater('chdir', function () { return order.map(function (k) { return byName[k]; }).filter(Boolean); }, 1500);
  }

  var CD = PT.channelDirectory = {
    learn: function (id, name, avatar) {
      if (!name || !avatar) return;
      var key = nkey(name), old = byName[key];
      if (old && old.avatar === avatar && (!id || old.id === id)) return;
      var e = { id: id || '', name: name, avatar: avatar };
      if (!id && old) e.id = old.id;
      put(e, key);
      saveDir();
    },
    learnVideo: function (v) { CD.learn(v.channelId, v.channelName, v.channelAvatar); },
    learnChannel: function (c) { CD.learn(c.id, c.name, c.avatar); },

    seed: function () {
      if (!seeded) { seeded = true; history.forEach(function (h) { CD.learnVideo(h.video); }); }
      if (subs.length !== seededSubs) { seededSubs = subs.length; subs.forEach(CD.learnChannel); }
    },

    /** `v` with its channel icon / id filled in from what is known (a row that already has an icon is only remembered). */
    filled: function (v) {
      CD.seed();
      if (v.channelAvatar) { CD.learnVideo(v); return v; }
      var e = null;
      if (v.channelId) e = byId[v.channelId];
      if (!e && v.channelName) e = byName[nkey(v.channelName)];
      if (!e) return v;
      var out = {};
      for (var k in v) out[k] = v[k];
      out.channelAvatar = e.avatar;
      if (!out.channelId) out.channelId = e.id;
      return out;
    },

    /** Asks who owns the video (once per channel name, two requests at a time, newest row first). */
    resolve: function (v) {
      if (v.channelAvatar || !v.id) return;
      var key = nkey(v.channelName);
      if (!key || byName[key] || inflight[key]) return;
      if (failed[key] && Date.now() - failed[key] < RETRY_AFTER) return;
      delete failed[key];
      inflight[key] = true;
      pending.push({ videoId: v.id, key: key });
      if (pending.length > MAX_PENDING) { var dropped = pending.shift(); delete inflight[dropped.key]; }
      pump();
    },

    /** The channel of a video right now (tapping an icon whose channel id is not known yet). */
    owner: function (v) {
      var known = CD.filled(v);
      if (known.channelId) {
        return Promise.resolve({ id: known.channelId, name: known.channelName, avatar: known.channelAvatar });
      }
      return PT.api.get('owner', { v: v.id }).then(function (r) {
        if (r.channel) CD.learnChannel(r.channel);
        return r.channel || null;
      });
    }
  };

  function pump() {
    while (running < MAX_RUNNING && pending.length) {
      var job = pending.pop();
      running++;
      (function (job) {
        PT.api.get('owner', { v: job.videoId }).then(function (r) { finished(job.key, r.channel); },
          function () { finished(job.key, null); });
      })(job);
    }
  }
  function finished(key, ch) {
    running--;
    delete inflight[key];
    if (ch && ch.avatar) {
      var e = { id: ch.id, name: ch.name, avatar: ch.avatar };
      put(e, key);                                 // under the name the row used ...
      var own = nkey(ch.name);
      if (own && own !== key) put(e, own);         // ... and under the channel's own name
      saveDir();
      PT.emit('channelDirectory');
    } else {
      failed[key] = Date.now();
    }
    pump();
  }
})(window.PT);
