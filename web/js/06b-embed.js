/* YouTube's own embedded player (the IFrame Player API), used when YouTube refuses to hand out streams to the server.
 *
 * Why this exists: the stream URLs of the normal player are bound to the IP that asked for them, so the server asks and relays.  When
 * YouTube answers the server's IP with "sign in to confirm you're not a bot" (HTTP 429 `botcheck` from api.cgi/play), nothing can be
 * done from the server.  A web page cannot ask YouTube's internal API itself (it answers a foreign Origin with 403) nor read
 * googlevideo (no CORS headers), but the official embed runs in the browser and so goes out over THIS device's connection.
 * It brings its own controls (and ads); the app only follows its state.  Videos whose owner forbids embedding report error 101 / 150.
 */
(function (PT) {
  'use strict';
  var h = PT.h;
  var apiPromise = null;

  /** The API script of YouTube (once).  Resolves with the `YT` namespace; rejects when it cannot be loaded. */
  function loadApi() {
    if (window.YT && window.YT.Player) return Promise.resolve(window.YT);
    if (apiPromise) return apiPromise;
    apiPromise = new Promise(function (resolve, reject) {
      var previous = window.onYouTubeIframeAPIReady, settled = false;
      window.onYouTubeIframeAPIReady = function () {
        settled = true;
        try { if (previous) previous(); } catch (e) { /* not ours */ }
        resolve(window.YT);
      };
      var s = document.createElement('script');
      s.src = 'https://www.youtube.com/iframe_api';
      s.async = true;
      s.onerror = function () { apiPromise = null; reject(new Error('iframe api')); };
      document.head.appendChild(s);
      setTimeout(function () { if (!settled) { apiPromise = null; reject(new Error('iframe api timeout')); } }, 15000);
    });
    return apiPromise;
  }

  var E = PT.embed = {
    /** The element the embed lives in: set by the watch page (it sits on top of the player). */
    layer: null,

    /** YouTube's own state numbers. */
    ENDED: 0, PLAYING: 1, PAUSED: 2, BUFFERING: 3,

    /** Error numbers that mean "this video may not be played in an embed" (the owner forbids it). */
    notEmbeddable: function (code) { return code === 101 || code === 150; },

    /**
     * Starts `videoId` in the embedded player.  o: {start (s), onState(code), onError(code), onReady()}.
     * Returns a controller: play() pause() seek(t) setSpeed(r) time() duration() state() destroy().  Every call is safe before the
     * player is ready (it does nothing) and after destroy().
     */
    open: function (videoId, o) {
      o = o || {};
      var dead = false, player = null, ticker = 0, state = -1;
      var mount = h('div', { class: 'embed-mount' });
      if (E.layer) E.layer.appendChild(mount);

      function safe(fn, dflt) { try { return fn(); } catch (e) { return dflt; } }

      var c = {
        play: function () { if (player) safe(function () { player.playVideo(); }); },
        pause: function () { if (player) safe(function () { player.pauseVideo(); }); },
        seek: function (t) { if (player) safe(function () { player.seekTo(Math.max(0, t), true); }); },
        setSpeed: function (r) { if (player) safe(function () { player.setPlaybackRate(r); }); },
        time: function () { var t = player ? safe(function () { return player.getCurrentTime(); }, 0) : 0; return isFinite(t) && t > 0 ? t : 0; },
        duration: function () { var d = player ? safe(function () { return player.getDuration(); }, 0) : 0; return isFinite(d) && d > 0 ? d : 0; },
        state: function () { return state; },
        destroy: function () {
          dead = true;
          clearInterval(ticker);
          if (player) safe(function () { player.destroy(); });
          player = null;
          if (mount.parentNode) mount.parentNode.removeChild(mount);
        }
      };

      loadApi().then(function (YT) {
        if (dead) return;
        player = new YT.Player(mount, {
          videoId: videoId, width: '100%', height: '100%',
          playerVars: {
            autoplay: 1, playsinline: 1, rel: 0, enablejsapi: 1, fs: 1, origin: location.origin,
            start: Math.max(0, Math.floor(o.start || 0)), hl: PT.settings.hl()
          },
          events: {
            onReady: function () { if (!dead && o.onReady) o.onReady(); },
            onStateChange: function (e) {
              if (dead) return;
              state = e.data;
              if (o.onState) o.onState(e.data);
            },
            onError: function (e) { if (!dead && o.onError) o.onError(e.data); }
          }
        });
      }, function () {
        if (!dead && o.onError) o.onError(-1);             // the API script itself did not load
      });
      return c;
    }
  };

  E.layerElement = function () {
    return h('div', { class: 'embed-layer', hidden: true });
  };
})(window.PT);
