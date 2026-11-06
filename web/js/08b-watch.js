/* The "now playing" surface: player, details, related videos, comments, mini player (WatchViewController.swift,
   WatchHeader.swift, Comments.swift). */
(function (PT) {
  'use strict';
  var h = PT.h;
  var MINI_H = 56;
  var MINI_VIDEO_W = Math.round(MINI_H * 16 / 9);

  // ---------------------------------------------------------------------------------------------------------------
  // the details above the related list: title, description, actions, channel, comment teaser, "up next"
  // ---------------------------------------------------------------------------------------------------------------
  function Header() {
    var self = this;
    this.video = null; this.info = null; this.channel = null;
    this.expanded = false; this.disliked = false; this.hasComments = false; this.previewComment = null;
    this.onChannel = this.onOpenComments = this.onSeek = null;

    this.titleEl = h('div', { class: 'wh-title' });
    this.metaEl = h('span', { class: 'wh-meta' });
    this.moreEl = h('span', { class: 'wh-more', text: PT.t('common.more') });
    this.desc = h('div', { class: 'wh-desc', hidden: true });
    this.metaRow = h('div', { class: 'wh-metarow' }, this.metaEl, this.moreEl);
    var toggle = function () { self.toggleExpanded(); };
    this.titleEl.addEventListener('click', toggle);
    this.metaRow.addEventListener('click', toggle);

    // like / dislike pill
    this.likeIcon = h('span', { class: 'lk-ico' });
    this.likeLabel = h('span', { class: 'lk-label', text: PT.t('video.like') });
    this.dislikeIcon = h('span', { class: 'lk-ico' });
    var likeBtn = h('button', { class: 'lk-btn like', type: 'button' }, this.likeIcon, this.likeLabel);
    var dislikeBtn = h('button', { class: 'lk-btn dislike', type: 'button', 'aria-label': PT.t('video.dislike') }, this.dislikeIcon);
    this.likePill = h('div', { class: 'likepill' }, likeBtn, h('span', { class: 'lk-div' }), dislikeBtn);
    likeBtn.addEventListener('click', function () { self.likeTapped(); });
    dislikeBtn.addEventListener('click', function () { self.dislikeTapped(); });
    this.shareBtn = PT.pill('share_outline', PT.t('video.share'), 'p-share');
    this.saveBtn = PT.pill('playlist_add', PT.t('video.save'), 'p-save');
    this.downloadBtn = PT.pill('file_download', PT.t('video.download'), 'p-download');
    this.shareBtn.addEventListener('click', function () { if (self.video) PT.router.share(self.video); });
    this.saveBtn.addEventListener('click', function () { if (self.video) PT.router.showPlaylistPicker(self.video); });
    this.downloadBtn.addEventListener('click', function () { self.downloadTapped(); });
    this.actions = h('div', { class: 'wh-actions' }, this.likePill, this.shareBtn, this.downloadBtn, this.saveBtn);

    // channel row
    this.avatar = PT.mkImg('avatar');
    this.chName = h('div', { class: 'whc-name' });
    this.chSubs = h('div', { class: 'whc-subs' });
    this.subBtn = PT.subscribeButton(function () { return self.channel; });
    this.chRow = h('div', { class: 'wh-channel', hidden: true }, this.avatar, h('div', { class: 'whc-txt' }, this.chName, this.chSubs), this.subBtn);
    this.chRow.addEventListener('click', function (e) {
      if (e.target.closest && e.target.closest('.subbtn')) return;
      if (self.video && self.video.channelId && self.onChannel) self.onChannel();
    });

    // comments teaser
    this.cmTitle = h('span', { class: 'cm-title', text: PT.t('video.comments') });
    this.cmCount = h('span', { class: 'cm-count' });
    this.cmAvatar = PT.mkImg('avatar small');
    this.cmText = h('div', { class: 'cm-text' });
    this.cmPreview = h('div', { class: 'cm-preview', hidden: true }, this.cmAvatar, this.cmText);
    this.cmCard = h('button', { class: 'wh-comments', type: 'button', hidden: true },
      h('div', { class: 'cm-head' }, this.cmTitle, this.cmCount, h('span', { class: 'cm-chev', html: PT.iconSvg('chevron_right', 22) })), this.cmPreview);
    this.cmCard.addEventListener('click', function () { if (self.onOpenComments) self.onOpenComments(); });
    this.lazy = PT.lazyLoader(null);

    // "up next" + the autoplay switch
    this.upNext = PT.upNextRow();

    this.el = h('div', { class: 'wh' }, this.titleEl, this.metaRow, this.desc, this.actions, h('div', { class: 'wh-divider' }),
      this.chRow, this.cmCard, this.upNext.el);
    PT.on('store', function () { self.refreshActions(); });
    PT.on('downloads', function () { self.refreshActions(); });
    PT.on('theme', function () { if (self.expanded) self.renderDescription(); });
    PT.on('settings', function () { self.refreshStatic(); });
  }

  Header.prototype = {
    refreshStatic: function () {
      this.moreEl.textContent = this.expanded ? PT.t('common.less') : PT.t('common.more');
      PT.setPill(this.shareBtn, 'share_outline', PT.t('video.share'));
      this.cmTitle.textContent = PT.t('video.comments');
      this.refreshActions();
    },

    /** Quick pass with the data that is already known from the list item. */
    configurePreview: function (v) {
      this.video = v; this.info = null; this.expanded = false; this.disliked = false; this.hasComments = false; this.previewComment = null;
      this.channel = v.channelId ? { id: v.channelId, name: v.channelName, avatar: v.channelAvatar, handle: '', subscribers: '' } : null;
      this.titleEl.textContent = v.title || '';
      this.titleEl.classList.remove('open');
      this.metaEl.textContent = [v.views, v.published].filter(Boolean).join(' · ');
      this.desc.hidden = true; this.desc.textContent = '';
      this.moreEl.textContent = PT.t('common.more');
      this.moreEl.hidden = false;
      this.applyChannel();
      this.refreshActions(null);
      this.cmCard.hidden = true;
      this.cmPreview.hidden = true;
      this.cmCount.textContent = '';
      this.el.scrollTop = 0;
    },

    configureInfo: function (i) {
      this.info = i;
      if (this.video && i.title) this.video = Object.assign({}, this.video, { title: i.title });
      this.titleEl.textContent = i.title || (this.video && this.video.title) || '';
      this.updateMeta();
      if (i.channel) {
        this.channel = i.channel;
        if (this.video) this.video = Object.assign({}, this.video, { channelId: i.channel.id, channelName: i.channel.name, channelAvatar: i.channel.avatar });
      }
      this.hasComments = !!i.commentsToken;
      this.cmCount.textContent = i.commentCount || '';
      this.cmCard.hidden = !this.hasComments;
      this.applyChannel();
      this.refreshActions(i.likeText);
      if (this.expanded) this.renderDescription();
    },

    updateMeta: function () {
      var i = this.info;
      if (!i) return;
      var views = this.expanded ? i.views : (i.viewsShort || i.views);
      this.metaEl.textContent = [views, i.date].filter(Boolean).join(' · ');
    },

    configureComment: function (c) {
      this.previewComment = c;
      if (c) {
        this.lazy.set(this.cmAvatar, c.avatar);
        this.cmText.textContent = c.text;
        this.cmPreview.hidden = false;
      } else { this.cmPreview.hidden = true; this.cmText.textContent = ''; }
    },

    applyChannel: function () {
      var c = this.channel;
      if (!c) { this.chRow.hidden = true; return; }
      this.chRow.hidden = false;
      this.chName.textContent = c.name || '';
      this.chSubs.textContent = c.subscribers || '';
      this.lazy.set(this.avatar, c.avatar);
      if (this.subBtn._refresh) this.subBtn._refresh();
    },

    refreshActions: function (likeText) {
      var v = this.video;
      if (!v) return;
      var liked = PT.store.isLiked(v.id);
      PT.setIcon(this.likeIcon, liked ? 'thumb_up' : 'thumb_up_outline', 20);
      PT.setIcon(this.dislikeIcon, this.disliked ? 'thumb_down' : 'thumb_down_outline', 20);
      if (typeof likeText === 'string') this.likeLabel.textContent = likeText || PT.t('video.like');
      PT.setPill(this.saveBtn, PT.store.isWatchLater(v.id) ? 'bookmark' : 'playlist_add', PT.t('video.save'));
      var dm = PT.downloads;
      this.downloadBtn.hidden = !(dm && dm.supported);
      if (dm && dm.supported) {
        if (dm.record(v.id)) PT.setPill(this.downloadBtn, 'offline_pin', PT.t('downloads.saved'));
        else if (dm.isDownloading(v.id)) PT.setPill(this.downloadBtn, 'file_download', Math.floor((dm.fraction(v.id) || 0) * 100) + '%');
        else PT.setPill(this.downloadBtn, 'file_download', PT.t('video.download'));
      }
      PT.setPill(this.shareBtn, 'share_outline', PT.t('video.share'));
    },

    expandDescription: function () { if (!this.expanded) this.toggleExpanded(); },
    toggleExpanded: function () {
      this.expanded = !this.expanded;
      this.updateMeta();
      this.moreEl.textContent = this.expanded ? PT.t('common.less') : PT.t('common.more');
      this.desc.hidden = !this.expanded;
      this.titleEl.classList.toggle('open', this.expanded);
      if (this.expanded) this.renderDescription();
    },

    renderDescription: function () {
      var text = (this.info && this.info.description) || '';
      PT.clear(this.desc);
      var self = this;
      this.desc.appendChild(PT.linkify(text, {
        seek: function (s) { PT.player.seek(s); },
        search: function (q) { PT.router.openSearch(q); }
      }));
    },

    likeTapped: function () {
      var v = this.video;
      if (!v) return;
      var was = PT.store.isLiked(v.id);
      this.disliked = false;
      PT.account.setLike(v, was ? 'none' : 'like');
      if (!was) PT.toast(PT.t('library.liked'));
      this.refreshActions();
    },
    dislikeTapped: function () {
      var v = this.video;
      if (!v) return;
      this.disliked = !this.disliked;
      if (PT.account.isSignedIn) PT.account.setLike(v, this.disliked ? 'dislike' : 'none');
      else if (this.disliked && PT.store.isLiked(v.id)) PT.store.toggleLike(v);
      this.refreshActions();
    },

    /** What the signed-in account says about this video: exact like / dislike and subscription state. */
    applyAccount: function (s) {
      var v = this.video;
      if (!v || !s) return;
      if (s.likeStatus) {
        this.disliked = s.likeStatus === 'DISLIKE';
        PT.store.setLiked(v, s.likeStatus === 'LIKE');
      }
      var c = this.channel;
      if (c && s.subscribed !== null && s.subscribed !== undefined && (!s.channelId || s.channelId === c.id)) {
        if (s.subscribed) PT.store.subscribe(c); else PT.store.unsubscribe(c.id);
      }
      this.refreshActions();
      if (this.subBtn._refresh) this.subBtn._refresh();
    },

    downloadTapped: function () {
      var v = this.video, dm = PT.downloads;
      if (!v || !dm) return;
      if (dm.record(v.id)) {
        PT.sheet.show({ title: PT.t('video.download'), actions: [{ title: PT.t('common.delete'), icon: 'delete', destructive: true, handler: function () { dm.remove(v.id); } }] });
      } else if (dm.isDownloading(v.id)) {
        PT.sheet.show({ title: PT.t('video.download'), actions: [{ title: PT.t('common.cancel'), icon: 'close', destructive: true, handler: function () { dm.cancel(v.id); } }] });
      } else PT.router.startDownload(v);
    }
  };

  /** "Up next" with the autoplay switch */
  PT.upNextRow = function () {
    var sw = h('button', { class: 'switch', type: 'button', role: 'switch' }, h('i'));
    var el = h('div', { class: 'upnext' }, h('div', { class: 'un-title', text: PT.t('video.nextUp') }),
      h('span', { class: 'un-label', text: PT.t('video.autoplay') }), sw);
    function refresh() { sw.classList.toggle('on', PT.settings.autoplay); sw.setAttribute('aria-checked', PT.settings.autoplay ? 'true' : 'false'); }
    sw.addEventListener('click', function () { PT.settings.autoplay = !PT.settings.autoplay; PT.emit('autoplay'); });
    PT.on('autoplay', refresh); PT.on('settings', function () { el.firstChild.textContent = PT.t('video.nextUp'); el.childNodes[1].textContent = PT.t('video.autoplay'); });
    refresh();
    return { el: el };
  };

  // ---------------------------------------------------------------------------------------------------------------
  // comments panel (slides over the related list)
  // ---------------------------------------------------------------------------------------------------------------
  function CommentsPanel(token, sortTokens, countText, firstPage, onClose) {
    var self = this;
    this.firstToken = token; this.sortTokens = sortTokens || []; this.currentSort = 0;
    this.comments = []; this.continuation = null; this.loading = false; this.gen = 0;
    this.title = h('span', { class: 'cp-title', text: PT.t('comments.title') });
    this.count = h('span', { class: 'cp-count', text: countText || '' });
    this.sortBtn = PT.iconButton('swap_vert', 22, 'cp-sort', 'sort');
    this.sortBtn.hidden = this.sortTokens.length < 2;
    this.closeBtn = PT.iconButton('close', 22, 'cp-close', PT.t('common.close'));
    this.list = h('div', { class: 'cp-list' });
    this.sentinel = h('div', { class: 'feed-sentinel' });
    this.state = PT.stateView();
    this.scroller = h('div', { class: 'scroll cp-scroll' }, this.list, this.sentinel);
    this.lazy = PT.lazyLoader(null);
    this.el = h('div', { class: 'cpanel' }, h('div', { class: 'cp-bar' }, this.title, this.count, h('span', { class: 'grow' }), this.sortBtn, this.closeBtn),
      this.scroller, this.state.el);
    this.closeBtn.addEventListener('click', onClose);
    this.sortBtn.addEventListener('click', function () {
      PT.sheet.show({ actions: self.sortTokens.map(function (s, i) {
        return { title: s.title, checked: i === self.currentSort, handler: function () {
          self.currentSort = i; self.comments = []; self.continuation = null; PT.clear(self.list); self.fetch(s.token);
        } };
      }) });
    });
    this.state.onAction = function () { self.loadFirst(); };
    if ('IntersectionObserver' in window) {
      this.io = new IntersectionObserver(function (es) { if (es[0].isIntersecting && self.continuation) self.fetch(self.continuation); },
        { root: null, rootMargin: '400px 0px' });
      this.io.observe(this.sentinel);
    }
    if (firstPage && firstPage.comments && firstPage.comments.length) {
      this.add(firstPage.comments);
      this.continuation = firstPage.continuation;
      this.updateSentinel();
    } else this.loadFirst();
  }
  CommentsPanel.prototype = {
    destroy: function () { if (this.io) this.io.disconnect(); this.lazy.disconnect(); this.gen++; },
    updateSentinel: function () {
      PT.clear(this.sentinel);
      if (this.continuation) this.sentinel.appendChild(h('div', { class: 'spinner' }));
    },
    loadFirst: function () {
      this.comments = []; this.continuation = null; PT.clear(this.list);
      this.fetch(this.firstToken);
    },
    add: function (list) {
      var self = this, frag = document.createDocumentFragment();
      list.forEach(function (c) {
        self.comments.push(c);
        var av = PT.mkImg('avatar');
        self.lazy.set(av, c.avatar);
        var head = c.author + (c.published ? ' · ' + c.published : '');
        var body = h('div', { class: 'cm-body' });
        body.appendChild(PT.linkify(c.text, { seek: function (s) { PT.player.seek(s); }, search: function (q) { PT.router.openSearch(q); } }));
        frag.appendChild(h('div', { class: 'comment' }, av,
          h('div', { class: 'cm-main' }, h('div', { class: 'cm-name' + (c.isOwner ? ' owner' : ''), text: head }), body,
            h('div', { class: 'cm-foot' }, h('span', { class: 'cm-like', html: PT.iconSvg('thumb_up_outline', 16) }), h('span', { text: c.likes })),
            c.replyCount > 0 ? h('div', { class: 'cm-replies', text: PT.t('comments.replies', String(c.replyCount)) }) : null)));
      });
      this.list.appendChild(frag);
    },
    fetch: function (token) {
      var self = this;
      if (this.loading) return;
      this.loading = true;
      var g = ++this.gen;
      if (!this.comments.length) this.state.loading();
      PT.api.comments(token).then(function (page) {
        if (g !== self.gen) return;
        self.loading = false;
        self.add(page.comments || []);
        self.continuation = page.continuation;
        self.updateSentinel();
        if (!self.comments.length) self.state.show('info', PT.t('comments.empty')); else self.state.hide();
      }, function (e) {
        if (g !== self.gen) return;
        self.loading = false;
        self.continuation = null;
        self.updateSentinel();
        if (!self.comments.length) self.state.show('cloud_off', PT.t('common.error'), e && e.message, PT.t('common.retry'));
      });
    }
  };

  // ---------------------------------------------------------------------------------------------------------------
  // the watch surface
  // ---------------------------------------------------------------------------------------------------------------
  var W = PT.watch = {
    isActive: false,
    progress: 0,
    dy: 0,                        // vertical offset in px while the surface slides in from / out to below the screen
    video: null, info: null, firstComments: null, playlistId: null
  };
  var root, appEl, tabbarEl, playerHost, controls, header, related, body, mainEl, sideEl, miniEl, commentsHost, upNextHeader;
  var miniTitle, miniChannel, miniPlay, miniProgress, panel = null, panelHist = null, expandHist = null;
  var cancelAnim = null, cssFullscreen = false, nativeFullscreen = false, split = false, wideHeader = false;

  W.init = function (app, tabbar) {
    appEl = app; tabbarEl = tabbar;
    root = h('div', { class: 'watch', hidden: true });
    controls = new PT.Controls();
    controls.onCollapse = function () { W.setMinimized(true, true); };
    controls.onFullscreen = function () { W.toggleFullscreen(); };
    controls.onSettings = function () { W.showSettings(); };
    controls.onCaptions = function () { W.showCaptions(); };
    PT.player.video.classList.add('pvideo');
    playerHost = h('div', { class: 'w-player' }, PT.player.video, controls.el);

    header = new Header();
    header.onChannel = function () { var v = header.video; if (v) PT.router.openChannel(v.channelId, v.channelName); };
    header.onOpenComments = function () { W.openComments(); };
    upNextHeader = PT.upNextRow();
    upNextHeader.el.classList.add('standalone');

    related = new PT.FeedView({
      refresh: false, endpoint: 'next', cls: 'related',
      scroller: h('div'),
      fetchFirst: function () { return fetchRelated(); },
      emptyTitle: '', play: function (v) { PT.router.play(v); }
    });
    body = h('div', { class: 'w-body scroll' }, header.el, related.el);
    mainEl = h('div', { class: 'w-main scroll', hidden: true });
    sideEl = h('div', { class: 'w-side scroll', hidden: true });

    miniTitle = h('div', { class: 'mini-title' });
    miniChannel = h('div', { class: 'mini-channel' });
    miniPlay = PT.iconButton('pause', 26, 'mini-play', 'play / pause');
    var miniClose = PT.iconButton('close', 24, 'mini-close', PT.t('common.close'));
    miniProgress = h('div', { class: 'mini-progress' });
    miniEl = h('div', { class: 'w-mini' }, miniProgress, h('div', { class: 'mini-txt' }, miniTitle, miniChannel), miniPlay, miniClose);
    miniPlay.addEventListener('click', function (e) { e.stopPropagation(); PT.player.toggle(); });
    miniClose.addEventListener('click', function (e) { e.stopPropagation(); W.closePlayer(); });
    commentsHost = h('div', { class: 'w-comments', hidden: true });

    root.appendChild(miniEl); root.appendChild(body); root.appendChild(mainEl); root.appendChild(sideEl);
    root.appendChild(commentsHost); root.appendChild(playerHost);
    app.appendChild(root);

    PT.on('playerItem', itemChanged);
    PT.on('player', miniState);
    PT.on('theme', function () { /* css variables handle it */ });
    setInterval(tickMini, 500);
    window.addEventListener('resize', function () { W.layout(); });
    window.addEventListener('orientationchange', function () { setTimeout(function () { W.layout(); }, 120); });
    ['fullscreenchange', 'webkitfullscreenchange'].forEach(function (ev) {
      document.addEventListener(ev, function () {
        nativeFullscreen = !!(document.fullscreenElement || document.webkitFullscreenElement);
        if (!nativeFullscreen && W.progress === 0) cssFullscreen = false;
        W.layout();
      });
    });

    // drag the player down to minimise it (and the mini player up to open it)
    var panStart = 0;
    PT.drag(root, {
      axis: 'y',
      start: function (x, y, e) {
        if (!W.isActive) return false;
        if (e.target.closest && e.target.closest('.seekbar, .filmstrip, .sheet-root')) return false;
        if (W.progress < 0.02) {
          if (W.fullscreenLayout()) return false;
          var r = root.getBoundingClientRect(), ph = playerHost.getBoundingClientRect();
          if (split && x > ph.right) return false;
          return y <= ph.bottom;
        }
        return true;
      },
      begin: function () { panStart = W.progress; if (cancelAnim) { cancelAnim(); cancelAnim = null; } },
      move: function (dx, dy) {
        var travel = Math.max(1, miniY());
        W.progress = PT.clamp(panStart + dy / travel, 0, 1);
        W.layout();
      },
      end: function (dx, dy, vx, vy) {
        var target = W.progress > 0.5 ? 1 : 0;
        if (vy > 700) target = 1; else if (vy < -700) target = 0;
        W.setMinimized(target === 1, true);
      }
    });
    root.addEventListener('click', function (e) {
      if (W.progress > 0.5 && !(e.target.closest && e.target.closest('button'))) W.setMinimized(false, true);
    });
    W.layout();
  };

  function miniY() { return appEl.clientHeight - tabbarEl.offsetHeight - MINI_H; }

  W.fullscreenLayout = function () {
    return W.progress === 0 && fullscreenWanted();
  };
  function phoneLandscape() {
    var vw = appEl.clientWidth, vh = appEl.clientHeight;
    return PT.hasTouch && Math.min(vw, vh) < 600 && vw > vh;
  }
  function fullscreenWanted() { return nativeFullscreen || cssFullscreen || phoneLandscape(); }

  // geometry ------------------------------------------------------------------------------------------------------
  W.layout = function () {
    if (!root || !appEl) return;
    var vw = appEl.clientWidth, vh = appEl.clientHeight;
    var fs = W.progress === 0 && fullscreenWanted();
    var rot = fs && cssFullscreen && !nativeFullscreen && vh > vw;
    PT.view.rot = rot;
    var Wd = rot ? vh : vw, Hs = rot ? vw : vh;
    var p = W.progress;
    var tabH = tabbarEl.offsetHeight;
    var my = vh - tabH - MINI_H;
    var wasSplit = split;
    split = !fs && Wd >= 900 && Wd > Hs;
    var pw = split ? Math.floor(Wd * 0.6875) : Wd;
    var y = rot ? 0 : PT.lerp(0, my, p), hh = rot ? Hs : PT.lerp(Hs, MINI_H, p);
    var s = root.style;
    s.left = '0'; s.top = (y + W.dy) + 'px'; s.width = Wd + 'px'; s.height = hh + 'px';
    s.transformOrigin = '0 0';
    s.transform = rot ? 'translate3d(' + vw + 'px,0,0) rotate(90deg)' : '';
    root.classList.toggle('fs', fs);
    root.classList.toggle('split', split);
    wideHeader = Wd >= 600;
    header.el.classList.toggle('wide', wideHeader);

    var px, py, pwid, phei;
    if (p === 0 && fs) { px = 0; py = 0; pwid = Wd; phei = hh; }
    else {
      var exH = Math.round(pw * 9 / 16);
      px = PT.lerp(0, 0, p); py = PT.lerp(0, 0, p);
      pwid = PT.lerp(pw, MINI_VIDEO_W, p); phei = PT.lerp(exH, MINI_H, p);
    }
    var ps = playerHost.style;
    ps.left = px + 'px'; ps.top = py + 'px'; ps.width = pwid + 'px'; ps.height = phei + 'px';
    var contentTop = py + phei;
    var alpha = Math.max(0, 1 - p * 3);
    var visible = alpha > 0.01 ? 'visible' : 'hidden';

    if (split !== wasSplit) arrange();
    var bs = body.style;
    if (split) {
      bs.display = 'none';
      mainEl.hidden = false; sideEl.hidden = false;
      var ms = mainEl.style; ms.left = '0'; ms.top = contentTop + 'px'; ms.width = pw + 'px'; ms.height = Math.max(0, hh - contentTop) + 'px';
      ms.opacity = alpha; ms.visibility = visible;
      var paneTop = PT.lerp(0, hh, p);
      var ss = sideEl.style; ss.left = pw + 'px'; ss.top = paneTop + 'px'; ss.width = (Wd - pw) + 'px'; ss.height = Math.max(0, hh - paneTop) + 'px';
      ss.opacity = alpha; ss.visibility = visible;
      commentsHost.style.left = pw + 'px'; commentsHost.style.top = paneTop + 'px';
      commentsHost.style.width = (Wd - pw) + 'px'; commentsHost.style.height = Math.max(0, hh - paneTop) + 'px';
    } else {
      mainEl.hidden = true; sideEl.hidden = true;
      bs.display = '';
      bs.left = '0'; bs.top = contentTop + 'px'; bs.width = Wd + 'px'; bs.height = Math.max(0, hh - contentTop) + 'px';
      bs.opacity = alpha; bs.visibility = visible;
      commentsHost.style.left = '0'; commentsHost.style.top = contentTop + 'px';
      commentsHost.style.width = Wd + 'px'; commentsHost.style.height = Math.max(0, hh - contentTop) + 'px';
    }
    commentsHost.style.opacity = alpha;
    commentsHost.style.visibility = visible;
    var cs = controls.el.style;
    cs.opacity = String(Math.max(0, 1 - p * 4));
    cs.pointerEvents = p < 0.05 ? '' : 'none';
    controls.setFullscreen(p === 0 && fs);
    miniEl.style.width = Wd + 'px';
    miniEl.style.opacity = String(PT.clamp((p - 0.5) * 2, 0, 1));
    miniEl.style.pointerEvents = p > 0.5 ? '' : 'none';
    root.classList.toggle('minimized', p > 0.5);
    controls.layoutScrub();
  };

  /** Where the details and the related list sit: one column, or (wide screens held sideways) two panes. */
  function arrange() {
    if (split) {
      mainEl.appendChild(header.el);
      PT.clear(sideEl);
      sideEl.appendChild(upNextHeader.el);
      sideEl.appendChild(related.el);
      header.upNext.el.hidden = true;
    } else {
      PT.clear(body);
      body.appendChild(header.el);
      body.appendChild(related.el);
      header.upNext.el.hidden = false;
    }
  }

  function animateTo(target, ms, then) {
    if (cancelAnim) cancelAnim();
    var from = W.progress;
    cancelAnim = PT.tween(from, target, ms, PT.ease.inOut, function (v) { W.progress = v; W.layout(); }, function () {
      cancelAnim = null; W.progress = target; W.layout(); if (then) then(); emitMini();
    });
  }

  function emitMini() { PT.emit('mini'); }

  // presentation --------------------------------------------------------------------------------------------------
  W.start = function (v, queue, playlistId) {
    if (PT.player.pip.active) PT.player.pip.toggle();     // a new video goes to the inline player, not to a PiP window of the old one
    var was = W.isActive;
    W.isActive = true;
    root.hidden = false;
    hideComments(false);
    PT.subtitles.clear();
    configureMini(v);
    loadContent(v, playlistId);
    PT.player.play(v, queue, playlistId);
    if (!was) {                                                            // slides in from below the screen
      if (cancelAnim) cancelAnim();
      W.progress = 0; W.dy = appEl.clientHeight; W.layout();
      cancelAnim = PT.tween(W.dy, 0, 300, PT.ease.out, function (v) { W.dy = v; W.layout(); }, function () {
        cancelAnim = null; W.dy = 0; W.layout(); emitMini();
      });
    } else if (W.progress > 0.001) animateTo(0, 280);
    else { W.layout(); emitMini(); }
    if (!expandHist) expandHist = PT.hist.push(function (fromPop) { expandHist = null; W.backPressed(); });
  };

  W.setMinimized = function (min, animated, fromHistory) {
    if (!W.isActive) return;
    if (min && W.fullscreenLayout()) W.exitFullscreen();
    if (min && panel) hideComments(true);
    if (min && expandHist && !fromHistory) { var e = expandHist; expandHist = null; PT.hist.release(e); }
    if (!min && !expandHist) expandHist = PT.hist.push(function () { expandHist = null; W.setMinimized(true, true, true); });
    if (fromHistory) expandHist = null;
    var target = min ? 1 : 0;
    if (animated === false) { W.progress = target; W.layout(); emitMini(); return; }
    animateTo(target, 280);
  };

  /** The browser's back button: close the comments panel first, then minimise. */
  W.backPressed = function () {
    if (panel) { hideComments(true, true); expandHist = PT.hist.push(function () { expandHist = null; W.backPressed(); }); return; }
    W.setMinimized(true, true, true);
  };

  W.closePlayer = function () {
    if (PT.player.pip.active) PT.player.pip.toggle();
    PT.player.stop();
    PT.subtitles.clear();
    hideComments(false);
    W.exitFullscreen();
    if (expandHist) { var e = expandHist; expandHist = null; PT.hist.release(e); }
    W.isActive = false;
    if (cancelAnim) cancelAnim();
    cancelAnim = PT.tween(W.dy, MINI_H + 90, 220, PT.ease.in, function (v) { W.dy = v; W.layout(); }, function () {
      cancelAnim = null; root.hidden = true; W.progress = 0; W.dy = 0; W.layout(); emitMini();
    });
  };

  // fullscreen ----------------------------------------------------------------------------------------------------
  W.toggleFullscreen = function () {
    if (W.fullscreenLayout()) { W.exitFullscreen(); return; }
    var el = root, req = el.requestFullscreen || el.webkitRequestFullscreen || el.mozRequestFullScreen;
    var iphone = /iPhone|iPod/.test(navigator.userAgent);
    if (req && !iphone && (document.fullscreenEnabled || document.webkitFullscreenEnabled)) {
      try {
        var r = req.call(el);
        if (r && r.catch) r.catch(function () { cssFullscreen = true; W.layout(); });
        if (screen.orientation && screen.orientation.lock) screen.orientation.lock('landscape').catch(PT.noop);
      } catch (e) { cssFullscreen = true; }
    } else cssFullscreen = true;
    W.layout();
  };
  W.exitFullscreen = function () {
    cssFullscreen = false;
    if (document.fullscreenElement || document.webkitFullscreenElement) {
      try { (document.exitFullscreen || document.webkitExitFullscreen).call(document); } catch (e) { /* ignore */ }
      try { if (screen.orientation && screen.orientation.unlock) screen.orientation.unlock(); } catch (e) { /* ignore */ }
    }
    nativeFullscreen = false;
    W.layout();
  };

  // mini player ---------------------------------------------------------------------------------------------------
  function configureMini(v) {
    miniTitle.textContent = v.title || '';
    miniChannel.textContent = v.channelName || '';
    miniState();
  }
  function miniState() {
    var st = PT.player.state;
    PT.setIcon(miniPlay, st === 'playing' || st === 'buffering' ? 'pause' : 'play_arrow', 26);
  }
  function tickMini() {
    if (!W.isActive || W.progress < 0.5) return;
    var P = PT.player, d = P.duration, f = d > 0 ? P.currentTime / d : 0;
    miniProgress.style.width = (PT.clamp(f, 0, 1) * 100) + '%';
  }
  W.miniInset = function () { return W.isActive && W.progress > 0.5 ? MINI_H : 0; };

  // content -------------------------------------------------------------------------------------------------------
  function loadContent(v, playlistId) {
    W.video = v; W.playlistId = playlistId || null; W.info = null; W.firstComments = null;
    related.clear();
    body.scrollTop = 0; mainEl.scrollTop = 0; sideEl.scrollTop = 0;
    header.configurePreview(v);
    related.reload();
  }

  function fetchRelated() {
    var v = W.video;
    if (!v) return Promise.resolve({ items: [] });
    related.endpoint = 'next';
    var vid = v.id;
    return PT.api.watch(vid, W.playlistId).then(function (w) {
      if (!W.video || W.video.id !== vid) return { items: [] };
      applyInfo(w);
      var page = w.related;
      if (w.queue && w.queue.length) {
        var after = w.queue.slice(w.queueIndex + 1).map(function (x) { return { type: 'video', video: x }; });
        page = { items: after.concat(page.items), sections: page.sections, continuation: page.continuation };
      }
      return page;
    });
  }

  function applyInfo(w) {
    W.info = w;
    header.configureInfo(w);
    var merged = header.video;
    if (merged) {
      configureMini(merged);
      PT.player.updateMetadata(merged);
      PT.store.updateHistoryVideo(merged);
      PT.channelDirectory.learnVideo(merged);
    }
    var next = [];
    if (w.autoplay) next.push(w.autoplay);
    (w.related.items || []).forEach(function (it) { if (it.type === 'video') next.push(it.video); });
    PT.player.upNext = next;
    PT.player.chapters = PT.chapters.parse(w.description);
    if (w.queue && w.queue.length) PT.player.adoptQueue(w.queue, w.videoId, W.playlistId);
    if (w.commentsToken) {
      PT.api.comments(w.commentsToken).then(function (page) {
        if (!W.video || W.video.id !== w.videoId) return;
        W.firstComments = page;
        header.configureComment(page.comments[0] || null);
      }, PT.noop);
    }
    var v = W.video;
    if (v) PT.account.loadWatchState(v).then(function (s) { if (s && W.video && W.video.id === v.id) header.applyAccount(s); });
  }

  /** The player moved on by itself (autoplay / queue): follow it. */
  function itemChanged() {
    var P = PT.player;
    if (P.current && W.isActive && (!W.video || P.current.id !== W.video.id)) {
      configureMini(P.current);
      loadContent(P.current, P.playlistId);
      hideComments(false);
    }
  }

  // comments ------------------------------------------------------------------------------------------------------
  W.openComments = function () {
    var info = W.info;
    if (!info || !info.commentsToken) return;
    hideComments(false);
    panel = new CommentsPanel(info.commentsToken, info.commentSortTokens, info.commentCount, W.firstComments, function () { hideComments(true); });
    commentsHost.appendChild(panel.el);
    commentsHost.hidden = false;
    commentsHost.style.transition = 'none';
    commentsHost.style.transform = 'translate3d(0,100%,0)';
    void commentsHost.offsetHeight;
    commentsHost.style.transition = 'transform .25s cubic-bezier(.2,.8,.2,1)';
    commentsHost.style.transform = 'translate3d(0,0,0)';
    panelHist = PT.hist.push(function () { panelHist = null; hideComments(true, true); });
  };

  function hideComments(animated, fromHistory) {
    if (!panel) return;
    var p = panel; panel = null;
    if (panelHist && !fromHistory) { var e = panelHist; panelHist = null; PT.hist.release(e); }
    if (fromHistory) panelHist = null;
    var finish = function () { p.destroy(); PT.remove(p.el); commentsHost.hidden = true; commentsHost.style.transform = ''; commentsHost.style.transition = ''; };
    if (animated) {
      commentsHost.style.transition = 'transform .22s ease-in';
      commentsHost.style.transform = 'translate3d(0,100%,0)';
      setTimeout(finish, 230);
    } else finish();
  }

  // player menus --------------------------------------------------------------------------------------------------
  function qualityLabel(hgt) { return hgt === 0 ? PT.t('player.auto') : hgt + 'p'; }

  W.showSettings = function () {
    var P = PT.player;
    var acts = [
      { title: PT.t('player.quality'), icon: 'hd', subtitle: qualityLabel(P.maxHeight), handler: W.showQuality },
      { title: PT.t('player.speed'), icon: 'speed', subtitle: P.speed === 1 ? PT.t('player.normal') : P.speed + 'x', handler: W.showSpeed },
      { title: PT.t('player.captions'), icon: 'closed_caption', subtitle: PT.subtitles.current ? PT.subtitles.current.name : PT.t('player.captionsOff'), handler: W.showCaptions },
      { title: PT.t('player.loop'), icon: 'repeat', checked: P.loops, handler: function () { P.loops = !P.loops; PT.emit('player'); } },
      { title: PT.t('player.sleep'), icon: 'timer', subtitle: (P.sleepEndsAt || P.sleepAtEnd) ? '●' : PT.t('player.sleepOff'), handler: W.showSleep }
    ];
    var audio = P.audioOptions();
    if (audio.length > 1) {
      var sel = audio.filter(function (o) { return o.isSelected; })[0];
      acts.splice(3, 0, { title: PT.t('player.audio'), icon: 'audiotrack', subtitle: sel ? sel.title : null, handler: W.showAudioTracks });
    }
    acts.push({ title: PT.t('player.stats'), icon: 'analytics', checked: P.showsStats, handler: function () { P.showsStats = !P.showsStats; controls.refreshStats(); PT.emit('player'); } });
    if (P.chapters.length >= 2) {
      var cur = PT.chapters.current(P.chapters, P.currentTime);
      acts.unshift({ title: PT.t('player.chapters'), icon: 'format_list_bulleted', subtitle: cur ? cur.title : null, handler: W.showChapters });
    }
    PT.sheet.show({ title: PT.t('player.settings'), actions: acts });
  };

  W.showChapters = function () {
    var P = PT.player, now = PT.chapters.current(P.chapters, P.currentTime);
    PT.sheet.show({ title: PT.t('player.chapters'), actions: P.chapters.map(function (c) {
      return { title: c.title, subtitle: PT.fmt.duration(c.start), checked: !!now && c.start === now.start, handler: function () { P.seek(c.start); } };
    }) });
  };

  /** Only offered when the video has several audio tracks. "Automatic" follows the language of the viewer. */
  W.showAudioTracks = function () {
    var P = PT.player, auto = !PT.settings.preferredAudio;
    var acts = [{ title: PT.t('player.audioAuto'), checked: auto, handler: function () { P.selectAutomaticAudio(); } }];
    P.audioOptions().forEach(function (o) {
      acts.push({ title: o.title, checked: !auto && o.isSelected, handler: function () { P.selectAudio(o); } });
    });
    PT.sheet.show({ title: PT.t('player.audio'), actions: acts });
  };

  W.showQuality = function () {
    var P = PT.player;
    var options = [0, 1080, 720, 480, 360, 240, 144];
    var m = P.info && P.info.maxHeight;
    if (m > 0) options = options.filter(function (x) { return x === 0 || x <= Math.max(m, 144); });
    PT.sheet.show({ title: PT.t('player.quality'), actions: options.map(function (x) {
      return { title: qualityLabel(x), checked: x === P.maxHeight, handler: function () { P.setMaxHeight(x); } };
    }) });
  };

  W.showSpeed = function () {
    var P = PT.player;
    PT.sheet.show({ title: PT.t('player.speed'), actions: [0.25, 0.5, 0.75, 1, 1.25, 1.5, 1.75, 2].map(function (s) {
      return { title: s === 1 ? PT.t('player.normal') : s + 'x', checked: s === P.speed, handler: function () { P.setSpeed(s); } };
    }) });
  };

  W.showCaptions = function () {
    var S = PT.subtitles;
    var acts = [{ title: PT.t('player.captionsOff'), checked: !S.isEnabled, handler: function () { S.disable(); } }];
    S.tracks.forEach(function (t) {
      acts.push({ title: t.name, checked: !!S.current && S.current.i === t.i, handler: function () { S.select(t); } });
    });
    PT.sheet.show({ title: PT.t('player.captions'), actions: acts });
  };

  W.showSleep = function () {
    var P = PT.player;
    var acts = [{ title: PT.t('player.sleepOff'), handler: function () { P.setSleepTimer(null); } }];
    [10, 15, 30, 45, 60].forEach(function (m) { acts.push({ title: PT.t('player.sleepMinutes', String(m)), handler: function () { P.setSleepTimer(m); } }); });
    acts.push({ title: PT.t('player.sleepEnd'), handler: function () { P.setSleepTimer(null, true); } });
    PT.sheet.show({ title: PT.t('player.sleep'), actions: acts });
  };

  W.controls = function () { return controls; };
  /** For tests: the CSS full screen that turns the player on its side on a phone held upright. */
  W.debugCssFullscreen = function (on) { cssFullscreen = on; nativeFullscreen = false; W.layout(); };
})(window.PT);
