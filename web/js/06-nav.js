/* Navigation: four tabs, a stack of screens per tab, and the router that knows how to open anything from anywhere
   (RootViewController.swift, Router.swift, Chrome.swift). */
(function (PT) {
  'use strict';
  var h = PT.h;

  // ---------------------------------------------------------------------------------------------------------------
  // screens.  A screen is {el, onShow?, onHide?, destroy?, scrollToTop?}.  Screens with the standard bar come from
  // PT.navScreen(title, content, o) which adds the back arrow + title bar.
  // ---------------------------------------------------------------------------------------------------------------
  PT.navScreen = function (title, content, o) {
    o = o || {};
    var titleEl = h('div', { class: 'bar-title', text: title || '' });
    var back = PT.iconButton('arrow_back', 24, 'bar-back', PT.t('common.close'));
    back.addEventListener('click', function () { PT.nav.back(); });
    var bar = h('div', { class: 'bar' }, back, titleEl);
    var right = h('div', { class: 'bar-right' });
    (o.right || []).forEach(function (b) { right.appendChild(b); });
    bar.appendChild(right);
    var el = h('div', { class: 'screen-inner' }, bar, h('div', { class: 'screen-body' }, content));
    var s = { el: el, setTitle: function (t) { titleEl.textContent = t || ''; }, bar: bar, rightEl: right };
    return s;
  };

  // ---------------------------------------------------------------------------------------------------------------
  // tab bar
  // ---------------------------------------------------------------------------------------------------------------
  var TABS = [
    { key: 'tab.home', icon: 'home_outline', iconOn: 'home' },
    { key: 'tab.shorts', icon: 'shorts_outline', iconOn: 'shorts' },
    { key: 'tab.subs', icon: 'subscriptions_outline', iconOn: 'subscriptions' },
    { key: 'tab.you', icon: 'account_circle_outline', iconOn: 'account_circle' }
  ];

  var Nav = PT.nav = {
    tabs: [],          // {pane, stack: [screen...], factory}
    selected: 0,
    root: null,

    init: function (root, tabsEl, tabbarEl, factories) {
      Nav.root = root;
      Nav.tabsEl = tabsEl;
      Nav.tabbarEl = tabbarEl;
      factories.forEach(function (f, i) {
        var pane = h('div', { class: 'tabpane' });
        tabsEl.appendChild(pane);
        Nav.tabs.push({ pane: pane, stack: [], factory: f, created: false });
      });
      Nav.buildTabbar();
      PT.on('settings', function () { Nav.buildTabbar(); });
      Nav.showTab(0);
    },

    buildTabbar: function () {
      PT.clear(Nav.tabbarEl);
      var items = TABS.map(function (t, i) {
        var b = h('button', { class: 'tabitem', type: 'button' },
          h('span', { class: 'tabicon', html: PT.iconSvg(i === Nav.selected ? t.iconOn : t.icon, 24) }),
          h('span', { class: 'tablabel', text: PT.t(t.key) }));
        b.addEventListener('click', function () { Nav.selectTab(i); });
        Nav.tabbarEl.appendChild(b);
        return b;
      });
      Nav.items = items;
      Nav.restyleTabbar();
    },

    restyleTabbar: function () {
      (Nav.items || []).forEach(function (b, i) {
        var sel = i === Nav.selected;
        b.classList.toggle('sel', sel);
        b.firstChild.innerHTML = PT.iconSvg(sel ? TABS[i].iconOn : TABS[i].icon, 24);
      });
    },

    /** Shows tab `i` (creating its root screen the first time). */
    showTab: function (i) {
      var tab = Nav.tabs[i];
      Nav.tabs.forEach(function (t, k) { t.pane.classList.toggle('active', k === i); });
      var prev = Nav.tabs[Nav.selected];
      if (prev && prev !== tab) Nav.fireHide(prev);
      Nav.selected = i;
      if (!tab.created) {
        tab.created = true;
        var s = tab.factory();
        Nav.attach(tab, s);
      }
      Nav.restyleTabbar();
      Nav.fireShow(tab);
    },

    selectTab: function (i) {
      var tab = Nav.tabs[i];
      if (i === Nav.selected) {
        if (tab.stack.length > 1) Nav.popToRoot();
        else { var top = tab.stack[0]; if (top && top.scrollToTop) top.scrollToTop(true); }
      } else Nav.showTab(i);
      if (PT.watch && PT.watch.isActive && PT.watch.progress < 0.5) PT.watch.setMinimized(true, true);
    },

    current: function () { return Nav.tabs[Nav.selected]; },
    top: function () { var t = Nav.current(); return t.stack[t.stack.length - 1]; },

    attach: function (tab, screen) {
      screen.el.classList.add('screen');
      tab.pane.appendChild(screen.el);
      tab.stack.push(screen);
    },

    fireShow: function (tab) { var s = tab.stack[tab.stack.length - 1]; if (s && s.onShow) s.onShow(); },
    fireHide: function (tab) { var s = tab.stack[tab.stack.length - 1]; if (s && s.onHide) s.onHide(); },

    /** Pushes a screen on the current tab with a slide-in. */
    push: function (screen) {
      var tab = Nav.current();
      var under = tab.stack[tab.stack.length - 1];
      if (under && under.onHide) under.onHide();
      screen.el.classList.add('screen');
      screen.el.style.transform = 'translate3d(100%,0,0)';
      tab.pane.appendChild(screen.el);
      tab.stack.push(screen);
      screen._hist = PT.hist.push(function (fromPop) { Nav.pop(true, fromPop); });
      void screen.el.offsetWidth;
      PT.tween(100, 0, 280, PT.ease.out, function (v) {
        screen.el.style.transform = 'translate3d(' + v + '%,0,0)';
        if (under) under.el.style.transform = 'translate3d(' + (-(100 - v) * 0.0 - (100 - v) * 0.25) + '%,0,0)';
      }, function () {
        screen.el.style.transform = '';
        if (under) { under.el.style.transform = ''; under.el.classList.add('under'); }
        if (screen.onShow) screen.onShow();
      });
      PT.emit('navchange');
    },

    /** The UI asked to go back (arrow button): goes through the history so that the back button stays in sync. */
    back: function () {
      var tab = Nav.current();
      if (tab.stack.length <= 1) return;
      var s = tab.stack[tab.stack.length - 1];
      if (s._hist) { var e = s._hist; s._hist = null; PT.hist.release(e); Nav.pop(true, false); }
      else Nav.pop(true, false);
    },

    /** Removes the top screen of the current tab (animated unless `quick`). */
    pop: function (animated, fromHistory) {
      var tab = Nav.current();
      if (tab.stack.length <= 1) return;
      var s = tab.stack.pop();
      if (fromHistory) s._hist = null;
      var under = tab.stack[tab.stack.length - 1];
      under.el.classList.remove('under');
      if (s.onHide) s.onHide();
      var done = function () {
        PT.remove(s.el);
        if (s.destroy) s.destroy();
        under.el.style.transform = '';
        if (under.onShow) under.onShow();
      };
      if (animated === false) { done(); PT.emit('navchange'); return; }
      PT.tween(0, 100, 220, PT.ease.in, function (v) {
        s.el.style.transform = 'translate3d(' + v + '%,0,0)';
        under.el.style.transform = 'translate3d(' + (-(100 - v) * 0.25) + '%,0,0)';
      }, done);
      PT.emit('navchange');
    },

    popToRoot: function () {
      var tab = Nav.current();
      while (tab.stack.length > 2) {
        var s = tab.stack.pop();
        if (s._hist) { PT.hist.release(s._hist); s._hist = null; }
        PT.remove(s.el);
        if (s.destroy) s.destroy();
      }
      if (tab.stack.length > 1) Nav.back();
    }
  };

  // left-edge swipe: the top screen follows the finger, a long or fast swipe goes back
  PT.initEdgeSwipe = function (el) {
    var pending = null;
    PT.drag(el, {
      axis: 'x', threshold: 8, bias: 1.5,
      start: function (x, y, e) {
        if (x > 24) return false;
        var tab = Nav.current();
        if (tab.stack.length <= 1) return false;
        if (PT.watch && PT.watch.isActive && PT.watch.progress < 0.5) return false;
        return true;
      },
      begin: function () {
        var tab = Nav.current();
        pending = { s: tab.stack[tab.stack.length - 1], under: tab.stack[tab.stack.length - 2] };
        pending.under.el.classList.remove('under');
      },
      move: function (dx) {
        if (!pending) return;
        var w = pending.s.el.offsetWidth || window.innerWidth;
        var d = Math.max(0, dx);
        pending.s.el.style.transform = 'translate3d(' + d + 'px,0,0)';
        pending.under.el.style.transform = 'translate3d(' + (-(1 - d / w) * w * 0.25) + 'px,0,0)';
      },
      end: function (dx, dy, vx) {
        if (!pending) return;
        var p = pending; pending = null;
        var w = p.s.el.offsetWidth || window.innerWidth;
        if (dx > w * 0.35 || vx > 700) {
          var tab = Nav.current();
          tab.stack.pop();
          if (p.s._hist) { var he = p.s._hist; p.s._hist = null; PT.hist.release(he); }
          if (p.s.onHide) p.s.onHide();
          PT.tween(Math.max(0, dx), w, 160, PT.ease.out, function (v) {
            p.s.el.style.transform = 'translate3d(' + v + 'px,0,0)';
            p.under.el.style.transform = 'translate3d(' + (-(1 - v / w) * w * 0.25) + 'px,0,0)';
          }, function () {
            PT.remove(p.s.el);
            if (p.s.destroy) p.s.destroy();
            p.under.el.style.transform = '';
            if (p.under.onShow) p.under.onShow();
            PT.emit('navchange');
          });
        } else {
          PT.tween(Math.max(0, dx), 0, 160, PT.ease.out, function (v) {
            p.s.el.style.transform = 'translate3d(' + v + 'px,0,0)';
            p.under.el.style.transform = 'translate3d(' + (-(1 - v / w) * w * 0.25) + 'px,0,0)';
          }, function () {
            p.s.el.style.transform = ''; p.under.el.style.transform = ''; p.under.el.classList.add('under');
          });
        }
      }
    });
  };

  // ---------------------------------------------------------------------------------------------------------------
  // router
  // ---------------------------------------------------------------------------------------------------------------
  function minimizeWatch() {
    if (PT.watch && PT.watch.isActive && PT.watch.progress < 0.5) PT.watch.setMinimized(true, true);
  }

  // youtube link -> target (Core/LinkParser.swift)
  PT.parseLink = function (text) {
    var t = (text || '').trim();
    if (!t || /\s/.test(t)) return null;
    var low = t.toLowerCase();
    if (low.indexOf('podtube://') === 0) {
      var rest = t.slice('podtube://'.length), decoded = rest;
      try { decoded = decodeURIComponent(rest); } catch (e) { /* keep */ }
      if (/^http/i.test(decoded) || /youtu/i.test(decoded)) return PT.parseLink(decoded);
      return PT.parseLink('https://youtube.com/' + decoded);
    }
    var s = t;
    if (s.indexOf('://') < 0) s = 'https://' + s;
    var m = /^[a-z][a-z0-9+.-]*:\/\/([^\/?#:]+)(?::\d+)?([^?#]*)(?:\?([^#]*))?/i.exec(s);
    if (!m) return null;
    var host = m[1].toLowerCase();
    ['www.', 'm.', 'music.'].forEach(function (p) { if (host.indexOf(p) === 0) host = host.slice(p.length); });
    var path = m[2] || '', query = {};
    (m[3] || '').split('&').forEach(function (kv) {
      if (!kv) return;
      var i = kv.indexOf('='), k = i < 0 ? kv : kv.slice(0, i), v = i < 0 ? '' : kv.slice(i + 1);
      try { v = decodeURIComponent(v.replace(/\+/g, ' ')); } catch (e) { /* keep */ }
      if (!(k in query)) query[k] = v;
    });
    var parts = path.split('/').filter(Boolean);
    var isId = function (x) { return /^[0-9A-Za-z_-]{11}$/.test(x || ''); };
    if (host === 'youtu.be') return isId(parts[0]) ? { type: 'video', id: parts[0], list: query.list || null } : null;
    if (host !== 'youtube.com' && host !== 'youtube-nocookie.com') return null;
    var first = parts[0];
    if (!first) return null;
    switch (first) {
      case 'watch': return isId(query.v) ? { type: 'video', id: query.v, list: query.list || null } : null;
      case 'shorts': case 'live': case 'embed': case 'v': case 'e':
        return isId(parts[1]) ? { type: 'video', id: parts[1], list: null } : null;
      case 'playlist': return query.list ? { type: 'playlist', id: query.list } : null;
      case 'channel': return parts[1] && parts[1].indexOf('UC') === 0 ? { type: 'channel', id: parts[1] } : null;
      case 'user': case 'c': return { type: 'resolve', url: 'https://www.youtube.com' + path };
      default:
        if (first.charAt(0) === '@') return { type: 'resolve', url: 'https://www.youtube.com/' + first };
        return null;
    }
  };

  var R = PT.router = {
    play: function (video, queue, playlistId) {
      if (PT.watch) PT.watch.start(video, queue, playlistId);
    },
    openShorts: function (videos, index) {
      minimizeWatch();
      if (PT.player) PT.player.pause();
      Nav.selectTab(1);
      if (PT.shortsScreen) PT.shortsScreen.open(videos, index);
    },
    openChannel: function (id, name) {
      if (!id) return;
      minimizeWatch();
      Nav.push(PT.screens.channel(id, name));
    },
    openPlaylist: function (id, title) {
      minimizeWatch();
      Nav.push(PT.screens.playlist(id, title));
    },
    openSearch: function (query) {
      minimizeWatch();
      PT.store.addSearch(query);
      Nav.push(PT.screens.searchResults(query));
    },
    openSearchScreen: function (prefill) {
      minimizeWatch();
      Nav.push(PT.screens.search(prefill));
    },
    openSettings: function () {
      minimizeWatch();
      Nav.push(PT.screens.settings());
    },
    push: function (screen) { Nav.push(screen); },

    /** Opens whatever a pasted / shared link points at. Returns false when the text is not a YouTube link. */
    open: function (text) {
      var target = PT.parseLink(text);
      if (!target) return false;
      if (target.type === 'video') R.play({ id: target.id }, null, target.list);
      else if (target.type === 'playlist') R.openPlaylist(target.id);
      else if (target.type === 'channel') R.openChannel(target.id);
      else {
        PT.api.resolve(target.url).then(function (id) { R.openChannel(id); }, function () { PT.toast(PT.t('link.failed')); });
      }
      return true;
    },

    // menus -------------------------------------------------------------------------------------------------------
    showVideoMenu: function (video, extra) {
      var actions = [];
      var saved = PT.store.isWatchLater(video.id);
      actions.push({ title: saved ? PT.t('video.removeWatchLater') : PT.t('video.watchLater'), icon: 'watch_later_outline', handler: function () {
        PT.account.setWatchLater(video, !saved);
        PT.toast(saved ? PT.t('video.removed') : PT.t('video.saved'));
      } });
      actions.push({ title: PT.t('video.addToPlaylist'), icon: 'playlist_add', handler: function () { R.showPlaylistPicker(video); } });
      if (!video.isLive && !video.isUpcoming && PT.downloads && PT.downloads.supported) {
        actions.push({ title: PT.t('video.download'), icon: 'file_download', handler: function () { R.startDownload(video); } });
      }
      if (video.channelId) {
        actions.push({ title: PT.t('video.channel'), icon: 'account_circle_outline', handler: function () { R.openChannel(video.channelId, video.channelName); } });
      }
      actions.push({ title: PT.t('video.share'), icon: 'share_outline', handler: function () { R.share(video); } });
      PT.sheet.show({ actions: actions.concat(extra || []) });
    },

    startDownload: function (video) {
      var dm = PT.downloads;
      if (!dm || !dm.supported) { PT.toast(PT.t('downloads.unsupported')); return; }
      if (dm.record(video.id) || dm.isDownloading(video.id)) { PT.toast(PT.t('downloads.already')); return; }
      PT.toast(PT.t('common.loading'));
      PT.api.play(video.id).then(function (info) {
        if (!info.hls || !info.heights.length) { PT.toast(PT.t('downloads.unavailable')); return; }
        var actions = info.heights.map(function (hgt) {
          var size = 0;
          info.sizes.forEach(function (s) { if (s.height === hgt) size = s.bytes; });
          return { title: hgt + 'p', icon: 'file_download', subtitle: PT.fmt.fileSize(size), handler: function () {
            dm.start(video, info, hgt);
            PT.toast(PT.t('downloads.started'));
          } };
        });
        PT.sheet.show({ title: PT.t('video.download'), actions: actions });
      }, function () { PT.toast(PT.t('downloads.failed')); });
    },

    showPlaylistPicker: function (video) {
      if (!PT.account.isSignedIn) { present([]); return; }
      if (!PT.account.hasPlaylistCache) PT.toast(PT.t('common.loading'));
      PT.account.loadPlaylists().then(present);
      function present(remote) {
        var actions = [];
        var later = PT.store.isWatchLater(video.id);
        actions.push({ title: PT.t('video.watchLater'), icon: 'watch_later_outline', checked: later, handler: function () {
          PT.account.setWatchLater(video, !later);
          PT.toast(later ? PT.t('video.removed') : PT.t('video.saved'));
        } });
        remote.forEach(function (p) {
          actions.push({ title: p.title, icon: 'playlist_play', subtitle: p.videoCount || null, handler: function () { PT.account.addToPlaylist(p, video); } });
        });
        PT.store.playlists.forEach(function (p) {
          var has = p.videos.some(function (v) { return v.id === video.id; });
          actions.push({ title: p.name, icon: 'playlist_play', subtitle: String(p.videos.length), checked: has, handler: function () {
            PT.store.togglePlaylist(video, p.id);
            PT.toast(has ? PT.t('video.removedFrom', p.name) : PT.t('video.addedTo', p.name));
          } });
        });
        actions.push({ title: PT.t('video.newPlaylist'), icon: 'add', handler: function () { R.promptNewPlaylist(video); } });
        PT.sheet.show({ title: PT.t('video.save'), actions: actions });
      }
    },

    promptNewPlaylist: function (video) {
      PT.dialog.prompt(PT.t('video.newPlaylist'), { placeholder: PT.t('video.playlistName'), okText: PT.t('common.create') }).then(function (name) {
        name = (name || '').trim();
        if (!name) return;
        var p = PT.store.createPlaylist(name, video || null);
        if (video) PT.toast(PT.t('video.addedTo', p.name));
      });
    },

    share: function (video) {
      PT.share({ title: video.title || '', url: 'https://youtu.be/' + video.id });
    }
  };
})(window.PT);
