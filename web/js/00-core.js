/* PodTube PWA - core helpers.  Plain ES2017 (no optional chaining etc.): the PWA has to run on Safari 12 (iOS 12). */
(function (global) {
  'use strict';
  var PT = global.PT = { version: '1.0.0' };

  // ---------------------------------------------------------------------------------------------------------------
  // platform
  // ---------------------------------------------------------------------------------------------------------------
  var ua = navigator.userAgent || '';
  PT.isIOS = /iPad|iPhone|iPod/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  PT.isAndroid = /Android/i.test(ua);
  PT.isSafari = /^((?!chrome|android|crios|fxios|edg).)*safari/i.test(ua);
  PT.isApple = PT.isIOS || PT.isSafari;
  PT.hasTouch = ('ontouchstart' in global) || (navigator.maxTouchPoints > 0);
  PT.standalone = !!(global.navigator.standalone) || (global.matchMedia && global.matchMedia('(display-mode: standalone)').matches);

  // ---------------------------------------------------------------------------------------------------------------
  // small utilities
  // ---------------------------------------------------------------------------------------------------------------
  PT.noop = function () {};

  PT.debounce = function (fn, ms) {
    var t = null;
    return function () {
      var self = this, args = arguments;
      clearTimeout(t);
      t = setTimeout(function () { fn.apply(self, args); }, ms);
    };
  };

  PT.clamp = function (v, lo, hi) { return Math.min(hi, Math.max(lo, v)); };
  PT.lerp = function (a, b, t) { return a + (b - a) * t; };

  PT.uuid = function () {
    var s = '';
    for (var i = 0; i < 16; i++) s += Math.floor(Math.random() * 256).toString(16).replace(/^(.)$/, '0$1');
    return s;
  };

  var CPN_ALPHABET = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_';
  PT.newCpn = function () {
    var s = '';
    for (var i = 0; i < 16; i++) s += CPN_ALPHABET.charAt(Math.floor(Math.random() * 64));
    return s;
  };

  // ---------------------------------------------------------------------------------------------------------------
  // DOM builder:  h('div', {class:'x', on:{click:fn}, style:'..'}, child, [children], 'text')
  // ---------------------------------------------------------------------------------------------------------------
  PT.h = function (tag, props) {
    var el = document.createElement(tag);
    if (props) {
      for (var k in props) {
        if (!Object.prototype.hasOwnProperty.call(props, k)) continue;
        var v = props[k];
        if (v === null || v === undefined || v === false) continue;
        if (k === 'class') el.className = v;
        else if (k === 'text') el.textContent = v;
        else if (k === 'html') el.innerHTML = v;
        else if (k === 'on') { for (var ev in v) el.addEventListener(ev, v[ev], false); }
        else if (k === 'style') { if (typeof v === 'string') el.style.cssText = v; else for (var sk in v) el.style[sk] = v[sk]; }
        else if (k === 'data') { for (var dk in v) el.setAttribute('data-' + dk, v[dk]); }
        else if (v === true) el.setAttribute(k, '');
        else el.setAttribute(k, v);
      }
    }
    for (var i = 2; i < arguments.length; i++) PT.append(el, arguments[i]);
    return el;
  };

  PT.append = function (el, c) {
    if (c === null || c === undefined || c === false) return el;
    if (Array.isArray(c)) { for (var i = 0; i < c.length; i++) PT.append(el, c[i]); }
    else if (c.nodeType) el.appendChild(c);
    else el.appendChild(document.createTextNode(String(c)));
    return el;
  };

  PT.clear = function (el) { while (el.firstChild) el.removeChild(el.firstChild); return el; };
  PT.remove = function (el) { if (el && el.parentNode) el.parentNode.removeChild(el); };
  PT.$ = function (sel, root) { return (root || document).querySelector(sel); };
  PT.$$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };

  PT.escapeHtml = function (s) {
    return String(s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; });
  };

  // ---------------------------------------------------------------------------------------------------------------
  // events
  // ---------------------------------------------------------------------------------------------------------------
  var listeners = {};
  PT.on = function (name, fn) { (listeners[name] = listeners[name] || []).push(fn); return fn; };
  PT.off = function (name, fn) {
    var l = listeners[name]; if (!l) return;
    var i = l.indexOf(fn); if (i >= 0) l.splice(i, 1);
  };
  PT.emit = function (name, arg) {
    var l = listeners[name]; if (!l) return;
    l = l.slice();
    for (var i = 0; i < l.length; i++) { try { l[i](arg); } catch (e) { if (global.console) console.error(e); } }
  };

  // ---------------------------------------------------------------------------------------------------------------
  // storage (localStorage; every access is guarded: private windows / blocked storage must not break the app)
  // ---------------------------------------------------------------------------------------------------------------
  var mem = {};
  PT.ls = {
    get: function (key, def) {
      try {
        var v = global.localStorage.getItem('pt.' + key);
        if (v === null) return def;
        return JSON.parse(v);
      } catch (e) {
        return key in mem ? mem[key] : def;
      }
    },
    set: function (key, val) {
      mem[key] = val;
      try { global.localStorage.setItem('pt.' + key, JSON.stringify(val)); } catch (e) { /* quota / blocked */ }
    },
    remove: function (key) {
      delete mem[key];
      try { global.localStorage.removeItem('pt.' + key); } catch (e) { /* ignore */ }
    },
    has: function (key) {
      try { return global.localStorage.getItem('pt.' + key) !== null; } catch (e) { return key in mem; }
    }
  };

  // writes a value a little later (and only once for a burst of changes)
  var saveTimers = {};
  function flushSave(key) {
    var s = saveTimers[key];
    if (!s) return;
    clearTimeout(s.t);
    delete saveTimers[key];
    PT.ls.set(key, s.getter());
  }
  PT.saveLater = function (key, getter, ms) {
    if (saveTimers[key]) { saveTimers[key].getter = getter; return; }
    saveTimers[key] = { getter: getter, t: setTimeout(function () { flushSave(key); }, ms || 400) };
  };
  PT.flushSaves = function () { for (var k in saveTimers) flushSave(k); };
  global.addEventListener('pagehide', PT.flushSaves);
  document.addEventListener('visibilitychange', function () { if (document.hidden) PT.flushSaves(); });

  // ---------------------------------------------------------------------------------------------------------------
  // formatting
  // ---------------------------------------------------------------------------------------------------------------
  PT.fmt = {
    parseDuration: function (s) {
      if (!s) return null;
      var parts = String(s).split(':'), total = 0;
      for (var i = 0; i < parts.length; i++) {
        if (!/^\d+$/.test(parts[i])) return null;
        total = total * 60 + parseInt(parts[i], 10);
      }
      return total;
    },
    duration: function (sec) {
      if (!isFinite(sec) || sec < 0) return '0:00';
      var total = Math.floor(sec), h = Math.floor(total / 3600), m = Math.floor((total % 3600) / 60), s = total % 60;
      var p2 = function (n) { return (n < 10 ? '0' : '') + n; };
      return h > 0 ? h + ':' + p2(m) + ':' + p2(s) : m + ':' + p2(s);
    },
    bitrate: function (bps) {
      if (!isFinite(bps) || bps <= 0) return '-';
      if (bps >= 1e6) return (bps / 1e6).toFixed(1) + ' Mbps';
      return Math.round(bps / 1e3) + ' kbps';
    },
    bytes: function (n) {
      if (!isFinite(n) || n < 0) return '-';
      var units = ['B', 'KB', 'MB', 'GB'], v = n, i = 0;
      while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
      return i === 0 ? n + ' B' : v.toFixed(1) + ' ' + units[i];
    },
    // ByteCountFormatter(.file) uses powers of 1000
    fileSize: function (n) {
      if (!isFinite(n) || n <= 0) return '';
      if (n >= 1e9) return (n / 1e9).toFixed(1) + ' GB';
      if (n >= 1e6) return (n / 1e6).toFixed(n >= 1e8 ? 0 : 1) + ' MB';
      return Math.max(1, Math.round(n / 1e3)) + ' KB';
    }
  };

  // ---------------------------------------------------------------------------------------------------------------
  // tweening (requestAnimationFrame)
  // ---------------------------------------------------------------------------------------------------------------
  PT.ease = {
    out: function (t) { return 1 - Math.pow(1 - t, 3); },
    inOut: function (t) { return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2; },
    in: function (t) { return t * t * t; }
  };

  /** Runs fn(value) from `from` to `to` over `ms`; returns a function that cancels it. */
  PT.tween = function (from, to, ms, easing, fn, done) {
    var start = null, id = 0, cancelled = false;
    easing = easing || PT.ease.inOut;
    function step(ts) {
      if (cancelled) return;
      if (start === null) start = ts;
      var t = Math.min(1, (ts - start) / ms);
      fn(from + (to - from) * easing(t));
      if (t < 1) id = requestAnimationFrame(step);
      else if (done) done();
    }
    if (ms <= 0) { fn(to); if (done) done(); return PT.noop; }
    id = requestAnimationFrame(step);
    return function () { cancelled = true; cancelAnimationFrame(id); };
  };

  // ---------------------------------------------------------------------------------------------------------------
  // drag gestures (touch + mouse).  o.start(x, y, ev) may return false to ignore the gesture.
  // o.move(dx, dy, x, y, ev, state), o.end(dx, dy, vx, vy, ev, state);  state.axis is 'x' / 'y' once decided
  // ---------------------------------------------------------------------------------------------------------------
  PT.drag = function (el, o) {
    var active = false, sx = 0, sy = 0, lx = 0, ly = 0, lt = 0, vx = 0, vy = 0, decided = false, axis = '', mouse = false;
    var thr = o.threshold || 6;
    var state = {};

    function point(e) {
      var t = e.touches && e.touches.length ? e.touches[0] : (e.changedTouches && e.changedTouches.length ? e.changedTouches[0] : e);
      return { x: t.clientX, y: t.clientY };
    }
    function down(e, isMouse) {
      if (active) return;
      if (isMouse && e.button !== 0) return;
      var p = point(e);
      if (o.start && o.start(p.x, p.y, e) === false) return;
      active = true; mouse = isMouse; decided = false; axis = ''; state = {};
      sx = lx = p.x; sy = ly = p.y; lt = Date.now(); vx = vy = 0;
    }
    function move(e) {
      if (!active) return;
      var p = point(e), dx = p.x - sx, dy = p.y - sy, now = Date.now();
      if (!decided) {
        if (Math.abs(dx) < thr && Math.abs(dy) < thr) return;
        axis = Math.abs(dy) > Math.abs(dx) * (o.bias || 1.2) ? 'y' : 'x';
        if (o.axis && o.axis !== axis) { active = false; return; }
        decided = true; state.axis = axis;
        if (o.begin) { if (o.begin(dx, dy, e, state) === false) { active = false; return; } }
      }
      var dt = Math.max(1, now - lt);
      vx = 0.8 * vx + 0.2 * ((p.x - lx) / dt * 1000);
      vy = 0.8 * vy + 0.2 * ((p.y - ly) / dt * 1000);
      lx = p.x; ly = p.y; lt = now;
      if (e.cancelable && o.prevent !== false) e.preventDefault();
      if (o.move) o.move(dx, dy, p.x, p.y, e, state);
    }
    function up(e) {
      if (!active) return;
      active = false;
      var p = point(e);
      if (decided && o.end) o.end(p.x - sx, p.y - sy, vx, vy, e, state);
      else if (!decided && o.tap) o.tap(p.x, p.y, e);
    }
    el.addEventListener('touchstart', function (e) { down(e, false); }, { passive: true });
    el.addEventListener('touchmove', move, { passive: false });
    el.addEventListener('touchend', up, false);
    el.addEventListener('touchcancel', up, false);
    el.addEventListener('mousedown', function (e) {
      if (PT.hasTouch && e.sourceCapabilities && e.sourceCapabilities.firesTouchEvents) return;
      down(e, true);
    }, false);
    global.addEventListener('mousemove', function (e) { if (mouse) move(e); }, false);
    global.addEventListener('mouseup', function (e) { if (mouse) { up(e); mouse = false; } }, false);
    return { cancel: function () { active = false; } };
  };

  // ---------------------------------------------------------------------------------------------------------------
  // text -> nodes (description, comments): links, #hashtags and time stamps become tappable
  // ---------------------------------------------------------------------------------------------------------------
  var LINK_RE = /(https?:\/\/[^\s]+)|(#[^\s#]+)|((?:^|[^0-9:])(?:[0-9]{1,2}:)?[0-5]?[0-9]:[0-5][0-9](?![0-9:]))/g;

  PT.linkify = function (text, handlers) {
    var frag = document.createDocumentFragment(), last = 0, m;
    handlers = handlers || {};
    LINK_RE.lastIndex = 0;
    function a(label, cls, fn) {
      var el = PT.h('a', { class: 'lnk ' + cls, href: '#', text: label });
      el.addEventListener('click', function (e) { e.preventDefault(); fn(); });
      return el;
    }
    while ((m = LINK_RE.exec(text)) !== null) {
      var s = m[0], idx = m.index;
      if (m[3]) {            // time stamp: the character in front of it (if any) stays text
        var lead = /^[0-9]/.test(s) ? '' : s.charAt(0);
        s = lead ? s.slice(1) : s;
        idx += lead.length;
      }
      if (idx > last) frag.appendChild(document.createTextNode(text.slice(last, idx)));
      last = idx + s.length;
      if (m[1]) {
        var url = s.replace(/[)\].,;!?]+$/, '');
        last = idx + url.length;
        frag.appendChild(PT.h('a', { class: 'lnk', href: url, target: '_blank', rel: 'noopener noreferrer', text: url }));
        if (url.length < s.length) frag.appendChild(document.createTextNode(s.slice(url.length)));
      } else if (m[2]) {
        frag.appendChild(a(s, 'tag', function (tag) { return function () { if (handlers.search) handlers.search(tag); }; }(s)));
      } else {
        var secs = PT.fmt.parseDuration(s);
        frag.appendChild(a(s, 'ts', function (t) { return function () { if (handlers.seek) handlers.seek(t); }; }(secs)));
      }
    }
    if (last < text.length) frag.appendChild(document.createTextNode(text.slice(last)));
    return frag;
  };

  // ---------------------------------------------------------------------------------------------------------------
  // clipboard / share
  // ---------------------------------------------------------------------------------------------------------------
  PT.copy = function (text) {
    return new Promise(function (resolve) {
      function fallback() {
        var ta = PT.h('textarea', { style: 'position:fixed;left:-1000px;top:0;opacity:0' });
        ta.value = text;
        document.body.appendChild(ta);
        ta.focus(); ta.select();
        try { ta.setSelectionRange(0, text.length); } catch (e) { /* ignore */ }
        var ok = false;
        try { ok = document.execCommand('copy'); } catch (e) { /* ignore */ }
        PT.remove(ta);
        resolve(ok);
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function () { resolve(true); }, fallback);
      } else fallback();
    });
  };

  PT.share = function (data) {
    if (navigator.share) {
      return navigator.share(data).then(function () { return true; }, function () { return false; });
    }
    return PT.copy((data.title ? data.title + '\n' : '') + (data.url || data.text || '')).then(function (ok) {
      if (ok && PT.toast) PT.toast(PT.t('share.copied'));
      return ok;
    });
  };

  var scriptPromises = {};
  /** Loads a script once (vendor libraries that only some screens need). */
  PT.loadScript = function (src) {
    if (scriptPromises[src]) return scriptPromises[src];
    scriptPromises[src] = new Promise(function (resolve, reject) {
      var s = document.createElement('script');
      s.src = src;
      s.onload = function () { resolve(); };
      s.onerror = function () { delete scriptPromises[src]; reject(new Error('load ' + src)); };
      document.head.appendChild(s);
    });
    return scriptPromises[src];
  };

  // timing helpers for waiting on the page
  PT.sleep = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };

  // ---------------------------------------------------------------------------------------------------------------
  // back button integration: every overlay / pushed screen / expanded player registers an entry, so that the browser's
  // (or Android's) back button closes the topmost one.
  // ---------------------------------------------------------------------------------------------------------------
  PT.hist = (function () {
    var stack = [], suppress = 0, seq = 0;
    function push(close) {
      var e = { id: ++seq, close: close };
      stack.push(e);
      try { global.history.pushState({ pt: e.id }, ''); } catch (x) { /* ignore */ }
      return e;
    }
    // the UI closed the thing itself
    function release(e) {
      var i = stack.indexOf(e);
      if (i < 0) return;
      stack.splice(i, 1);
      if (i === stack.length) {
        suppress++;
        try { global.history.back(); } catch (x) { suppress--; }
      }
    }
    global.addEventListener('popstate', function () {
      if (suppress > 0) { suppress--; return; }
      var e = stack.pop();
      if (e) e.close(true);
    });
    return { push: push, release: release, depth: function () { return stack.length; } };
  })();

})(window);
