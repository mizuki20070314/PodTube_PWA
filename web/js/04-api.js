/* The API (api.cgi), the access key gate, the sign-in session and the account actions (Auth.swift, Account.swift). */
(function (PT) {
  'use strict';

  // ---------------------------------------------------------------------------------------------------------------
  // access key: the server refuses everything but the media of an open session without it (config.json: require_key)
  // ---------------------------------------------------------------------------------------------------------------
  var gate = PT.gate = {
    key: PT.ls.get('key', '') || '',
    promise: null,
    setKey: function (k) { gate.key = k || ''; if (k) PT.ls.set('key', k); else PT.ls.remove('key'); },

    /** Resolves when the server accepted a key (the user is asked when the stored one does not work). */
    ensure: function () {
      if (gate.promise) return gate.promise;
      gate.promise = new Promise(function (resolve) { gate.show(resolve); });
      gate.promise.then(function () { gate.promise = null; });
      return gate.promise;
    },

    unlock: function (key) {
      return fetch(PT.api.base + '/unlock', {
        method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: key })
      }).then(function (r) { return r.ok; }, function () { return false; });
    },

    show: function (done) {
      var input = PT.h('input', { type: 'password', class: 'gate-input', autocomplete: 'off', autocapitalize: 'none',
        autocorrect: 'off', spellcheck: 'false', placeholder: PT.t('gate.placeholder') });
      var msg = PT.h('div', { class: 'gate-msg' });
      var btn = PT.h('button', { class: 'btn-pill primary', type: 'button', text: PT.t('gate.submit') });
      var box = PT.h('div', { class: 'gate' },
        PT.h('div', { class: 'gate-card' },
          PT.h('div', { class: 'gate-logo', html: PT.logoSvg(40) }),
          PT.h('h1', { text: 'PodTube' }),
          PT.h('p', { text: PT.t('gate.intro') }),
          input, msg, btn,
          PT.h('p', { class: 'gate-note', text: PT.t('gate.note') })));
      function submit() {
        var k = input.value.trim();
        if (!k) return;
        btn.disabled = true;
        msg.textContent = '';
        gate.unlock(k).then(function (ok) {
          btn.disabled = false;
          if (ok) { gate.setKey(k); PT.remove(box); done(); }
          else { msg.textContent = PT.t('gate.wrong'); input.select(); }
        });
      }
      btn.addEventListener('click', submit);
      input.addEventListener('keydown', function (e) { if (e.keyCode === 13) submit(); });
      document.body.appendChild(box);
      setTimeout(function () { input.focus(); }, 50);
    }
  };

  // ---------------------------------------------------------------------------------------------------------------
  // the API
  // ---------------------------------------------------------------------------------------------------------------
  var visitorRec = PT.ls.get('visitor', null);
  var VISITOR_TTL = 14 * 86400 * 1000;

  var api = PT.api = {
    base: location.pathname.replace(/[^\/]*$/, '') + 'api.cgi',

    visitor: function () {
      if (visitorRec && Date.now() - visitorRec.t < VISITOR_TTL) return visitorRec.v;
      return '';
    },
    setVisitor: function (v) {
      if (!v) return;
      visitorRec = { v: v, t: Date.now() };
      PT.ls.set('visitor', visitorRec);
    },

    url: function (route, params) {
      var q = '';
      if (params) {
        var parts = [];
        for (var k in params) {
          if (params[k] === undefined || params[k] === null || params[k] === '') continue;
          parts.push(encodeURIComponent(k) + '=' + encodeURIComponent(params[k]));
        }
        if (parts.length) q = '?' + parts.join('&');
      }
      return api.base + '/' + route + q;
    },

    headers: function (extra) {
      var h = { 'X-PT-Hl': PT.settings.hl(), 'X-PT-Gl': PT.settings.gl() };
      if (gate.key) h['X-PT-Key'] = gate.key;
      var v = api.visitor();
      if (v) h['X-PT-Visitor'] = v;
      for (var k in extra) h[k] = extra[k];
      return h;
    },

    /** opts: {auth: true to send the account's token, signal} */
    request: function (method, route, params, body, opts, retried) {
      opts = opts || {};
      var tokenP = opts.auth ? PT.auth.token() : Promise.resolve('');
      return tokenP.then(function (token) {
        var extra = {};
        if (token) extra['X-PT-Token'] = token;
        var init = { method: method, headers: api.headers(extra), credentials: 'same-origin' };
        if (body !== undefined && body !== null) {
          init.body = JSON.stringify(body);
          init.headers['Content-Type'] = 'application/json';
        }
        if (opts.signal) init.signal = opts.signal;
        return fetch(api.url(route, params), init).then(function (res) {
          return res.text().then(function (text) {
            var js = null;
            try { js = text ? JSON.parse(text) : {}; } catch (e) { js = null; }
            if (res.ok && js) {
              if (js._visitor) { api.setVisitor(js._visitor); delete js._visitor; }
              return js;
            }
            var err = js && js.error ? js.error : { code: 'http', message: 'HTTP ' + res.status, status: res.status };
            if (res.status === 401 && !retried) {
              if (err.code === 'locked') return gate.ensure().then(function () { return api.request(method, route, params, body, opts, true); });
              if (err.code === 'auth' && opts.auth) {
                return PT.auth.refreshNow().then(function () { return api.request(method, route, params, body, opts, true); });
              }
            }
            var e = new Error(err.message || ('HTTP ' + res.status));
            e.code = err.code; e.status = res.status;
            throw e;
          });
        }, function (netErr) {
          if (netErr && netErr.name === 'AbortError') throw netErr;
          var e = new Error(PT.t('net.error'));
          e.code = 'network';
          throw e;
        });
      });
    },

    get: function (route, params, opts) { return api.request('GET', route, params, null, opts); },
    post: function (route, body, opts) { return api.request('POST', route, null, body || {}, opts); },

    // typed calls ---------------------------------------------------------------------------------------------------
    home: function (seen, fresh) { return api.post('home', { seen: seen, fresh: !!fresh }, { auth: PT.auth.signedIn }); },
    search: function (q, f) {
      f = f || {};
      return api.get('search', { q: q, sort: f.sort || '', date: f.date || '', kind: f.kind || '', dur: f.duration || '',
        live: f.live ? 1 : '', hd: f.hd ? 1 : '', cc: f.subtitles ? 1 : '', '4k': f.fourK ? 1 : '' });
    },
    continuation: function (token, endpoint) {
      return api.post('continuation', { token: token, endpoint: endpoint }, { auth: endpoint === 'tv' });
    },
    suggestions: function (q) { return api.get('suggest', { q: q }).then(function (r) { return r.suggestions || []; }); },
    watch: function (v, list) { return api.get('watch', { v: v, list: list }); },
    comments: function (token) { return api.post('comments', { token: token }); },
    channel: function (id) { return api.get('channel', { id: id }); },
    channelTab: function (id, params) { return api.get('channeltab', { id: id, params: params }); },
    channelBasics: function (id) { return api.get('channelbasics', { id: id }); },
    resolve: function (url) { return api.get('resolve', { url: url }).then(function (r) { return r.id; }); },
    playlist: function (id) { return api.get('playlist', { id: id }); },
    owner: function (v) { return api.get('owner', { v: v }).then(function (r) { return r.channel; }); },
    play: function (v) { return api.get('play', { v: v }); },
    captions: function (sid, i, tlang) { return api.get('captions', { sid: sid, i: i, tlang: tlang }); },
    reelSeq: function (seed) { return api.get('reel/seq', { seed: seed }).then(function (r) { return r.ids || []; }); },
    reelItem: function (v) { return api.get('reel/item', { v: v }); },
    subsFeed: function (channels) { return api.post('subsfeed', { channels: channels }); },
    diag: function () { return api.get('diag', null, { auth: PT.auth.signedIn }); },
    init: function () { return api.get('init'); }
  };

  // ---------------------------------------------------------------------------------------------------------------
  // sign-in session (tokens live in this browser only; the server keeps none)
  // ---------------------------------------------------------------------------------------------------------------
  var rec = PT.ls.get('auth', null);          // {accessToken, refreshToken, expiresAt}
  var profile = PT.ls.get('profile', null);   // {name, handle, avatar}
  var refreshing = null;

  var auth = PT.auth = {
    get signedIn() { return !!rec; },
    get profile() { return profile; },

    adopt: function (t) {
      rec = { accessToken: t.accessToken, refreshToken: t.refreshToken, expiresAt: Date.now() + (t.expiresIn || 3600) * 1000 };
      PT.ls.set('auth', rec);
      PT.emit('account');
    },
    setProfile: function (p) {
      profile = p;
      PT.ls.set('profile', p);
      PT.emit('accountProfile');
    },
    clearLocal: function () {
      rec = null; profile = null;
      PT.ls.remove('auth'); PT.ls.remove('profile');
      PT.emit('account');
    },

    /** A valid access token, refreshed first when it is about to expire. */
    token: function () {
      if (!rec) return Promise.reject(authError());
      if (rec.expiresAt - Date.now() > 90000) return Promise.resolve(rec.accessToken);
      return auth.refreshNow();
    },

    refreshNow: function () {
      if (!rec) return Promise.reject(authError());
      if (refreshing) return refreshing;
      var refresh = rec.refreshToken;
      refreshing = api.post('auth/refresh', { refreshToken: refresh }).then(function (r) {
        refreshing = null;
        if (r.status === 'ok' && rec) {
          rec.accessToken = r.accessToken;
          rec.expiresAt = Date.now() + (r.expiresIn || 3600) * 1000;
          PT.ls.set('auth', rec);
          return rec.accessToken;
        }
        if (r.status === 'revoked') auth.clearLocal();      // revoked from the Google account page: sign out locally
        throw authError();
      }, function (e) { refreshing = null; throw e; });
      return refreshing;
    },

    signOut: function () {
      var refresh = rec && rec.refreshToken;
      auth.clearLocal();
      if (refresh) api.post('auth/revoke', { token: refresh }).catch(PT.noop);
    }
  };

  function authError() {
    var e = new Error(PT.t('account.signInRequired'));
    e.code = 'auth';
    return e;
  }

  // ---------------------------------------------------------------------------------------------------------------
  // account actions: the local store stays the source of truth for the UI; while signed in each change is also sent to
  // the account and rolled back when YouTube refuses it
  // ---------------------------------------------------------------------------------------------------------------
  var playlistCache = null;
  var lastSignedIn = auth.signedIn;
  PT.on('account', function () {
    if (auth.signedIn !== lastSignedIn) { lastSignedIn = auth.signedIn; playlistCache = null; PT.emit('accountChanged'); }
  });

  function rollback(undo) {
    undo();
    PT.toast(PT.t('account.actionFailed'));
  }

  var acct = PT.account = {
    get isSignedIn() { return auth.signedIn; },

    start: function () { if (auth.signedIn && !profile) acct.refreshProfile(); },

    refreshProfile: function () {
      return api.get('acct/profile', null, { auth: true }).then(function (p) { auth.setProfile(p); }, PT.noop);
    },

    /** After the device code was approved: name / avatar and the channels that can be mirrored locally. */
    didSignIn: function () {
      PT.player && PT.player.history && PT.player.history.reset();
      acct.refreshProfile();
      api.get('acct/subscriptions', null, { auth: true }).then(function (s) { PT.store.mergeSubscriptions(s.channels || []); }, PT.noop);
      api.get('acct/channels', null, { auth: true }).then(function (s) { PT.store.mergeSubscriptions(s.channels || []); }, PT.noop);
    },

    signOut: function () { auth.signOut(); },

    toggleLike: function (video) { acct.setLike(video, PT.store.isLiked(video.id) ? 'none' : 'like'); },
    setLike: function (video, status) {
      var before = PT.store.isLiked(video.id);
      PT.store.setLiked(video, status === 'like');
      if (!auth.signedIn) return;
      api.post('acct/like', { v: video.id, status: status }, { auth: true }).catch(function () {
        rollback(function () { PT.store.setLiked(video, before); });
      });
    },

    setSubscribed: function (channel, on) {
      var before = PT.store.isSubscribed(channel.id);
      if (on) PT.store.subscribe(channel); else PT.store.unsubscribe(channel.id);
      if (!auth.signedIn) return;
      api.post('acct/subscribe', { id: channel.id, on: on }, { auth: true }).catch(function () {
        rollback(function () { if (before) PT.store.subscribe(channel); else PT.store.unsubscribe(channel.id); });
      });
    },
    toggleSubscribe: function (channel) { acct.setSubscribed(channel, !PT.store.isSubscribed(channel.id)); },

    setWatchLater: function (video, on) {
      var before = PT.store.isWatchLater(video.id);
      if (before !== on) PT.store.toggleWatchLater(video);
      if (!auth.signedIn) return;
      api.post('acct/editplaylist', { id: 'WL', v: video.id, add: on }, { auth: true }).catch(function () {
        rollback(function () { if (PT.store.isWatchLater(video.id) !== before) PT.store.toggleWatchLater(video); });
      });
    },

    addToPlaylist: function (playlist, video) {
      api.post('acct/editplaylist', { id: playlist.id, v: video.id, add: true }, { auth: true }).then(function () {
        PT.toast(PT.t('video.addedTo', playlist.title));
      }, function () { PT.toast(PT.t('account.actionFailed')); });
    },

    get hasPlaylistCache() { return !!playlistCache; },

    /** The account's own playlists (without "Watch later" / "Liked videos"), cached for the save sheet. */
    loadPlaylists: function (force) {
      if (!force && playlistCache) return Promise.resolve(playlistCache);
      return api.post('acct/browse', { browseId: 'FEplaylist_aggregation' }, { auth: true }).then(function (page) {
        var list = [];
        (page.items || []).forEach(function (it) {
          if (it.type === 'playlist' && it.playlist.id !== 'WL' && it.playlist.id !== 'LL') list.push(it.playlist);
        });
        playlistCache = list;
        return list;
      }, function () { return []; });
    },

    /** Applies what the account knows about a video (like state, subscription) to the local mirror. */
    loadWatchState: function (video) {
      if (!auth.signedIn) return Promise.resolve(null);
      return api.get('acct/watchstate', { v: video.id }, { auth: true }).catch(function () { return null; });
    }
  };
})(window.PT);
