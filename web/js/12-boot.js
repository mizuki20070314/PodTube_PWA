/* Start-up: access key from a link, the tabs, the player surface, links opened from outside, the service worker. */
(function (PT) {
  'use strict';

  /** Opened with  #key=...  : the access key travels in the link the operator hands out (kept in this browser only). */
  function captureKey() {
    var m = /[#&?]key=([^&]+)/.exec(location.hash + location.search);
    if (!m) return false;
    var k = decodeURIComponent(m[1]);
    PT.gate.setKey(k);
    PT.gate.unlock(k);                       // also sets the cookie
    return true;
  }

  /** Things that arrive from outside: #/open/<link> (bookmarklet), #/watch/ID, ?url= (share target) ... */
  function handleLaunch() {
    var hash = location.hash || '', search = location.search || '', handled = false;
    var m;
    if ((m = /^#\/open\/(.+)$/.exec(hash))) {
      var target = m[1];
      try { target = decodeURIComponent(target); } catch (e) { /* keep */ }
      handled = PT.router.open(target) || false;
      if (!handled) PT.toast(PT.t('link.failed'));
    } else if ((m = /^#\/watch\/([\w-]{11})(?:\?list=([\w-]+))?/.exec(hash))) {
      PT.router.play({ id: m[1] }, null, m[2] || null); handled = true;
    } else if ((m = /^#\/channel\/(UC[\w-]{22})/.exec(hash))) {
      PT.router.openChannel(m[1]); handled = true;
    } else if ((m = /^#\/playlist\/([\w-]+)/.exec(hash))) {
      PT.router.openPlaylist(m[1]); handled = true;
    } else if ((m = /^#\/search\/(.+)$/.exec(hash))) {
      var q = m[1];
      try { q = decodeURIComponent(q); } catch (e) { /* keep */ }
      PT.router.openSearch(q); handled = true;
    } else if (search) {
      // Web Share Target: ?title=...&text=...&url=...
      var params = {};
      search.replace(/^\?/, '').split('&').forEach(function (kv) {
        var i = kv.indexOf('=');
        if (i > 0) { try { params[kv.slice(0, i)] = decodeURIComponent(kv.slice(i + 1).replace(/\+/g, ' ')); } catch (e) { /* ignore */ } }
      });
      var blob = [params.url, params.text, params.title].filter(Boolean).join(' ');
      var link = /https?:\/\/[^\s]+/.exec(blob);
      if (link) { handled = PT.router.open(link[0]) || false; }
      else if (params.q) { PT.router.openSearch(params.q); handled = true; }
    }
    if ((hash || search) && (handled || /key=/.test(hash + search))) {
      try { history.replaceState(null, '', location.pathname); } catch (e) { /* ignore */ }
    }
  }

  function registerWorker() {
    if (!('serviceWorker' in navigator)) return;
    var hadController = !!navigator.serviceWorker.controller;
    navigator.serviceWorker.register('sw.js').then(function (reg) {
      reg.addEventListener('updatefound', function () { /* a new version is being installed */ });
    }, PT.noop);
    navigator.serviceWorker.addEventListener('controllerchange', function () {
      // a new version took over: reload when nothing is playing so that the page matches its files
      if (!hadController) { hadController = true; return; }
      if (PT.player.state === 'idle' || PT.player.state === 'ended') location.reload();
      else PT.toast(PT.t('settings.updated'));
    });
  }

  function boot() {
    captureKey();
    PT.applyTheme();
    var app = PT.$('#app'), tabs = PT.$('#tabs'), tabbar = PT.$('#tabbar');
    PT.nav.init(app, tabs, tabbar, [PT.screens.home, PT.screens.shorts, PT.screens.subscriptions, PT.screens.library]);
    PT.watch.init(app, tabbar);
    PT.initEdgeSwipe(tabs);
    PT.account.start();
    PT.on('mini', function () { app.style.setProperty('--mini-inset', PT.watch.miniInset() + 'px'); });
    PT.on('settings', function () { document.documentElement.setAttribute('lang', PT.isJapanese() ? 'ja' : 'en'); });
    document.documentElement.setAttribute('lang', PT.isJapanese() ? 'ja' : 'en');
    handleLaunch();
    window.addEventListener('hashchange', handleLaunch);
    registerWorker();
    // the safe area changes with the orientation
    window.addEventListener('resize', PT.debounce(function () { PT.watch.layout(); }, 50));
    var boot = PT.$('#boot');
    if (boot) PT.remove(boot);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})(window.PT);
