/* UI building blocks: toast, bottom sheet, dialogs, lazy images, cards, chips, the paginated feed (Components.swift, Grid.swift,
   FeedViewController.swift). */
(function (PT) {
  'use strict';
  var h = PT.h;

  // ---------------------------------------------------------------------------------------------------------------
  // toast
  // ---------------------------------------------------------------------------------------------------------------
  var toastEl = null, toastTimer = 0;
  PT.toast = function (text) {
    if (!toastEl) { toastEl = h('div', { class: 'toast', role: 'status' }); document.body.appendChild(toastEl); }
    toastEl.textContent = text;
    toastEl.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toastEl.classList.remove('show'); }, 2300);
  };

  // ---------------------------------------------------------------------------------------------------------------
  // Material-style modal bottom sheet.  actions: [{title, icon, subtitle, checked, destructive, handler}]
  // ---------------------------------------------------------------------------------------------------------------
  PT.sheet = {
    show: function (o) {
      o = o || {};
      var actions = o.actions || [];
      var closed = false, entry = null;
      var dim = h('div', { class: 'sheet-dim' });
      var panel = h('div', { class: 'sheet-panel', role: 'dialog' });
      var root = h('div', { class: 'sheet-root' }, dim, panel);
      if (o.title) panel.appendChild(h('div', { class: 'sheet-title', text: o.title }));
      var list = h('div', { class: 'sheet-list' });
      panel.appendChild(list);
      actions.forEach(function (a) {
        var row = h('button', { class: 'sheet-row' + (a.destructive ? ' destructive' : ''), type: 'button' });
        if (a.icon) row.appendChild(h('span', { class: 'sheet-ico', html: PT.iconSvg(a.icon, 24) }));
        else row.classList.add('noicon');
        var txt = h('span', { class: 'sheet-txt' }, h('span', { class: 't', text: a.title }));
        if (a.subtitle) txt.appendChild(h('span', { class: 's', text: a.subtitle }));
        row.appendChild(txt);
        if (a.checked) row.appendChild(h('span', { class: 'sheet-chk', html: PT.iconSvg('check', 22) }));
        row.addEventListener('click', function () { close(false, a.handler); });
        list.appendChild(row);
      });
      document.body.appendChild(root);
      // slide in
      panel.style.transform = 'translate3d(0,100%,0)';
      dim.style.opacity = '0';
      void panel.offsetHeight;
      panel.style.transition = 'transform .26s cubic-bezier(.2,.8,.2,1)';
      dim.style.transition = 'opacity .26s';
      panel.style.transform = 'translate3d(0,0,0)';
      dim.style.opacity = '1';

      function close(fromHistory, then) {
        if (closed) return;
        closed = true;
        if (!fromHistory) PT.hist.release(entry);
        panel.style.transition = 'transform .2s ease-in';
        dim.style.transition = 'opacity .2s';
        panel.style.transform = 'translate3d(0,100%,0)';
        dim.style.opacity = '0';
        setTimeout(function () { PT.remove(root); if (then) then(); }, 200);
      }
      entry = PT.hist.push(function (fromPop) { close(fromPop, null); });
      dim.addEventListener('click', function () { close(false, null); });
      // A list that has a selection (chapters, audio tracks, captions ...) opens with the selected row in view: with 60 chapters the
      // one that is playing would otherwise be somewhere far below.
      if (o.reveal) {
        var cur = list.querySelector('.sheet-chk');
        if (cur) {
          var row = cur.parentNode, rr = row.getBoundingClientRect(), lr = list.getBoundingClientRect();
          list.scrollTop = Math.max(0, list.scrollTop + (rr.top - lr.top) - Math.round((lr.height - rr.height) / 2));
        }
      }
      // drag down to dismiss.  It takes over only for a pull DOWN that starts at the top of the list: a swipe UP there is the list
      // scrolling, and a handler that preventDefault()s every vertical move would make a long list impossible to scroll by touch.
      PT.drag(panel, {
        axis: 'y',
        // (from the title bar the pull works whatever the list is showing)
        start: function (x, y, e) { return list.scrollTop <= 0 || !(e && e.target && list.contains(e.target)); },
        begin: function (dx, dy) { return dy > 0; },
        move: function (dx, dy) {
          var d = Math.max(0, dy);
          panel.style.transition = 'none';
          panel.style.transform = 'translate3d(0,' + d + 'px,0)';
          dim.style.opacity = String(Math.max(0, 1 - d / Math.max(1, panel.offsetHeight)));
        },
        end: function (dx, dy, vx, vy) {
          if (dy > panel.offsetHeight * 0.35 || vy > 900) close(false, null);
          else {
            panel.style.transition = 'transform .2s'; dim.style.transition = 'opacity .2s';
            panel.style.transform = 'translate3d(0,0,0)'; dim.style.opacity = '1';
          }
        }
      });
      return { close: function () { close(false, null); } };
    }
  };

  // ---------------------------------------------------------------------------------------------------------------
  // dialogs (instead of the browser's alert / confirm / prompt)
  // ---------------------------------------------------------------------------------------------------------------
  function dialog(title, o) {
    return new Promise(function (resolve) {
      o = o || {};
      var input = o.input ? h('input', { class: 'dlg-input', type: 'text', placeholder: o.placeholder || '', autocapitalize: 'none' }) : null;
      var ok = h('button', { class: 'dlg-btn' + (o.destructive ? ' destructive' : ''), type: 'button', text: o.okText || PT.t('common.ok') });
      var cancel = h('button', { class: 'dlg-btn', type: 'button', text: PT.t('common.cancel') });
      var box = h('div', { class: 'dlg-root' }, h('div', { class: 'dlg-dim' }),
        h('div', { class: 'dlg', role: 'alertdialog' }, h('div', { class: 'dlg-title', text: title }),
          o.message ? h('div', { class: 'dlg-msg', text: o.message }) : null, input,
          h('div', { class: 'dlg-actions' }, cancel, ok)));
      var done = false;
      function finish(v) {
        if (done) return;
        done = true;
        PT.remove(box);
        resolve(v);
      }
      ok.addEventListener('click', function () { finish(input ? input.value : true); });
      cancel.addEventListener('click', function () { finish(input ? null : false); });
      if (input) input.addEventListener('keydown', function (e) { if (e.keyCode === 13) finish(input.value); });
      document.body.appendChild(box);
      if (input) setTimeout(function () { input.focus(); }, 50);
    });
  }
  PT.dialog = {
    confirm: function (title, o) { return dialog(title, o); },
    prompt: function (title, o) { o = o || {}; o.input = true; return dialog(title, o); }
  };

  // ---------------------------------------------------------------------------------------------------------------
  // lazy images
  // ---------------------------------------------------------------------------------------------------------------
  /** A loader that fetches the images of `root` shortly before they scroll into view. */
  PT.lazyLoader = function (root) {
    var io = null;
    if ('IntersectionObserver' in window) {
      io = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) {
          if (en.isIntersecting) { io.unobserve(en.target); load(en.target); }
        });
      }, { root: root, rootMargin: '700px 0px 700px 0px' });
    }
    function load(img) {
      var u = img.getAttribute('data-src');
      if (u) { img.removeAttribute('data-src'); img.src = u; }
    }
    return {
      /** Starts loading `url` into `img` when it gets near the screen. */
      set: function (img, url) {
        img.removeAttribute('src');
        if (!url) { img.removeAttribute('data-src'); img.classList.remove('loaded'); return; }
        img.classList.remove('loaded');
        img.setAttribute('data-src', url);
        if (io) io.observe(img); else load(img);
      },
      disconnect: function () { if (io) io.disconnect(); }
    };
  };

  function mkImg(cls) {
    var img = h('img', { class: cls, alt: '', draggable: 'false', referrerpolicy: 'no-referrer', decoding: 'async' });
    img.addEventListener('load', function () { img.classList.add('loaded'); });
    return img;
  }
  PT.mkImg = mkImg;

  // ---------------------------------------------------------------------------------------------------------------
  // buttons
  // ---------------------------------------------------------------------------------------------------------------
  PT.iconButton = function (icon, size, cls, label) {
    var b = h('button', { class: 'ibtn ' + (cls || ''), type: 'button', 'aria-label': label || icon });
    PT.setIcon(b, icon, size || 24);
    return b;
  };

  PT.pill = function (icon, title, cls) {
    var b = h('button', { class: 'pill ' + (cls || ''), type: 'button' });
    PT.setPill(b, icon, title);
    return b;
  };
  PT.setPill = function (b, icon, title) {
    b.innerHTML = '';
    if (icon) b.appendChild(h('span', { class: 'pill-ico', html: PT.iconSvg(icon, 20) }));
    if (title) b.appendChild(h('span', { class: 'pill-txt', text: title }));
  };

  /** The channel subscribe button (white pill / grey "subscribed"), in sync with the store. */
  PT.subscribeButton = function (getChannel, small) {
    var b = h('button', { class: 'subbtn' + (small ? ' small' : ''), type: 'button' });
    function refresh() {
      var c = getChannel();
      var on = !!c && PT.store.isSubscribed(c.id);
      b.classList.toggle('on', on);
      b.textContent = on ? PT.t('video.subscribed') : (small ? PT.t('video.subscribe') : PT.t('video.subscribe'));
    }
    b.addEventListener('click', function (e) {
      e.stopPropagation();
      var c = getChannel();
      if (c && c.id) { PT.account.toggleSubscribe(c); refresh(); }
    });
    b._refresh = refresh;
    PT.on('store', refresh); PT.on('settings', refresh);
    refresh();
    return b;
  };

  // ---------------------------------------------------------------------------------------------------------------
  // loading / error / empty state
  // ---------------------------------------------------------------------------------------------------------------
  PT.stateView = function () {
    var box = h('div', { class: 'state', hidden: true });
    var api = {
      el: box, onAction: null,
      loading: function () {
        box.hidden = false;
        box.innerHTML = '<div class="spinner big"></div>';
      },
      show: function (icon, title, detail, button) {
        box.hidden = false;
        box.innerHTML = '';
        if (icon) box.appendChild(h('div', { class: 'state-ico', html: PT.iconSvg(icon, 56) }));
        box.appendChild(h('div', { class: 'state-title', text: title }));
        if (detail) box.appendChild(h('div', { class: 'state-detail', text: detail }));
        if (button) {
          var b = h('button', { class: 'btn-pill primary', type: 'button', text: button });
          b.addEventListener('click', function () { if (api.onAction) api.onAction(); });
          box.appendChild(b);
        }
      },
      hide: function () { box.hidden = true; box.innerHTML = ''; }
    };
    return api;
  };

  PT.spinnerRow = function () { return h('div', { class: 'loadrow' }, h('div', { class: 'spinner' })); };

  // ---------------------------------------------------------------------------------------------------------------
  // chip bar
  // ---------------------------------------------------------------------------------------------------------------
  PT.chipBar = function (onSelect) {
    var scroll = h('div', { class: 'chips-scroll' });
    var el = h('div', { class: 'chips' }, scroll);
    var buttons = [], sel = 0;
    var api = {
      el: el,
      set: function (titles, selected) {
        PT.clear(scroll);
        buttons = titles.map(function (t, i) {
          var b = h('button', { class: 'chip', type: 'button', text: t });
          b.addEventListener('click', function () { if (i === sel) return; sel = i; restyle(); onSelect(i); });
          scroll.appendChild(b);
          return b;
        });
        sel = selected || 0;
        restyle();
      },
      get selected() { return sel; }
    };
    function restyle() { buttons.forEach(function (b, i) { b.classList.toggle('sel', i === sel); }); }
    return api;
  };

  // ---------------------------------------------------------------------------------------------------------------
  // cards
  // ---------------------------------------------------------------------------------------------------------------
  function videoMeta(v) {
    var p = [];
    if (v.channelName) p.push(v.channelName);
    if (v.views) p.push(v.views);
    if (v.published) p.push(v.published);
    return p.join(' · ');
  }
  PT.videoMeta = videoMeta;

  function thumbUrl(v) {
    return v.thumbnail || ('https://i.ytimg.com/vi/' + v.id + '/mqdefault.jpg');
  }
  PT.thumbUrl = thumbUrl;

  function progressOf(v) {
    if (typeof v.watchedPercent === 'number') return v.watchedPercent / 100;
    var p = PT.store.progress(v.id);
    return p === null ? 0 : p;
  }

  function badge(v) {
    if (v.isLive) return { text: PT.t('video.live'), cls: 'live' };
    if (v.isUpcoming) return { text: PT.t('video.upcoming'), cls: '' };
    return { text: v.duration || '', cls: '' };
  }

  PT.cards = {
    /** ctx: {lazy, avatars, play(v), more(v), avatar(v)} */
    video: function (v0, ctx) {
      var v = ctx.avatars ? PT.channelDirectory.filled(v0) : v0;
      if (ctx.avatars && !v.channelAvatar) PT.channelDirectory.resolve(v);
      var thumb = mkImg('thumb-img');
      ctx.lazy.set(thumb, thumbUrl(v));
      thumb.addEventListener('error', function onerr() {
        thumb.removeEventListener('error', onerr);
        thumb.src = 'https://i.ytimg.com/vi/' + v.id + '/mqdefault.jpg';
      });
      var b = badge(v);
      var dur = h('span', { class: 'dur ' + b.cls, text: b.text, hidden: !b.text });
      var frac = progressOf(v);
      var prog = h('i', { class: 'prog', style: 'width:' + Math.round(frac * 100) + '%', hidden: frac <= 0.01 });
      var showAvatar = !!v.channelAvatar || !!ctx.avatars;
      var avatar = null;
      if (showAvatar) {
        avatar = mkImg('avatar');
        ctx.lazy.set(avatar, v.channelAvatar);
        avatar.addEventListener('click', function (e) { e.stopPropagation(); if (ctx.avatar) ctx.avatar(v); });
      }
      var more = PT.iconButton('more_vert', 20, 'more', 'menu');
      more.addEventListener('click', function (e) { e.stopPropagation(); if (ctx.more) ctx.more(v); });
      var card = h('div', { class: 'vcard' + (showAvatar ? ' has-avatar' : ''), data: { id: v.id }, role: 'button', tabindex: '0' },
        h('div', { class: 'thumb' }, thumb, dur, prog),
        h('div', { class: 'vmeta' }, avatar,
          h('div', { class: 'vtxt' }, h('div', { class: 'vtitle', text: v.title }), h('div', { class: 'vsub', text: videoMeta(v) })),
          more));
      card.addEventListener('click', function () { ctx.play(v); });
      card.addEventListener('keydown', function (e) { if (e.keyCode === 13) ctx.play(v); });
      card._video = v;
      card._progress = prog;
      card._avatar = avatar;
      return card;
    },

    playlist: function (p, ctx) {
      var thumb = mkImg('thumb-img');
      ctx.lazy.set(thumb, p.thumbnail);
      var meta = [];
      if (p.channelName) meta.push(p.channelName);
      meta.push(PT.t('video.playlists'));
      var card = h('div', { class: 'vcard plcard', role: 'button', tabindex: '0' },
        h('div', { class: 'thumb' }, thumb, h('span', { class: 'dur', text: '≡ ' + p.videoCount, hidden: !p.videoCount })),
        h('div', { class: 'vmeta' }, h('div', { class: 'vtxt' }, h('div', { class: 'vtitle', text: p.title }), h('div', { class: 'vsub', text: meta.join(' · ') }))));
      card.addEventListener('click', function () { ctx.openPlaylist(p); });
      return card;
    },

    channel: function (c, ctx) {
      var avatar = mkImg('avatar big');
      ctx.lazy.set(avatar, c.avatar);
      var sub = [];
      if (c.handle) sub.push(c.handle);
      if (c.subscribers) sub.push(c.subscribers);
      var btn = PT.subscribeButton(function () { return c; });
      var row = h('div', { class: 'chrow', role: 'button', tabindex: '0' }, avatar,
        h('div', { class: 'chtxt' }, h('div', { class: 'chname', text: c.name }), h('div', { class: 'chsub', text: sub.join(' · ') })), btn);
      row.addEventListener('click', function () { PT.router.openChannel(c.id, c.name); });
      return row;
    },

    text: function (text) {
      var box = h('div', { class: 'textblock' });
      box.appendChild(PT.linkify(text, {}));
      return box;
    },

    /** Horizontal row of vertical Shorts cards */
    shorts: function (list, ctx) {
      var row = h('div', { class: 'shorts-row' });
      list.forEach(function (v, i) {
        var img = mkImg('thumb-img');
        ctx.lazy.set(img, thumbUrl(v));
        var card = h('div', { class: 'scard', role: 'button', tabindex: '0' }, img,
          h('div', { class: 'scard-txt' }, h('div', { class: 'scard-title', text: v.title }), h('div', { class: 'scard-views', text: v.views })));
        card.addEventListener('click', function () { PT.router.openShorts(list, i); });
        row.appendChild(card);
      });
      return h('div', { class: 'shorts-shelf' },
        h('div', { class: 'shorts-head' }, h('span', { class: 'shorts-ico', html: PT.iconSvg('shorts', 26) }), h('span', { text: PT.t('shorts.title') })), row);
    }
  };

  // ---------------------------------------------------------------------------------------------------------------
  // pull to refresh
  // ---------------------------------------------------------------------------------------------------------------
  PT.pullToRefresh = function (scroller, onRefresh) {
    var ind = h('div', { class: 'ptr' }, h('div', { class: 'spinner' }));
    scroller.parentNode ? scroller.parentNode.insertBefore(ind, scroller) : null;
    var pulling = false, dist = 0, busy = false, startY = 0, startTop = 0;
    var TH = 64;
    function setDist(d) {
      dist = d;
      ind.style.transform = 'translate3d(0,' + (d - 40) + 'px,0)';
      ind.style.opacity = String(Math.min(1, d / TH));
      ind.classList.toggle('ready', d >= TH);
    }
    function reset(animate) {
      ind.style.transition = animate ? 'transform .2s, opacity .2s' : 'none';
      setDist(0);
      setTimeout(function () { ind.style.transition = 'none'; }, 220);
    }
    scroller.addEventListener('touchstart', function (e) {
      if (busy || scroller.scrollTop > 0 || e.touches.length !== 1) { pulling = false; return; }
      startY = e.touches[0].clientY; startTop = scroller.scrollTop; pulling = true;
    }, { passive: true });
    scroller.addEventListener('touchmove', function (e) {
      if (!pulling || busy) return;
      var dy = e.touches[0].clientY - startY;
      if (dy <= 0 || scroller.scrollTop > 0) { if (dist > 0) reset(false); return; }
      if (e.cancelable) e.preventDefault();
      setDist(Math.min(110, dy * 0.5));
    }, { passive: false });
    function release() {
      if (!pulling) return;
      pulling = false;
      if (dist >= TH && !busy) {
        busy = true;
        ind.style.transition = 'transform .15s';
        setDist(TH * 0.8);
        ind.classList.add('spin');
        var finish = function () { busy = false; ind.classList.remove('spin'); reset(true); };
        Promise.resolve(onRefresh()).then(finish, finish);
      } else reset(true);
    }
    scroller.addEventListener('touchend', release, false);
    scroller.addEventListener('touchcancel', release, false);
    return { trigger: function () { if (!busy) { busy = true; ind.classList.add('spin'); setDist(TH * 0.8); var f = function () { busy = false; ind.classList.remove('spin'); reset(true); }; Promise.resolve(onRefresh()).then(f, f); } } };
  };

  // ---------------------------------------------------------------------------------------------------------------
  // FeedView: a paginated list of videos / channels / playlists / shorts shelves
  // ---------------------------------------------------------------------------------------------------------------
  PT.FeedView = function (o) {
    var self = this;
    o = o || {};
    this.o = o;
    this.items = [];
    this.seen = {};
    this.continuation = null;
    this.endpoint = o.endpoint || 'browse';
    this.generation = 0;
    this.loadingMore = false;
    this.hasLoadedOnce = false;
    this.userRequestedRefresh = false;
    this.errorState = false;

    this.list = h('div', { class: 'feed-list' });
    this.sentinel = h('div', { class: 'feed-sentinel' });
    this.state = PT.stateView();
    this.header = o.header || null;
    if (o.scroller) {
      // the list lives inside a scroller that belongs to someone else (the watch page)
      this.scroller = o.scroller;
      this.el = h('div', { class: 'feedview inline' + (o.cls ? ' ' + o.cls : '') }, this.list, this.sentinel, this.state.el);
    } else {
      this.scroller = h('div', { class: 'scroll feed' + (o.cls ? ' ' + o.cls : '') });
      if (this.header) this.scroller.appendChild(this.header);
      this.scroller.appendChild(this.list);
      this.scroller.appendChild(this.sentinel);
      this.el = h('div', { class: 'feedview' }, this.scroller, this.state.el);
    }
    this.lazy = PT.lazyLoader(null);
    this.state.onAction = function () { if (self.errorState) self.reload(); else if (o.onEmptyAction) o.onEmptyAction(); };

    this.ctx = {
      lazy: this.lazy,
      avatars: !!o.avatars,
      play: function (v) { if (o.play) o.play(v, self); else PT.router.play(v); },
      more: function (v) { PT.router.showVideoMenu(v, o.extraActions ? o.extraActions(v, self) : []); },
      avatar: function (v) {
        PT.channelDirectory.owner(v).then(function (c) { if (c) PT.router.openChannel(c.id, c.name); }, PT.noop);
      },
      openPlaylist: function (p) {
        if (p.id.indexOf('RD') === 0 && p.id.length === 13) {
          // A Mix ("RD" + video id) cannot be browsed; play its seed video and let autoplay follow the related list.
          PT.router.play({ id: p.id.slice(2), title: p.title, thumbnail: p.thumbnail });
        } else PT.router.openPlaylist(p.id, p.title);
      }
    };

    // infinite scroll
    if ('IntersectionObserver' in window) {
      this.io = new IntersectionObserver(function (es) {
        if (es[0].isIntersecting) self.loadMore();
      }, { root: null, rootMargin: '600px 0px 600px 0px' });
      this.io.observe(this.sentinel);
    } else {
      this.scroller.addEventListener('scroll', PT.debounce(function () {
        if (self.scroller.scrollHeight - self.scroller.scrollTop - self.scroller.clientHeight < 800) self.loadMore();
      }, 100));
    }

    // "seen on screen" tracking (Home remembers what it showed)
    if (o.onDisplayVideo && 'IntersectionObserver' in window) {
      this.seenIO = new IntersectionObserver(function (es) {
        es.forEach(function (en) {
          if (en.isIntersecting && en.target._video) { self.seenIO.unobserve(en.target); o.onDisplayVideo(en.target._video); }
        });
      }, { root: null, threshold: 0.5 });
    }

    if (o.refresh !== false && !o.scroller) {
      this.ptr = PT.pullToRefresh(this.scroller, function () { return self.pulled(); });
    }

    this.onStore = function () { self.refreshProgress(); };
    this.onDir = function () { self.refreshAvatars(); };
    PT.on('store', this.onStore);
    if (o.avatars) PT.on('channelDirectory', this.onDir);
  };

  PT.FeedView.prototype = {
    destroy: function () {
      PT.off('store', this.onStore);
      PT.off('channelDirectory', this.onDir);
      if (this.io) this.io.disconnect();
      if (this.seenIO) this.seenIO.disconnect();
      this.lazy.disconnect();
      this.generation++;
    },

    pulled: function () {
      var self = this;
      this.userRequestedRefresh = true;
      var p = this.reload();
      this.userRequestedRefresh = false;
      return p;
    },

    allVideos: function () {
      var out = [];
      this.items.forEach(function (it) { if (it.type === 'video') out.push(it.video); });
      return out;
    },

    scrollToTop: function (smooth) {
      if (smooth && this.scroller.scrollTo) { try { this.scroller.scrollTo({ top: 0, behavior: 'smooth' }); return; } catch (e) { /* old browsers */ } }
      this.scroller.scrollTop = 0;
    },

    /** Loads the first page again. */
    reload: function () {
      var self = this, o = this.o;
      var gen = ++this.generation;
      this.loadingMore = false;
      if (!this.items.length) this.state.loading();
      return Promise.resolve(o.fetchFirst ? o.fetchFirst(this.userRequestedRefresh, this) : { items: [] }).then(function (page) {
        if (gen !== self.generation) return;
        self.resetItems();
        self.append(page);
        self.hasLoadedOnce = true;
        if (o.didReceiveFirstPage) o.didReceiveFirstPage(page, self);
        self.finishFirst();
      }, function (err) {
        if (gen !== self.generation) return;
        if (!self.items.length) {
          self.errorState = true;
          self.state.show('cloud_off', PT.t('common.error'), err && err.message, PT.t('common.retry'));
        }
      });
    },

    finishFirst: function () {
      var o = this.o;
      if (!this.items.length) {
        this.errorState = false;
        this.state.show(o.emptyIcon || 'search', o.emptyTitle || PT.t('common.empty'), o.emptyDetail, o.emptyButton);
      } else this.state.hide();
    },

    /** Empties the list (e.g. before switching to another chip / query) without touching the network. */
    clear: function () {
      this.generation++;
      this.resetItems();
      this.loadingMore = false;
      this.scroller.scrollTop = 0;
    },

    resetItems: function () {
      this.items = []; this.seen = {}; this.continuation = null;
      PT.clear(this.list);
    },

    /** Replace the content with an already available page (library screens etc.). */
    setPage: function (page) {
      this.generation++;
      this.resetItems();
      this.append(page);
      this.hasLoadedOnce = true;
      this.finishFirst();
    },

    append: function (page) {
      var self = this, frag = document.createDocumentFragment(), added = 0;
      (page.items || []).forEach(function (it) {
        var el = null;
        if (it.type === 'video') {
          if (self.seen[it.video.id]) return;
          self.seen[it.video.id] = true;
          el = PT.cards.video(it.video, self.ctx);
          if (self.seenIO) self.seenIO.observe(el);
          self.items.push(it);
        } else if (it.type === 'channel') {
          var ck = 'c:' + it.channel.id;
          if (self.seen[ck]) return;
          self.seen[ck] = true;
          el = PT.cards.channel(it.channel, self.ctx);
          self.items.push(it);
        } else if (it.type === 'playlist') {
          var pk = 'p:' + it.playlist.id;
          if (self.seen[pk]) return;
          self.seen[pk] = true;
          el = PT.cards.playlist(it.playlist, self.ctx);
          self.items.push(it);
        } else if (it.type === 'shorts') {
          var fresh = it.videos.filter(function (v) { return !self.seen[v.id]; });
          if (!fresh.length) return;
          fresh.forEach(function (v) { self.seen[v.id] = true; });
          el = PT.cards.shorts(fresh, self.ctx);
          self.items.push({ type: 'shorts', videos: fresh });
        } else if (it.type === 'text') {
          el = PT.cards.text(it.text);
          self.items.push(it);
        }
        if (el) { frag.appendChild(el); added++; }
      });
      this.list.appendChild(frag);
      this.continuation = page.continuation || null;
      this.sentinel.className = 'feed-sentinel' + (this.continuation ? ' more' : '');
      if (this.continuation && !this.sentinel.firstChild) this.sentinel.appendChild(h('div', { class: 'spinner' }));
      if (!this.continuation) PT.clear(this.sentinel);
      return added;
    },

    removeVideo: function (id) {
      this.items = this.items.filter(function (it) { return !(it.type === 'video' && it.video.id === id); });
      delete this.seen[id];
      var el = this.list.querySelector('.vcard[data-id="' + id + '"]');
      if (el) PT.remove(el);
      if (!this.items.length) this.finishFirst();
    },

    loadMore: function () {
      var self = this, o = this.o;
      var token = this.continuation;
      if (!token || this.loadingMore || !this.hasLoadedOnce) return;
      this.loadingMore = true;
      var gen = this.generation;
      var fetch = o.fetchMore ? o.fetchMore(token, this.endpoint, this) : PT.api.continuation(token, this.endpoint);
      Promise.resolve(fetch).then(function (page) {
        if (gen !== self.generation) return;
        self.loadingMore = false;
        var before = self.items.length;
        self.append(page);
        // A page that adds nothing new would otherwise loop forever.
        if (self.items.length === before && page.continuation === token) { self.continuation = null; PT.clear(self.sentinel); }
        else if (self.continuation && self.sentinel.getBoundingClientRect().top < window.innerHeight + 400) {
          setTimeout(function () { self.loadMore(); }, 50);
        }
      }, function () {
        if (gen !== self.generation) return;
        self.loadingMore = false;
        self.continuation = null;
        PT.clear(self.sentinel);
      });
    },

    refreshProgress: function () {
      var cards = this.list.querySelectorAll('.vcard');
      for (var i = 0; i < cards.length; i++) {
        var c = cards[i];
        if (!c._video || !c._progress) continue;
        var f = progressOf(c._video);
        c._progress.style.width = Math.round(f * 100) + '%';
        c._progress.hidden = f <= 0.01;
      }
    },

    refreshAvatars: function () {
      var cards = this.list.querySelectorAll('.vcard');
      for (var i = 0; i < cards.length; i++) {
        var c = cards[i];
        if (!c._video || !c._avatar || c._avatar.getAttribute('src') || c._avatar.getAttribute('data-src')) continue;
        var filled = PT.channelDirectory.filled(c._video);
        if (filled.channelAvatar) { c._video = filled; this.lazy.set(c._avatar, filled.channelAvatar); }
      }
    }
  };
})(window.PT);
