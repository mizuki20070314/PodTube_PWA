/* Player controls overlay: seek bar with fine scrubbing and film strip, transport, captions, stats
   (PlayerControls.swift, ScrubPreview.swift). */
(function (PT) {
  'use strict';
  var h = PT.h;

  // when the player is turned on its side by CSS (a phone held upright, full screen), pointer positions must be mapped back
  PT.view = { rot: false };

  // ---------------------------------------------------------------------------------------------------------------
  // seek bar: a finger anywhere on it moves the position; held well above the bar it "fine adjusts" (the position then
  // follows the sideways movement at the pace of the film strip)
  // ---------------------------------------------------------------------------------------------------------------
  function SeekBar() {
    var self = this;
    this.track = h('div', { class: 'sb-track' });
    this.bufferEl = h('div', { class: 'sb-buffer' });
    this.playedEl = h('div', { class: 'sb-played' });
    this.thumb = h('div', { class: 'sb-thumb' });
    this.el = h('div', { class: 'seekbar' }, this.track, this.bufferEl, this.playedEl, this.thumb);
    this.value = 0;
    this.buffered = 0;
    this.isScrubbing = false;
    this.isFine = false;
    this.fineValuePerPoint = null;
    this.fineAnchorX = 0;
    this.fineAnchorValue = 0;
    this.onBegin = this.onChange = this.onFineChanged = this.onEnd = null;
    var active = false;

    function pos(e) {
      var t = e.touches && e.touches.length ? e.touches[0] : (e.changedTouches && e.changedTouches.length ? e.changedTouches[0] : e);
      var r = self.el.getBoundingClientRect(), rot = PT.view.rot;
      return {
        x: rot ? t.clientY - r.top : t.clientX - r.left,
        y: rot ? r.right - t.clientX : t.clientY - r.top,
        len: rot ? r.height : r.width, thick: rot ? r.width : r.height
      };
    }
    function update(e) {
      var p = pos(e), lift = p.thick / 2 - p.y;
      var wantsFine = self.fineValuePerPoint !== null && lift >= (self.isFine ? 14 : 36);
      if (wantsFine !== self.isFine) {
        self.isFine = wantsFine;
        self.fineAnchorX = p.x;
        self.fineAnchorValue = self.value;
        if (self.onFineChanged) self.onFineChanged(wantsFine);
      }
      if (self.isFine) {
        self.setValue(PT.clamp(self.fineAnchorValue + (p.x - self.fineAnchorX) * self.fineValuePerPoint, 0, 1));
        return;
      }
      var inset = 7, w = Math.max(1, p.len - inset * 2);
      self.setValue(PT.clamp((p.x - inset) / w, 0, 1));
    }
    function begin(e) {
      if (active) return;
      active = true;
      self.isScrubbing = true; self.isFine = false;
      self.el.classList.add('scrubbing');
      update(e);
      if (self.onBegin) self.onBegin();
      if (self.onChange) self.onChange(self.value);
    }
    function move(e) {
      if (!active) return;
      if (e.cancelable) e.preventDefault();
      update(e);
      if (self.onChange) self.onChange(self.value);
    }
    function end(e, cancelled) {
      if (!active) return;
      active = false;
      if (!cancelled) update(e);
      self.isScrubbing = false; self.isFine = false;
      self.el.classList.remove('scrubbing');
      self.render();
      if (self.onEnd) self.onEnd(self.value);
    }
    this.el.addEventListener('touchstart', function (e) { begin(e); if (e.cancelable) e.preventDefault(); }, { passive: false });
    this.el.addEventListener('touchmove', move, { passive: false });
    this.el.addEventListener('touchend', function (e) { end(e, false); }, false);
    this.el.addEventListener('touchcancel', function (e) { end(e, true); }, false);
    this.el.addEventListener('mousedown', function (e) {
      if (e.button !== 0) return;
      begin(e);
      var mm = function (ev) { move(ev); };
      var mu = function (ev) { window.removeEventListener('mousemove', mm); window.removeEventListener('mouseup', mu); end(ev, false); };
      window.addEventListener('mousemove', mm);
      window.addEventListener('mouseup', mu);
      e.preventDefault();
    }, false);
    this.render();
  }
  SeekBar.prototype = {
    setValue: function (v) { this.value = v; this.render(); },
    setBuffered: function (b) { this.buffered = b; this.render(); },
    render: function () {
      var v = PT.clamp(this.value, 0, 1), b = PT.clamp(this.buffered, 0, 1);
      // the track runs between the two thumb radii
      this.bufferEl.style.width = 'calc((100% - 14px) * ' + b + ')';
      this.playedEl.style.width = 'calc((100% - 14px) * ' + v + ')';
      this.thumb.style.left = 'calc(7px + (100% - 14px) * ' + v + ' - ' + (this.isScrubbing ? 10 : 7) + 'px)';
    }
  };

  // ---------------------------------------------------------------------------------------------------------------
  // film strip: preview frames sliding under a fixed white line (the current position)
  // ---------------------------------------------------------------------------------------------------------------
  var PREFERRED_FRAME_WIDTH = 160;

  function FilmStrip() {
    this.el = h('div', { class: 'filmstrip' });
    this.playhead = h('div', { class: 'fs-playhead' });
    this.el.appendChild(this.playhead);
    this.tiles = [];
    this.sb = null; this.level = null; this.coarse = null; this.time = 0;
    var self = this;
    PT.on('storyboardSheet', function () { if (self.el.classList.contains('show')) self.layout(); });
  }
  FilmStrip.prototype = {
    configure: function (sb) {
      this.sb = sb;
      this.level = sb ? sb.level(PREFERRED_FRAME_WIDTH) : null;
      this.coarse = sb ? sb.levels[0] : null;
    },
    setTime: function (t) { this.time = t; this.layout(); },

    /** Paints a tile with the frame `cell` of `level` (false when its sheet is not here yet). */
    paint: function (tile, level, cell, tileW, tileH) {
      var url = this.sb.sheetURL(level, cell.sheet);
      var entry = PT.player.loadSheet(url);
      if (!entry.loaded) return false;
      var img = entry.img;
      var k = tileH / level.height;                         // sheet scale so that one frame is as tall as the tile
      var sx = img.naturalWidth / (level.columns * level.width);   // the last sheet may have fewer rows: same factor on both axes
      var cellW = level.width * k, cellH = level.height * k;
      var bgW = img.naturalWidth / sx * k, bgH = img.naturalHeight / sx * k;
      tile.style.backgroundImage = 'url("' + url + '")';
      tile.style.backgroundSize = bgW + 'px ' + bgH + 'px';
      tile.style.backgroundPosition = (-(cell.column * cellW + (cellW - tileW) / 2)) + 'px ' + (-(cell.row * cellH)) + 'px';
      return true;
    },

    layout: function () {
      var el = this.el, hgt = el.clientHeight, w = el.clientWidth;
      if (!this.sb || !this.level || hgt <= 0) { this.tiles.forEach(function (t) { t.style.display = 'none'; }); return; }
      var sb = this.sb, level = this.level;
      var tileW = Math.round(hgt), spacing = sb.spacing(level), pps = tileW / spacing, mid = w / 2, t = this.time;
      var origin = Math.round(mid - t * pps);
      var firstSeen = Math.floor((t - mid / pps) / spacing), lastSeen = Math.ceil((t + mid / pps) / spacing);
      var first = Math.max(0, firstSeen), last = Math.min(level.count - 1, lastSeen), used = 0;
      for (var f = first; f <= last; f++) {
        while (this.tiles.length <= used) {
          var tile = h('div', { class: 'fs-tile' });
          el.insertBefore(tile, this.playhead);
          this.tiles.push(tile);
        }
        var tl = this.tiles[used++];
        tl.style.display = 'block';
        tl.style.left = (origin + f * tileW) + 'px';
        tl.style.width = tileW + 'px';
        var ok = this.paint(tl, level, sb.cell(level, f), tileW, hgt);
        if (!ok && this.coarse && this.coarse.index !== level.index) {
          // the small frames of the whole video come first: a blurry stand-in until the real one arrives
          var when = sb.time(level, f) + spacing / 2;
          ok = this.paint(tl, this.coarse, sb.cellAt(this.coarse, when), tileW, hgt);
        }
        if (!ok) { tl.style.backgroundImage = 'none'; }
      }
      for (var i = used; i < this.tiles.length; i++) this.tiles[i].style.display = 'none';
    }
  };

  // ---------------------------------------------------------------------------------------------------------------
  // controls
  // ---------------------------------------------------------------------------------------------------------------
  PT.Controls = function () {
    var self = this, P = PT.player;
    this.visible = true;
    this.fingerDown = false;
    this.scrubFine = false;
    this.scrubbingFlag = false;
    this.scrubTime = 0;
    this.scrubSb = null;
    this.hideTimer = 0;
    this.ticks = 0;
    this.isFullscreen = false;
    this.onCollapse = this.onFullscreen = this.onSettings = this.onCaptions = null;

    function ib(icon, size, cls, label) { return PT.iconButton(icon, size, 'ctl-btn ' + cls, label); }
    this.shade = h('div', { class: 'ctl-shade' });
    this.stats = h('pre', { class: 'ctl-stats', hidden: true });
    this.thin = h('div', { class: 'ctl-thin' });
    this.sub = h('div', { class: 'ctl-sub', hidden: true });
    this.collapseBtn = ib('keyboard_arrow_down', 30, 'ctl-collapse', 'minimize');
    this.title = h('div', { class: 'ctl-title', hidden: true });
    this.pipBtn = ib('picture_in_picture_alt', 24, 'ctl-pip', 'picture in picture');
    this.airBtn = ib('airplay', 24, 'ctl-air', 'AirPlay');
    this.capBtn = ib('closed_caption_off', 24, 'ctl-cap', PT.t('player.captions'));
    this.setBtn = ib('settings', 24, 'ctl-set', PT.t('player.settings'));
    this.prevBtn = ib('skip_previous', 34, 'ctl-prev', 'previous');
    this.playBtn = ib('play_arrow', 44, 'ctl-play', 'play');
    this.nextBtn = ib('skip_next', 34, 'ctl-next', 'next');
    this.time = h('div', { class: 'ctl-time' });
    this.chapter = h('div', { class: 'ctl-chapter' });
    this.fsBtn = ib('fullscreen', 26, 'ctl-fs', 'fullscreen');
    this.seek = new SeekBar();
    this.spinner = h('div', { class: 'spinner white ctl-spinner' });
    this.errorEl = h('div', { class: 'ctl-error', hidden: true });
    this.retryBtn = h('button', { class: 'ctl-retry', type: 'button', text: PT.t('common.retry'), hidden: true });
    this.strip = new FilmStrip();
    this.pill = h('div', { class: 'ctl-pill' });
    this.skip = h('div', { class: 'ctl-skip' });
    this.topRight = h('div', { class: 'ctl-topright' }, this.pipBtn, this.airBtn, this.capBtn, this.setBtn);
    this.el = h('div', { class: 'ctl' }, this.shade, this.stats, this.thin, this.sub, this.collapseBtn, this.title, this.topRight,
      this.prevBtn, this.playBtn, this.nextBtn, this.time, this.chapter, this.seek.el, this.fsBtn,
      this.spinner, this.errorEl, this.retryBtn, this.strip.el, this.pill, this.skip);

    this.collapseBtn.addEventListener('click', function () { if (self.onCollapse) self.onCollapse(); });
    this.capBtn.addEventListener('click', function () { if (self.onCaptions) self.onCaptions(); self.scheduleHide(); });
    this.setBtn.addEventListener('click', function () { if (self.onSettings) self.onSettings(); self.scheduleHide(); });
    this.pipBtn.addEventListener('click', function () { P.pip.toggle(); self.scheduleHide(); });
    this.airBtn.addEventListener('click', function () { P.airplay.show(); self.scheduleHide(); });
    this.fsBtn.addEventListener('click', function () { if (self.onFullscreen) self.onFullscreen(); });
    this.playBtn.addEventListener('click', function () { P.toggle(); self.scheduleHide(); });
    this.prevBtn.addEventListener('click', function () { P.playPrevious(); self.scheduleHide(); });
    this.nextBtn.addEventListener('click', function () { P.playNext(); self.scheduleHide(); });
    this.retryBtn.addEventListener('click', function () { P.retry(); });

    this.seek.onBegin = function () { self.scrubBegan(); };
    this.seek.onFineChanged = function (f) { self.scrubFine = f; self.updateScrubChrome(); };
    this.seek.onChange = function (v) { self.scrubMoved(v); };
    this.seek.onEnd = function (v) { self.scrubEnded(v); };

    // tap: toggle the controls; double tap: skip back / forward by 10 s or play / pause (by third of the width)
    var lastTap = 0, lastX = 0, tapTimer = 0;
    this.el.addEventListener('click', function (e) {
      if (e.target.closest && e.target.closest('button, .seekbar')) return;
      var now = Date.now();
      var r = self.el.getBoundingClientRect();
      var x = PT.view.rot ? (e.clientY - r.top) : (e.clientX - r.left);
      var w = PT.view.rot ? r.height : r.width;
      if (now - lastTap < 300) {
        clearTimeout(tapTimer); lastTap = 0;
        if (x < w / 3) { P.skip(-10); self.flashSkip('« 10', false); }
        else if (x > w * 2 / 3) { P.skip(10); self.flashSkip('10 »', true); }
        else P.toggle();
        return;
      }
      lastTap = now; lastX = x;
      clearTimeout(tapTimer);
      tapTimer = setTimeout(function () { self.setVisible(!self.visible); }, 260);
    }, false);

    PT.on('player', function () { self.refreshState(); });
    PT.on('playerItem', function () { self.refreshState(); });
    PT.on('subtitles', function () { self.refreshCaptionIcon(); });
    PT.on('pip', function () { self.refreshPip(); });
    PT.on('airplay', function () { self.refreshPip(); });
    this.timer = setInterval(function () { self.tick(); }, 250);
    this.refreshState();
  };

  PT.Controls.prototype = {
    stripHeight: function () { return Math.min(120, Math.max(56, Math.round(this.el.clientHeight * 0.3))); },

    // scrubbing ------------------------------------------------------------------------------------------------------
    scrubBegan: function () {
      var P = PT.player;
      this.scrubbingFlag = true;
      this.fingerDown = true;
      this.scrubFine = false;
      this.cancelHide();
      P.beginScrub();
      this.scrubSb = P.storyboard;
      this.strip.configure(this.scrubSb);
      var sb = this.scrubSb, d = P.duration;
      this.seek.fineValuePerPoint = (sb && d > 0)
        ? sb.spacing(sb.level(PREFERRED_FRAME_WIDTH)) / Math.round(this.stripHeight()) / d : null;
      if (sb) P.warmStoryboard(sb, sb.level(PREFERRED_FRAME_WIDTH), this.seek.value * d);
      this.updateScrubChrome();
    },
    scrubMoved: function (v) {
      var P = PT.player, d = P.duration;
      this.scrubTime = v * d;
      this.time.textContent = PT.fmt.duration(this.scrubTime) + ' / ' + PT.fmt.duration(d);
      P.scrub(this.scrubTime, this.scrubFine);
      this.strip.setTime(this.scrubTime);
      this.updatePill();
    },
    scrubEnded: function (v) {
      var self = this, d = PT.player.duration;
      this.fingerDown = false;
      this.scrubFine = false;
      this.updateScrubChrome();
      PT.player.endScrub(v * d, function () { self.scrubbingFlag = false; });
      this.scheduleHide();
    },
    updatePill: function () {
      var P = PT.player;
      var ch = PT.chapters.current(P.chapters, this.scrubTime);
      this.pill.innerHTML = '';
      this.pill.appendChild(h('b', { text: PT.fmt.duration(this.scrubTime) }));
      if (ch) this.pill.appendChild(h('span', { text: '  ' + ch.title }));
      this.layoutScrub();
    },
    layoutScrub: function () {
      var hgt = this.el.clientHeight, sh = this.stripHeight();
      this.strip.el.style.height = sh + 'px';
      var bottom = this.scrubFine ? sh + 12 : (hgt - (this.seek.el.offsetTop + this.seek.el.offsetHeight / 2)) + 26;
      this.pill.style.bottom = bottom + 'px';
    },
    updateScrubChrome: function () {
      this.layoutScrub();
      this.applyVisibility();
      var showStrip = this.fingerDown && this.scrubFine;
      this.strip.el.classList.toggle('show', showStrip);
      this.pill.classList.toggle('show', this.fingerDown);
      if (showStrip) this.strip.layout();
    },

    flashSkip: function (text, forward) {
      var s = this.skip;
      s.textContent = text;
      s.style.left = (forward ? 78 : 22) + '%';
      s.classList.remove('fade');
      void s.offsetWidth;
      s.classList.add('show');
      clearTimeout(this._skipT);
      this._skipT = setTimeout(function () { s.classList.remove('show'); s.classList.add('fade'); }, 350);
    },

    // visibility ---------------------------------------------------------------------------------------------------
    setVisible: function (v) {
      this.visible = v;
      this.applyVisibility();
      if (v) this.scheduleHide(); else this.cancelHide();
    },
    chromeVisible: function () { return this.visible && !this.fingerDown; },
    applyVisibility: function () {
      var chrome = this.chromeVisible();
      this.el.classList.toggle('chrome', chrome);
      this.el.classList.toggle('barshown', this.visible || this.fingerDown);
      this.refreshTransport();
      this.refreshPip();
      this.updatePlayButton();
    },
    refreshTransport: function () {
      var P = PT.player;
      this.prevBtn.classList.toggle('dim', !P.hasPrevious);
      this.nextBtn.classList.toggle('dim', !P.hasNext);
    },
    scheduleHide: function () {
      var self = this;
      clearTimeout(this.hideTimer);
      if (PT.player.state !== 'playing') return;
      this.hideTimer = setTimeout(function () { if (!self.scrubbingFlag) self.setVisible(false); }, 3500);
    },
    cancelHide: function () { clearTimeout(this.hideTimer); this.hideTimer = 0; },
    updatePlayButton: function () {
      var st = PT.player.state, busy = st === 'loading' || st === 'buffering', failed = st === 'failed';
      this.playBtn.classList.toggle('gone', !((this.chromeVisible()) && !busy && !failed));
    },

    // state --------------------------------------------------------------------------------------------------------
    refreshState: function () {
      var P = PT.player, st = P.state;
      PT.setIcon(this.playBtn, st === 'playing' ? 'pause' : (st === 'ended' ? 'refresh' : 'play_arrow'), 44);
      var busy = st === 'loading' || st === 'buffering';
      this.spinner.style.display = busy ? 'block' : 'none';
      this.errorEl.hidden = st !== 'failed';
      this.retryBtn.hidden = st !== 'failed';
      this.errorEl.textContent = P.errorMessage || '';
      this.refreshTransport();
      this.title.textContent = P.current ? P.current.title || '' : '';
      this.updatePlayButton();
      if (st === 'playing') this.scheduleHide();
      else { this.cancelHide(); if (st !== 'loading' && !this.visible) this.setVisible(true); }
      this.refreshCaptionIcon();
      this.refreshPip();
      this.refreshStats();
    },
    refreshStats: function () {
      var P = PT.player;
      this.stats.hidden = !P.showsStats;
      if (P.showsStats) this.stats.textContent = P.statsLines().join('\n');
    },
    refreshPip: function () {
      var P = PT.player, sup = P.pip.supported;
      this.pipBtn.hidden = !sup;
      this.airBtn.hidden = !(P.airplay.supported && P.airplay.available);
      this.el.classList.toggle('no-pip', !sup);
      this.el.classList.toggle('no-air', this.airBtn.hidden);
      this.pipBtn.classList.toggle('dim', !P.current);
    },
    refreshCaptionIcon: function () {
      var S = PT.subtitles;
      this.capBtn.hidden = !S.tracks.length;
      PT.setIcon(this.capBtn, S.isEnabled ? 'closed_caption' : 'closed_caption_off', 24);
      if (!S.isEnabled) this.sub.hidden = true;
    },
    setFullscreen: function (on) {
      this.isFullscreen = on;
      PT.setIcon(this.fsBtn, on ? 'fullscreen_exit' : 'fullscreen', 26);
      this.title.hidden = !on;
      this.el.classList.toggle('fullscreen', on);
      this.layoutScrub();
    },

    tick: function () {
      var P = PT.player;
      if (!this.el.offsetParent && !this.el.clientWidth) return;       // not on screen
      var d = P.duration, t = P.currentTime, live = P.isLive;
      this.seek.el.style.visibility = live ? 'hidden' : '';
      this.thin.style.display = live ? 'none' : '';
      if (!this.scrubbingFlag) {
        var v = d > 0 ? t / d : 0;
        this.seek.setValue(PT.clamp(v, 0, 1));
        this.seek.setBuffered(d > 0 ? P.bufferedEnd / d : 0);
        this.time.textContent = live ? '● ' + PT.t('video.live') : PT.fmt.duration(t) + ' / ' + PT.fmt.duration(d);
        this.thin.style.width = (PT.clamp(v, 0, 1) * 100) + '%';
      }
      var ch = live ? null : PT.chapters.current(P.chapters, t);
      this.chapter.textContent = ch ? '· ' + ch.title : '';
      // captions (not while a finger scrubs: they would sit on the pill)
      var text = (!this.fingerDown && PT.subtitles.isEnabled) ? PT.subtitles.textAt(t) : null;
      if (text) {
        if (this.sub.textContent !== text) this.sub.textContent = text;
        this.sub.hidden = false;
      } else this.sub.hidden = true;
      if (++this.ticks % 4 === 0) this.refreshStats();
    }
  };
})(window.PT);
