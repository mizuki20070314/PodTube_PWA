/* Screens, part 2: Channel, Playlist, Settings, Sign-in, Diagnostics, Downloads
   (ChannelViewController, PlaylistViewController, SettingsViewController, SignInViewController, DiagnosticsViewController). */
(function (PT) {
  'use strict';
  var h = PT.h;
  var S = PT.screens;

  // ---------------------------------------------------------------------------------------------------------------
  // Channel
  // ---------------------------------------------------------------------------------------------------------------
  S.channel = function (channelId, name) {
    var info = null, tabIndex = 0, loadedInfo = false;
    var lazy = PT.lazyLoader(null);

    // header: banner, avatar, name, stats, subscribe button, tab strip
    var banner = PT.mkImg('chh-banner');
    var bannerBox = h('div', { class: 'chh-bannerbox', hidden: true }, banner);
    var avatar = PT.mkImg('avatar chh-avatar');
    var nameEl = h('div', { class: 'chh-name', text: name || '' });
    var metaEl = h('div', { class: 'chh-meta' });
    var subBtn = PT.subscribeButton(function () { return info ? asItem(info) : null; });
    subBtn.classList.add('chh-sub');
    var tabsEl = h('div', { class: 'chh-tabs' });
    var headEl = h('div', { class: 'chh' }, bannerBox,
      h('div', { class: 'chh-row' }, avatar, h('div', { class: 'chh-txt' }, nameEl, metaEl)),
      h('div', { class: 'chh-subrow' }, subBtn), tabsEl);

    function asItem(i) { return { id: i.id, name: i.name, handle: i.handle, avatar: i.avatar, subscribers: i.subscribers, videoCount: i.videoCount }; }

    function configureHeader() {
      nameEl.textContent = info.name;
      metaEl.textContent = [info.handle, info.subscribers, info.videoCount].filter(Boolean).join(' · ');
      lazy.set(avatar, info.avatar);
      bannerBox.hidden = !info.banner;
      if (info.banner) lazy.set(banner, info.banner);
      if (subBtn._refresh) subBtn._refresh();
      PT.clear(tabsEl);
      info.tabs.forEach(function (t, i) {
        var b = h('button', { class: 'chh-tab' + (i === tabIndex ? ' sel' : ''), type: 'button' }, h('span', { text: t.title }));
        b.addEventListener('click', function () { selectTab(i); });
        tabsEl.appendChild(b);
      });
    }

    var askedKey = 'asked-' + channelId;
    /** Signed in: the account knows whether this channel is subscribed (the local list only mirrors the recently active ones). */
    function syncSubscription(i) {
      if (!PT.auth.signedIn || PT.store.isSubscribed(i.id) || S._askedChannels[i.id]) return;
      S._askedChannels[i.id] = true;
      PT.api.get('acct/subscribed', { id: i.id }, { auth: true }).then(function (r) { if (r.subscribed) PT.store.subscribe(asItem(i)); }, PT.noop);
    }

    /** Videos on channel tabs carry no byline of their own. */
    function fill(page, i) {
      var out = { items: [], sections: page.sections, continuation: page.continuation };
      out.items = (page.items || []).map(function (it) {
        if (it.type === 'video') {
          var v = Object.assign({}, it.video);
          if (!v.channelName) v.channelName = i.name;
          if (!v.channelId) v.channelId = i.id;
          return { type: 'video', video: v };
        }
        if (it.type === 'shorts') {
          return { type: 'shorts', videos: it.videos.map(function (v) { var c = Object.assign({}, v); if (!c.channelName) c.channelName = i.name; return c; }) };
        }
        return it;
      });
      return out;
    }

    var feed = new PT.FeedView({
      refresh: false, header: headEl, endpoint: 'browse',
      fetchFirst: function () {
        feed.endpoint = 'browse';
        if (info && tabIndex < info.tabs.length && (!loadedInfo || tabIndex !== 0)) {
          var tab = info.tabs[tabIndex], i0 = info;
          return PT.api.channelTab(i0.id, tab.params).then(function (page) { return fill(page, i0); });
        }
        return PT.api.channel(channelId).then(function (i) {
          info = i; loadedInfo = true;
          scr.setTitle(i.name);
          configureHeader();
          syncSubscription(i);
          var page = Object.assign({}, i.firstPage);
          page.continuation = null;                                // the Home tab is a set of shelves; shown as a flat list
          return fill(page, i);
        });
      }
    });

    function selectTab(i) {
      if (!info || i >= info.tabs.length || i === tabIndex) return;
      tabIndex = i;
      PT.$$('.chh-tab', tabsEl).forEach(function (b, k) { b.classList.toggle('sel', k === i); });
      feed.clear();
      if (i === 0) { loadedInfo = false; info = null; }
      feed.reload();
    }

    var share = PT.iconButton('share_outline', 24, 'bar-share', PT.t('video.share'));
    share.addEventListener('click', function () { PT.share({ title: info ? info.name : name || '', url: 'https://www.youtube.com/channel/' + channelId }); });
    var scr = PT.navScreen(name || '', feed.el, { right: [share] });
    feed.reload();
    scr.scrollToTop = function (s) { feed.scrollToTop(s); };
    scr.destroy = function () { feed.destroy(); lazy.disconnect(); };
    return scr;
  };
  S._askedChannels = {};

  // ---------------------------------------------------------------------------------------------------------------
  // Playlist
  // ---------------------------------------------------------------------------------------------------------------
  S.playlist = function (playlistId, title) {
    var titleEl = h('div', { class: 'plh-title', text: title || '' });
    var metaEl = h('div', { class: 'plh-meta' });
    var playBtn = h('button', { class: 'btn-pill primary wide', type: 'button' }, h('span', { html: PT.iconSvg('play_arrow', 22) }), h('span', { text: PT.t('playlist.playAll') }));
    var shuffleBtn = h('button', { class: 'btn-pill wide', type: 'button' }, h('span', { html: PT.iconSvg('shuffle', 22) }), h('span', { text: PT.t('playlist.shuffle') }));
    var headEl = h('div', { class: 'plh' }, titleEl, metaEl, h('div', { class: 'plh-btns' }, playBtn, shuffleBtn));
    var scr;

    function adopt(info) {
      if (scr) scr.setTitle(info.title);
      titleEl.textContent = info.title;
      metaEl.textContent = [info.owner].concat(info.stats || []).filter(Boolean).join(' · ');
    }
    // lists read through the account carry no playlist id for the player: the list itself is the queue
    function queueId() { return feed.endpoint === 'tv' ? null : playlistId; }

    var feed = new PT.FeedView({
      refresh: false, header: headEl, endpoint: 'browse',
      play: function (v, fv) { PT.router.play(v, fv.allVideos(), queueId()); },
      fetchFirst: function () {
        function anonymous() {
          feed.endpoint = 'browse';
          return PT.api.playlist(playlistId).then(function (info) { adopt(info); return info.firstPage; });
        }
        // Signed in: the TV client can also read private lists (Watch later, Liked videos, own playlists).
        if (PT.auth.signedIn) {
          feed.endpoint = 'tv';
          return PT.api.get('acct/playlist', { id: playlistId }, { auth: true }).then(function (info) {
            if (info.firstPage && info.firstPage.items.length) { adopt(info); return info.firstPage; }
            return anonymous();
          }, function () { return anonymous(); });
        }
        return anonymous();
      }
    });
    function playAll(shuffle) {
      var list = feed.allVideos();
      if (!list.length) return;
      if (shuffle) { for (var i = list.length - 1; i > 0; i--) { var j = Math.floor(Math.random() * (i + 1)); var t = list[i]; list[i] = list[j]; list[j] = t; } }
      PT.router.play(list[0], list, shuffle ? null : queueId());
    }
    playBtn.addEventListener('click', function () { playAll(false); });
    shuffleBtn.addEventListener('click', function () { playAll(true); });
    var share = PT.iconButton('share_outline', 24, 'bar-share', PT.t('video.share'));
    share.addEventListener('click', function () { PT.share({ title: titleEl.textContent, url: 'https://www.youtube.com/playlist?list=' + playlistId }); });
    scr = PT.navScreen(title || '', feed.el, { right: [share] });
    feed.reload();
    scr.destroy = function () { feed.destroy(); };
    return scr;
  };

  // ---------------------------------------------------------------------------------------------------------------
  // Settings
  // ---------------------------------------------------------------------------------------------------------------
  S.settings = function () {
    var list = h('div', { class: 'settings scroll' });
    var scr = PT.navScreen(PT.t('settings.title'), list, {});
    var set = PT.settings;

    function qualityText(x) { return x === 0 ? PT.t('player.auto') : x + 'p'; }
    function languageText() { return set.uiLanguage === 'ja' ? '日本語' : set.uiLanguage === 'en' ? 'English' : PT.t('settings.languageAuto'); }
    function regionText() {
      var r = set.region(), name = r;
      set.regions.forEach(function (x) { if (x[0] === r) name = x[1]; });
      return name;
    }

    function accountRows() {
      if (PT.auth.signedIn) {
        var p = PT.auth.profile;
        return [
          { info: (p && p.name) || PT.t('account.signedIn'), detail: (p && p.handle) || '' },
          { button: PT.t('account.signOut'), destructive: true, action: function () { PT.account.signOut(); } },
          { note: PT.t('account.signedInNote') }
        ];
      }
      return [
        { button: PT.t('account.signIn'), action: function () { PT.nav.push(S.signIn()); } },
        { note: PT.t('account.signedOutNote') }
      ];
    }

    function bookmarklet() {
      var origin = location.href.replace(/[#?].*$/, '').replace(/[^\/]*$/, '');
      return "javascript:location.href='" + origin + "#/open/'+encodeURIComponent(location.href)";
    }

    function installHint() {
      if (PT.standalone) return PT.t('settings.installed');
      if (PT.isIOS) return PT.t('settings.installIOS');
      return PT.t('settings.installOther');
    }

    function sections() {
      var downloads = PT.downloads;
      return [
        { title: PT.t('settings.account'), rows: accountRows() },
        { title: PT.t('settings.general'), rows: [
          { choice: PT.t('settings.appearance'), value: set.isDark() ? PT.t('settings.dark') : PT.t('settings.light'), action: function () {
            PT.sheet.show({ title: PT.t('settings.appearance'), actions: [
              { title: PT.t('settings.dark'), checked: set.isDark(), handler: function () { set.theme = 'dark'; } },
              { title: PT.t('settings.light'), checked: !set.isDark(), handler: function () { set.theme = 'light'; } }] });
          } },
          { choice: PT.t('settings.language'), value: languageText(), action: function () {
            PT.sheet.show({ title: PT.t('settings.language'), actions: [
              { title: PT.t('settings.languageAuto'), checked: set.uiLanguage === 'auto', handler: function () { set.uiLanguage = 'auto'; } },
              { title: '日本語', checked: set.uiLanguage === 'ja', handler: function () { set.uiLanguage = 'ja'; } },
              { title: 'English', checked: set.uiLanguage === 'en', handler: function () { set.uiLanguage = 'en'; } }] });
          } },
          { choice: PT.t('settings.region'), value: regionText(), action: function () {
            PT.sheet.show({ title: PT.t('settings.region'), actions: set.regions.map(function (r) {
              return { title: r[1], checked: r[0] === set.region(), handler: function () { set.contentRegion = r[0]; } };
            }) });
          } }
        ] },
        { title: PT.t('settings.playback'), rows: [
          { toggle: PT.t('settings.autoplay'), get: function () { return set.autoplay; }, set: function (v) { set.autoplay = v; PT.emit('autoplay'); } },
          { toggle: PT.t('settings.backgroundPlay'), get: function () { return set.backgroundPlay; }, set: function (v) { set.backgroundPlay = v; } },
          { toggle: PT.t('settings.captionsAlways'), get: function () { return set.captionsAlways; }, set: function (v) { set.captionsAlways = v; } },
          { choice: PT.t('settings.defaultQuality'), value: qualityText(set.maxQuality), action: function () {
            PT.sheet.show({ title: PT.t('settings.defaultQuality'), actions: [0, 1080, 720, 480, 360, 240, 144].map(function (x) {
              return { title: qualityText(x), checked: x === set.maxQuality, handler: function () { set.maxQuality = x; PT.player.setMaxHeight(x); render(); } };
            }) });
          } },
          { choice: PT.t('settings.defaultSpeed'), value: set.playbackSpeed === 1 ? PT.t('player.normal') : set.playbackSpeed + 'x', action: function () {
            PT.sheet.show({ title: PT.t('settings.defaultSpeed'), actions: [0.5, 0.75, 1, 1.25, 1.5, 2].map(function (x) {
              return { title: x === 1 ? PT.t('player.normal') : x + 'x', checked: x === set.playbackSpeed, handler: function () { set.playbackSpeed = x; PT.player.setSpeed(x); render(); } };
            }) });
          } }
        ] },
        { title: PT.t('settings.privacy'), rows: [
          { toggle: PT.t('settings.pauseHistory'), get: function () { return set.pauseHistory; }, set: function (v) { set.pauseHistory = v; } },
          { button: PT.t('settings.clearHistory'), destructive: true, action: function () {
            PT.dialog.confirm(PT.t('library.confirmClear'), { okText: PT.t('common.delete'), destructive: true }).then(function (ok) { if (ok) PT.store.clearHistory(); });
          } },
          { button: PT.t('settings.clearSearch'), action: function () { PT.store.clearSearches(); PT.toast(PT.t('settings.clearSearch')); } },
          { button: PT.t('settings.clearCache'), action: function () { clearCaches().then(function () { PT.toast(PT.t('settings.clearCache')); }); } }
        ] },
        { title: PT.t('settings.app'), rows: [
          { info: PT.t('settings.addToHome'), detail: '' },
          { note: installHint() },
          { button: PT.t('settings.bookmarklet'), action: function () { PT.copy(bookmarklet()).then(function () { PT.toast(PT.t('settings.bookmarkletCopied')); }); } },
          { note: PT.t('settings.bookmarkletHint') },
          { button: PT.t('settings.update'), action: function () { updateApp(); } },
          downloads && downloads.supported ? { info: PT.t('settings.storage'), detail: PT.fmt.fileSize(downloads.totalBytes()) || '0 B' } : null,
          { button: PT.t('settings.forgetKey'), action: function () {
            PT.dialog.confirm(PT.t('settings.forgetKey'), { message: PT.t('settings.forgetKeyHint'), okText: PT.t('common.ok'), destructive: true }).then(function (ok) {
              if (!ok) return;
              PT.gate.setKey('');
              location.reload();
            });
          } }
        ].filter(Boolean) },
        { title: PT.t('settings.about'), rows: [
          { info: PT.t('settings.version'), detail: PT.version },
          { button: PT.t('diag.title'), action: function () { PT.nav.push(S.diagnostics()); } },
          { note: PT.t('settings.disclaimer') },
          { button: PT.t('settings.source'), action: function () { window.open('https://github.com/mizuki20070314/podtube-ios12', '_blank', 'noopener'); } }
        ] }
      ];
    }

    function clearCaches() {
      if (!window.caches) return Promise.resolve();
      return caches.keys().then(function (keys) {
        return Promise.all(keys.filter(function (k) { return /^pt-runtime/.test(k); }).map(function (k) { return caches.delete(k); }));
      });
    }

    function updateApp() {
      if (!navigator.serviceWorker) { location.reload(); return; }
      PT.toast(PT.t('common.loading'));
      navigator.serviceWorker.getRegistration().then(function (reg) {
        if (!reg) { location.reload(); return; }
        return reg.update().then(function () {
          if (reg.waiting || reg.installing) { PT.toast(PT.t('settings.updated')); setTimeout(function () { location.reload(); }, 800); }
          else PT.toast(PT.t('settings.upToDate'));
        });
      }).catch(function () { location.reload(); });
    }

    function render() {
      var top = list.scrollTop;
      PT.clear(list);
      scr.setTitle(PT.t('settings.title'));
      sections().forEach(function (sec) {
        var box = h('div', { class: 'set-section' }, h('div', { class: 'set-head', text: sec.title }));
        var group = h('div', { class: 'set-group' });
        sec.rows.forEach(function (r) {
          var row;
          if (r.toggle) {
            var sw = h('button', { class: 'switch' + (r.get() ? ' on' : ''), type: 'button', role: 'switch', 'aria-checked': r.get() ? 'true' : 'false' }, h('i'));
            sw.addEventListener('click', function () { var v = !r.get(); r.set(v); sw.classList.toggle('on', v); sw.setAttribute('aria-checked', v ? 'true' : 'false'); });
            row = h('div', { class: 'set-row' }, h('span', { class: 'set-label', text: r.toggle }), sw);
          } else if (r.choice) {
            row = h('button', { class: 'set-row choice', type: 'button' }, h('span', { class: 'set-label', text: r.choice }),
              h('span', { class: 'set-value', text: r.value }), h('span', { class: 'lr-chev', html: PT.iconSvg('chevron_right', 20) }));
            row.addEventListener('click', r.action);
          } else if (r.button) {
            row = h('button', { class: 'set-row btn' + (r.destructive ? ' destructive' : ''), type: 'button', text: r.button });
            row.addEventListener('click', r.action);
          } else if (r.note) {
            row = h('div', { class: 'set-note', text: r.note });
          } else {
            row = h('div', { class: 'set-row' }, h('span', { class: 'set-label', text: r.info }), h('span', { class: 'set-value', text: r.detail || '' }));
          }
          group.appendChild(row);
        });
        box.appendChild(group);
        list.appendChild(box);
      });
      list.scrollTop = top;
    }
    var rerender = function () { render(); };
    ['theme', 'settings', 'accountChanged', 'accountProfile', 'downloads'].forEach(function (ev) { PT.on(ev, rerender); });
    render();
    scr.destroy = function () { ['theme', 'settings', 'accountChanged', 'accountProfile', 'downloads'].forEach(function (ev) { PT.off(ev, rerender); }); };
    return scr;
  };

  // ---------------------------------------------------------------------------------------------------------------
  // Sign-in: the "limited input device" flow (the one YouTube on TV uses)
  // ---------------------------------------------------------------------------------------------------------------
  S.signIn = function () {
    var code = null, interval = 5, gen = 0, finished = false, expiresAt = 0, timer = 0;
    var qrBox = h('div', { class: 'si-qr' });
    var urlBtn = h('a', { class: 'si-url', href: 'https://www.google.com/device', target: '_blank', rel: 'noopener', text: 'google.com/device' });
    var codeEl = h('div', { class: 'si-code', text: '···-···-····' });
    var copyBtn = PT.pill('content_copy', PT.t('signin.copy'));
    var openBtn = PT.pill('open_in_new', PT.t('signin.open'));
    var status = h('div', { class: 'si-status' });
    var spin = h('div', { class: 'spinner', hidden: true });
    var retry = PT.pill('refresh', PT.t('signin.newCode'));
    retry.hidden = true;
    var body = h('div', { class: 'signin scroll' }, h('div', { class: 'si-col' },
      h('p', { class: 'si-intro', text: PT.t('signin.intro') }),
      h('div', { class: 'si-step', text: PT.t('signin.step1') }), urlBtn,
      h('div', { class: 'si-qrrow' }, qrBox, openBtn),
      h('div', { class: 'si-step', text: PT.t('signin.step2') }), codeEl, copyBtn,
      status, spin, retry,
      h('p', { class: 'si-note', text: PT.t('signin.note') })));
    var scr = PT.navScreen(PT.t('signin.title'), body, {});

    function setStatus(text, busy, showRetry) {
      status.textContent = text;
      spin.hidden = !busy;
      retry.hidden = !showRetry;
    }
    function drawQr(text) {
      PT.clear(qrBox);
      PT.loadScript('vendor/qrcode.js').then(function () {
        try {
          var qr = window.qrcode(0, 'M');
          qr.addData(text);
          qr.make();
          qrBox.innerHTML = qr.createSvgTag(4, 3);
        } catch (e) { /* no QR: the code and the link are still there */ }
      }, PT.noop);
    }
    function showCode(c) {
      code = c;
      interval = Math.max(c.interval || 5, 3);
      expiresAt = Date.now() + (c.expiresIn || 1800) * 1000;
      codeEl.textContent = c.userCode;
      urlBtn.textContent = c.verificationURL.replace('https://', '');
      urlBtn.href = c.verificationURL;
      drawQr(c.verificationURL);
      setStatus(PT.t('signin.waiting'), true, false);
    }
    function start() {
      gen++;
      var g = gen;
      code = null;
      clearTimeout(timer);
      codeEl.textContent = '···-···-····';
      setStatus(PT.t('signin.getting'), true, false);
      PT.api.post('auth/device').then(function (c) {
        if (g !== gen) return;
        showCode(c);
        schedulePoll(g);
      }, function (e) { if (g === gen) setStatus(PT.t('signin.failed') + '\n' + (e && e.message || ''), false, true); });
    }
    function schedulePoll(g) { clearTimeout(timer); timer = setTimeout(function () { poll(g, true); }, interval * 1000); }
    function poll(g, reschedule) {
      if (g !== gen || finished || !code) return;
      if (Date.now() > expiresAt) { start(); return; }
      PT.api.post('auth/poll', { deviceCode: code.deviceCode }).then(function (r) {
        if (g !== gen || finished) return;
        switch (r.status) {
          case 'ok': finish(r); break;
          case 'pending': if (reschedule) schedulePoll(g); break;
          case 'slow_down': interval += 5; if (reschedule) schedulePoll(g); break;
          case 'denied': gen++; setStatus(PT.t('signin.denied'), false, true); break;
          case 'expired': start(); break;
          default: setStatus(PT.t('signin.waiting') + '\n' + (r.message || ''), true, false); if (reschedule) schedulePoll(g);
        }
      }, function (e) {
        // transient problem (offline, 5xx): keep trying until the code expires
        if (g !== gen || finished) return;
        setStatus(PT.t('signin.waiting') + '\n' + (e && e.message || ''), true, false);
        if (reschedule) schedulePoll(g);
      });
    }
    function finish(tokens) {
      finished = true;
      gen++;
      setStatus(PT.t('signin.finishing'), true, false);
      PT.auth.adopt(tokens);
      PT.account.didSignIn();
      PT.toast(PT.t('signin.done'));
      setTimeout(function () { PT.nav.back(); }, 600);
    }
    copyBtn.addEventListener('click', function () { if (code) PT.copy(code.userCode).then(function () { PT.toast(PT.t('signin.copied')); }); });
    openBtn.addEventListener('click', function () { window.open(code ? code.verificationURL : 'https://www.google.com/device', '_blank', 'noopener'); });
    retry.addEventListener('click', function () { finished = false; start(); });
    // coming back from the other tab: do not wait for the next timer tick
    var onVis = function () { if (!document.hidden && code && !finished) poll(gen, false); };
    document.addEventListener('visibilitychange', onVis);
    start();
    scr.destroy = function () { gen++; clearTimeout(timer); document.removeEventListener('visibilitychange', onVis); };
    return scr;
  };

  // ---------------------------------------------------------------------------------------------------------------
  // Diagnostics: runs the whole playback chain once and prints what worked
  // ---------------------------------------------------------------------------------------------------------------
  S.diagnostics = function () {
    var lines = [];
    var out = h('pre', { class: 'diag-out scroll' });
    var run = h('button', { class: 'btn-pill primary wide', type: 'button', text: PT.t('diag.run') });
    var running = false;
    var scr = PT.navScreen(PT.t('diag.title'), h('div', { class: 'diag' }, out, run), {});

    function append(s) { lines.push(s); out.textContent = lines.join('\n'); out.scrollTop = out.scrollHeight; }
    function report(label, ok, ms, detail) { append((ok ? 'OK  ' : 'NG  ') + label + ' ' + ms + 'ms ' + (detail || '')); }

    append('PodTube ' + PT.version + ' (PWA)');
    append((navigator.userAgent || '').slice(0, 120));
    append('hl=' + PT.settings.hl() + ' gl=' + PT.settings.gl());
    append('');

    function capability() {
      var video = document.createElement('video');
      append('-- this browser');
      append('   engine: ' + (window.Hls && window.Hls.isSupported() && !PT.isApple ? 'hls.js (MSE)' : (video.canPlayType('application/vnd.apple.mpegurl') ? 'native HLS' : 'none')));
      append('   Picture in Picture: ' + (PT.player.pip.supported ? 'the browser offers it' : 'the browser does not offer it'));
      append('   AirPlay: ' + (PT.player.airplay.supported ? 'supported' : 'not supported'));
      append('   service worker: ' + (navigator.serviceWorker ? 'yes' : 'no') + ', Cache Storage: ' + (window.caches ? 'yes' : 'no') + ', standalone: ' + PT.standalone);
      if (navigator.storage && navigator.storage.estimate) {
        return navigator.storage.estimate().then(function (e) { append('   storage: ' + PT.fmt.fileSize(e.usage || 0) + ' of ' + PT.fmt.fileSize(e.quota || 0)); }, PT.noop);
      }
      return Promise.resolve();
    }

    /** The relay as the browser sees it: master -> media playlist -> first segment, through the public URLs. */
    function relayCheck(sid) {
      var t0 = Date.now(), base = PT.api.base + '/hls/' + sid;
      return fetch(base + '/master.m3u8?maxh=360', { credentials: 'same-origin' }).then(function (r) {
        if (!r.ok) throw new Error('master HTTP ' + r.status);
        return r.text();
      }).then(function (text) {
        var uris = text.split('\n').filter(function (l) { return l && l.charAt(0) !== '#'; });
        if (!uris.length) throw new Error('no variants');
        return fetch(uris[0], { credentials: 'same-origin' }).then(function (r) {
          if (!r.ok) throw new Error('playlist HTTP ' + r.status);
          return r.text();
        });
      }).then(function (text) {
        var segs = text.split('\n').filter(function (l) { return l && l.charAt(0) !== '#'; });
        if (!segs.length) throw new Error('no segments');
        return fetch(segs[0], { credentials: 'same-origin' }).then(function (r) {
          if (!r.ok) throw new Error('segment HTTP ' + r.status);
          return r.arrayBuffer();
        });
      }).then(function (buf) { report('HLS relay (this browser)', true, Date.now() - t0, PT.fmt.bytes(buf.byteLength)); },
        function (e) { report('HLS relay (this browser)', false, Date.now() - t0, e.message); });
    }

    run.addEventListener('click', function () {
      if (running) return;
      running = true; run.disabled = true;
      append('--- ' + new Date().toLocaleTimeString());
      capability().then(function () { return PT.api.diag(); }).then(function (r) {
        append('-- server ' + r.version);
        r.lines.forEach(function (l) { report(l.label, l.ok, l.ms, l.detail); });
        if (r.sid) return relayCheck(r.sid);
      }, function (e) { append('NG  server: ' + (e && e.message)); }).then(function () { running = false; run.disabled = false; append(''); });
    });
    return scr;
  };

  // ---------------------------------------------------------------------------------------------------------------
  // Downloads
  // ---------------------------------------------------------------------------------------------------------------
  S.downloads = function () {
    var list = h('div', { class: 'dl-list scroll' });
    var state = PT.stateView();
    var lazy = PT.lazyLoader(null);
    var scr = PT.navScreen(PT.t('library.downloads'), h('div', { class: 'dl-wrap' }, list, state.el), {});
    function render() {
      var dm = PT.downloads;
      PT.clear(list);
      var entries = [];
      Object.keys(dm.pending).forEach(function (id) { entries.push({ pending: dm.pending[id] }); });
      dm.records.forEach(function (r) { entries.push({ rec: r }); });
      if (!entries.length) { state.show('file_download', PT.t('downloads.empty')); return; }
      state.hide();
      entries.forEach(function (e) {
        var v = e.pending ? e.pending.video : e.rec.video;
        var img = PT.mkImg('thumb-img');
        lazy.set(img, PT.thumbUrl(v));
        var detail, frac = null;
        if (e.pending) { frac = dm.fraction(v.id) || 0; detail = Math.floor(frac * 100) + '% · ' + e.pending.height + 'p'; }
        else detail = e.rec.height + 'p · ' + PT.fmt.fileSize(e.rec.bytes);
        var del = PT.iconButton('delete_outline', 22, 'dl-del', PT.t('common.delete'));
        var row = h('div', { class: 'dl-row', role: 'button', tabindex: '0' }, h('div', { class: 'dl-thumb' }, img),
          h('div', { class: 'dl-txt' }, h('div', { class: 'dl-title', text: v.title }), h('div', { class: 'dl-sub', text: detail }),
            frac === null ? null : h('div', { class: 'dl-bar' }, h('i', { style: 'width:' + Math.round(frac * 100) + '%' }))), del);
        row.addEventListener('click', function () { if (e.rec) PT.router.play(v); });
        del.addEventListener('click', function (ev) {
          ev.stopPropagation();
          if (e.pending) dm.cancel(v.id); else dm.remove(v.id);
        });
        list.appendChild(row);
      });
    }
    PT.on('downloads', render);
    render();
    scr.destroy = function () { PT.off('downloads', render); lazy.disconnect(); };
    return scr;
  };
})(window.PT);
