/* Shorts: a vertical pager of full-screen clips that loop (ShortsViewController.swift).  The pager scrolls natively with
   scroll snapping; the one <video> element of this screen moves into the item that is on screen. */
(function (PT) {
  'use strict';
  var h = PT.h;

  PT.screens.shorts = function () {
    var videos = [], entries = {}, infos = {}, requested = {}, items = [];
    var current = -1, loadingSeq = false, seeded = false, seedStarted = false, gen = 0, pausedByUser = false, active = false;
    var hls = null, primed = false, timer = 0;

    var video = document.createElement('video');
    video.className = 'short-video';
    video.setAttribute('playsinline', ''); video.setAttribute('webkit-playsinline', '');
    video.setAttribute('preload', 'auto');
    video.loop = true;
    video.muted = false;

    var lazy = PT.lazyLoader(null);
    var list = h('div', { class: 'shorts-pager' });
    var state = PT.stateView();
    state.el.classList.add('dark');
    var title = h('div', { class: 'shorts-title', text: PT.t('shorts.title') });
    var search = PT.iconButton('search', 24, 'shorts-search', PT.t('search.placeholder'));
    search.addEventListener('click', function () { PT.router.openSearchScreen(); });
    var el = h('div', { class: 'screen-inner shorts' }, list, title, search, state.el);

    // -----------------------------------------------------------------------------------------------------------
    // playback of the active clip
    // -----------------------------------------------------------------------------------------------------------
    var SILENT = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=';
    function prime() {                                          // inside a user gesture (see player.js)
      if (primed) return;
      primed = true;
      try { video.src = SILENT; var p = video.play(); if (p && p.catch) p.catch(PT.noop); } catch (e) { /* ignore */ }
    }
    function destroyEngine() { if (hls) { try { hls.destroy(); } catch (e) { /* ignore */ } hls = null; } }
    function setSource(info) {
      destroyEngine();
      var url;
      if (info.hls) url = PT.api.base + '/hls/' + info.sid + '/master.m3u8?maxh=0&hl=' + encodeURIComponent(PT.settings.hl());
      else if (info.progressive) url = PT.api.base + '/hls/' + info.sid + '/prog';
      else return false;
      if (info.hls && window.Hls && window.Hls.isSupported() && !PT.isApple) {
        hls = new window.Hls({ enableWorker: true, maxBufferLength: 20, abrEwmaDefaultEstimate: 4000000 });
        hls.loadSource(url);
        hls.attachMedia(video);
      } else { video.src = url; try { video.load(); } catch (e) { /* ignore */ } }
      return true;
    }
    function playShort() {
      var p = video.play();
      if (p && p.catch) p.catch(function () { if (items[current]) items[current].setPaused(true); });
    }

    var refused = {};                       // Shorts that YouTube would not hand to the server (HTTP 429 `botcheck`)
    function loadInfo(id) {
      var i = infos[id];
      if (i && Date.now() - i.t < 3600000) return Promise.resolve(i.v);
      return PT.api.play(id).then(function (info) { infos[id] = { v: info, t: Date.now() }; delete refused[id]; return info; }, function (e) {
        if (e && e.code === 'botcheck') refused[id] = true;
        return null;
      });
    }

    function loadDetails(v) {
      if (entries[v.id] || requested[v.id]) return;
      requested[v.id] = true;
      PT.api.reelItem(v.id).then(function (entry) {
        entries[v.id] = entry;
        var i = indexOfVideo(v.id);
        if (i < 0) return;
        var m = Object.assign({}, videos[i]);
        ['title', 'channelName', 'channelId', 'channelAvatar'].forEach(function (k) { if (entry.video[k]) m[k] = entry.video[k]; });
        videos[i] = m;
        if (items[i]) items[i].configure(m, entry);
      }, PT.noop);
    }
    function indexOfVideo(id) {
      for (var i = 0; i < videos.length; i++) if (videos[i].id === id) return i;
      return -1;
    }

    function activate(index) {
      if (index < 0 || index >= videos.length || index === current) return;
      if (current >= 0 && items[current]) items[current].detach();
      current = index;
      var v = videos[index], g = gen;
      pausedByUser = false;
      video.pause();
      var it = items[index];
      it.attach(video);
      it.setLoading(true); it.setPaused(false); it.showPoster(true);
      loadDetails(v);
      loadInfo(v.id).then(function (info) {
        if (g !== gen || current !== index || !info) {
          if (current === index && !info) { it.setLoading(false); it.setNotice(!!refused[v.id], v.id); }
          return;
        }
        it.setNotice(false, v.id);
        if (!setSource(info)) { it.setLoading(false); return; }
        if (active && !pausedByUser) playShort();
        waitForFirstFrame(index, g);
      });
      if (index + 1 < videos.length) loadInfo(videos[index + 1].id);               // warm the next one
      if (index >= videos.length - 3 && videos.length) fetchSequence(videos[videos.length - 1].id);
    }

    function waitForFirstFrame(index, g) {
      var tries = 0;
      (function check() {
        if (g !== gen || current !== index) return;
        if (!video.paused && video.currentTime > 0.05 && video.readyState >= 2) {
          items[index].setLoading(false); items[index].showPoster(false);
          return;
        }
        if (tries++ < 60) setTimeout(check, 200);
        else { items[index].setLoading(false); items[index].showPoster(false); }
      })();
    }

    video.addEventListener('timeupdate', function () {
      if (current < 0 || !items[current]) return;
      var d = video.duration;
      if (isFinite(d) && d > 0) items[current].setProgress(video.currentTime / d);
    });
    video.addEventListener('playing', function () { if (current >= 0 && items[current]) { items[current].setLoading(false); items[current].setPaused(false); } });
    video.addEventListener('waiting', function () { if (current >= 0 && items[current] && video.currentTime > 0.1) items[current].setLoading(true); });
    video.addEventListener('canplay', function () { if (current >= 0 && items[current]) items[current].setLoading(false); });

    // -----------------------------------------------------------------------------------------------------------
    // items
    // -----------------------------------------------------------------------------------------------------------
    function makeItem(v, index) {
      var poster = PT.mkImg('short-poster');
      lazy.set(poster, PT.thumbUrl(v));
      var avatar = PT.mkImg('avatar');
      var chName = h('div', { class: 'sh-channel' });
      var channelObj = function () { var m = videos[index]; return m && m.channelId ? { id: m.channelId, name: m.channelName, avatar: m.channelAvatar, handle: '', subscribers: '' } : null; };
      var subBtn = PT.subscribeButton(channelObj, true);
      var titleEl = h('div', { class: 'sh-title' });
      var likeBtn = PT.iconButton('thumb_up_outline', 28, 'sh-act', PT.t('video.like'));
      var likeLabel = h('div', { class: 'sh-count' });
      var cmBtn = PT.iconButton('video_library', 28, 'sh-act', PT.t('video.comments'));
      var cmLabel = h('div', { class: 'sh-count' });
      var shareBtn = PT.iconButton('share', 28, 'sh-act', PT.t('video.share'));
      var moreBtn = PT.iconButton('more_vert', 28, 'sh-act', 'menu');
      var spinner = h('div', { class: 'spinner white sh-spinner', hidden: true });
      var pauseIcon = h('div', { class: 'sh-pause', hidden: true, html: PT.iconSvg('play_arrow', 64) });
      var progress = h('div', { class: 'sh-progress' });
      var videoSlot = h('div', { class: 'sh-videoslot' });
      // when YouTube refuses the server's IP the Short cannot play here: say so, and offer YouTube itself (this device's connection)
      var noticeLink = h('a', { class: 'sh-notice-open', target: '_blank', rel: 'noopener' });
      var noticeText = h('div', { class: 'sh-notice-text' });
      var notice = h('div', { class: 'sh-notice', hidden: true }, noticeText, noticeLink);
      var card = h('div', { class: 'short-card' }, poster, videoSlot, h('div', { class: 'sh-grad' }), pauseIcon, notice,
        h('div', { class: 'sh-actions' }, h('div', { class: 'sh-actgroup' }, likeBtn, likeLabel), h('div', { class: 'sh-actgroup' }, cmBtn, cmLabel), shareBtn, moreBtn),
        h('div', { class: 'sh-bottom' }, h('div', { class: 'sh-row' }, avatar, chName, subBtn), titleEl), spinner, progress);
      var root = h('div', { class: 'short' }, card);

      function refreshLike() {
        var m = videos[index];
        var on = m && PT.store.isLiked(m.id);
        PT.setIcon(likeBtn, on ? 'thumb_up' : 'thumb_up_outline', 28);
        likeBtn.classList.toggle('on', !!on);
      }
      var item = {
        el: root,
        configure: function (m, entry) {
          chName.textContent = m.channelName || '';
          titleEl.textContent = m.title || '';
          if (m.channelAvatar) { lazy.set(avatar, m.channelAvatar); avatar.hidden = false; } else avatar.hidden = true;
          subBtn.hidden = !m.channelId;
          if (subBtn._refresh) subBtn._refresh();
          likeLabel.textContent = entry ? entry.likes : '';
          cmLabel.textContent = entry ? entry.comments : '';
          refreshLike();
        },
        attach: function (vid) { videoSlot.appendChild(vid); },
        detach: function () { if (video.parentNode === videoSlot) videoSlot.removeChild(video); progress.style.width = '0'; pauseIcon.hidden = true; spinner.hidden = true; poster.style.visibility = ''; },
        setLoading: function (on) { spinner.hidden = !on; },
        setNotice: function (on, id) {
          notice.hidden = !on;
          if (!on) return;
          noticeText.textContent = PT.t('embed.title');
          noticeLink.textContent = PT.t('embed.openYouTube');
          noticeLink.href = 'https://www.youtube.com/shorts/' + encodeURIComponent(id);
        },
        setPaused: function (p) { pauseIcon.hidden = !p; },
        setProgress: function (f) { progress.style.width = (PT.clamp(f, 0, 1) * 100) + '%'; },
        showPoster: function (on) { poster.style.visibility = on ? '' : 'hidden'; }
      };
      item.configure(v, entries[v.id]);
      card.addEventListener('click', function (e) {
        if (e.target.closest && e.target.closest('button, a, .avatar, .sh-channel')) return;
        if (index !== current) return;
        if (!video.paused) { video.pause(); pausedByUser = true; item.setPaused(true); }
        else { pausedByUser = false; playShort(); item.setPaused(false); }
      });
      var openChannel = function () {
        var m = videos[index], e = entries[m.id];
        PT.router.openChannel((e && e.video.channelId) || m.channelId, m.channelName);
      };
      avatar.addEventListener('click', openChannel);
      chName.addEventListener('click', openChannel);
      likeBtn.addEventListener('click', function () { var m = videos[index]; PT.account.toggleLike(m); refreshLike(); });
      cmBtn.addEventListener('click', function () { PT.router.play(videos[index]); });
      shareBtn.addEventListener('click', function () { var m = videos[index]; PT.share({ title: m.title || '', url: 'https://youtube.com/shorts/' + m.id }); });
      moreBtn.addEventListener('click', function () { PT.router.showVideoMenu(videos[index]); });
      PT.on('store', refreshLike);
      return item;
    }

    function render(startIndex) {
      gen++;
      destroyEngine();
      current = -1;
      PT.clear(list);
      items = videos.map(function (v, i) { var it = makeItem(v, i); list.appendChild(it.el); return it; });
      state.hide();
      if (!videos.length) return;
      var idx = PT.clamp(startIndex || 0, 0, videos.length - 1);
      requestAnimationFrame(function () {
        list.scrollTop = idx * list.clientHeight;
        activate(idx);
      });
    }

    function appendVideos(fresh) {
      var start = videos.length;
      fresh.forEach(function (v, k) { videos.push(v); var it = makeItem(v, start + k); items.push(it); list.appendChild(it.el); });
    }

    list.addEventListener('scroll', function () {
      clearTimeout(timer);
      timer = setTimeout(function () {
        var hgt = Math.max(1, list.clientHeight);
        activate(Math.round(list.scrollTop / hgt));
      }, 110);
    }, { passive: true });

    // -----------------------------------------------------------------------------------------------------------
    // data
    // -----------------------------------------------------------------------------------------------------------
    function showError(text) {
      seedStarted = false;
      state.show('cloud_off', PT.t('common.error'), text, PT.t('common.retry'));
    }
    state.onAction = function () { seedStarted = false; seedFromHome(); };

    /** Any video id works as a seed for YouTube's Shorts sequence, so the first home-feed video is used. */
    function seedFromHome() {
      if (seedStarted) return;
      seedStarted = true;
      state.loading();
      PT.api.post('home', { seen: [], fresh: false }).then(function (page) {
        var all = [];
        (page.items || []).forEach(function (it) { if (it.type === 'video') all.push(it.video); else if (it.type === 'shorts') all = all.concat(it.videos); });
        var shorts = all.filter(function (v) { return v.isShort; });
        if (shorts.length) { videos = shorts; render(0); }
        var seed = shorts.length ? shorts[shorts.length - 1].id : (all[0] && all[0].id);
        if (seed) fetchSequence(seed);
        else if (!shorts.length) showError('');
      }, function (e) { showError(e && e.message); });
    }

    function fetchSequence(seed) {
      if (loadingSeq) return;
      loadingSeq = true;
      PT.api.reelSeq(seed).then(function (ids) {
        loadingSeq = false;
        var known = {};
        videos.forEach(function (v) { known[v.id] = true; });
        var fresh = ids.filter(function (id) { return !known[id]; }).map(function (id) { return { id: id, title: '', channelName: '', channelId: '', channelAvatar: '', thumbnail: '', duration: '', views: '', published: '', isLive: false, isUpcoming: false, isShort: true }; });
        if (!videos.length) { videos = fresh; render(0); }
        else if (fresh.length) appendVideos(fresh);
        if (!videos.length) showError('');
      }, function (e) { loadingSeq = false; if (!videos.length) showError(e && e.message); });
    }

    var screen = {
      el: el,
      scrollToTop: function (smooth) {
        if (videos.length) { try { list.scrollTo({ top: 0, behavior: smooth ? 'smooth' : 'auto' }); } catch (e) { list.scrollTop = 0; } }
      },
      onShow: function () {
        active = true;
        prime();
        PT.player.pause();
        if (!videos.length) seedFromHome();
        else if (!pausedByUser && current >= 0) playShort();
      },
      onHide: function () { active = false; video.pause(); },
      open: function (list2, startIndex) {
        seedStarted = true;
        videos = list2.slice();
        render(startIndex);
        if (list2.length) fetchSequence(list2[list2.length - 1].id);
      }
    };
    PT.shortsScreen = screen;
    document.addEventListener('visibilitychange', function () { if (document.hidden) video.pause(); });
    return screen;
  };
})(window.PT);
