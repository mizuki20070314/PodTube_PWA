/* Screens, part 1: Home, Search, Search results, Subscriptions, Library and the lists behind it
   (HomeViewController, SearchViewController, SubscriptionsViewController, LibraryViewController, AccountViews, SubscriptionParser). */
(function (PT) {
  'use strict';
  var h = PT.h;
  var S = PT.screens = PT.screens || {};

  /** Top app bar: logo on the left, search on the right. */
  function appBar() {
    var search = PT.iconButton('search', 24, 'bar-search', PT.t('search.placeholder'));
    search.addEventListener('click', function () { PT.router.openSearchScreen(); });
    var el = h('div', { class: 'bar appbar' }, h('span', { class: 'appbar-logo', html: PT.logoSvg(20) }),
      h('span', { class: 'appbar-title', text: 'PodTube' }), h('span', { class: 'grow' }), search);
    return { el: el, search: search };
  }

  // ---------------------------------------------------------------------------------------------------------------
  // Home: topic chips + the recommendation feed
  // ---------------------------------------------------------------------------------------------------------------
  S.home = function () {
    var bar = appBar();
    var defs = [], selected = 0;
    var chips = PT.chipBar(function (i) { selected = i; feed.clear(); feed.reload(); });

    function buildChips() {
      var video = { kind: 1 }, live = { kind: 1, live: true }, week = { kind: 1, date: 3 };
      defs = [
        { title: PT.t('chip.all'), filter: video }, { title: PT.t('chip.music'), filter: video },
        { title: PT.t('chip.gaming'), filter: video }, { title: PT.t('chip.live'), filter: live },
        { title: PT.t('chip.news'), filter: week }, { title: PT.t('chip.anime'), filter: video },
        { title: PT.t('chip.sports'), filter: video }, { title: PT.t('chip.cooking'), filter: video },
        { title: PT.t('chip.comedy'), filter: video }, { title: PT.t('chip.tech'), filter: video },
        { title: PT.t('chip.travel'), filter: video }, { title: PT.t('chip.pets'), filter: video }
      ];
      selected = 0;
      chips.set(defs.map(function (d) { return d.title; }), 0);
    }

    var feed = new PT.FeedView({
      avatars: true, refresh: true, endpoint: 'browse',
      onDisplayVideo: function (v) { if (selected === 0) PT.homeSeen.mark(v.id); },
      fetchFirst: function (userRefresh) {
        if (selected === 0) {
          // New videos first: what was already shown goes behind them. A refresh the user asked for also gets a fresh
          // anonymous visitor id (the anonymous feed changes far more with it).
          return PT.api.home(PT.homeSeen.ids(), userRefresh).then(function (r) { feed.endpoint = r.endpoint || 'browse'; return r; });
        }
        var d = defs[selected];
        feed.endpoint = 'search';
        return PT.api.search(d.query || d.title, d.filter);
      }
    });
    buildChips();
    var el = h('div', { class: 'screen-inner home' }, bar.el, chips.el, feed.el);
    PT.on('settings', function () { buildChips(); feed.clear(); feed.reload(); });
    PT.on('accountChanged', function () { feed.clear(); feed.reload(); });
    feed.reload();
    return { el: el, feed: feed, scrollToTop: function (smooth) { feed.scrollToTop(smooth); } };
  };

  // ---------------------------------------------------------------------------------------------------------------
  // Search: text field + history / live suggestions
  // ---------------------------------------------------------------------------------------------------------------
  S.search = function (prefill) {
    var suggestions = [], timer = 0;
    var back = PT.iconButton('arrow_back', 24, 'bar-back', PT.t('common.close'));
    back.addEventListener('click', function () { PT.nav.back(); });
    var input = h('input', { class: 'sf-input', type: 'search', enterkeyhint: 'search', placeholder: PT.t('search.placeholder'),
      autocomplete: 'off', autocapitalize: 'none', autocorrect: 'off', spellcheck: 'false' });
    var clear = PT.iconButton('close', 18, 'sf-clear', PT.t('common.close'));
    var field = h('form', { class: 'sf', action: '#' }, input, clear);
    var list = h('div', { class: 'sg-list scroll' });
    var el = h('div', { class: 'screen-inner search' }, h('div', { class: 'bar searchbar' }, back, field), list);

    function query() { return input.value.trim(); }
    function showsHistory() { return !query(); }
    function render() {
      PT.clear(list);
      var rows = showsHistory() ? PT.store.searches : suggestions;
      rows.forEach(function (text) {
        var fill = PT.iconButton('north_west', 20, 'sg-fill', 'fill');
        var del = showsHistory() ? PT.iconButton('close', 18, 'sg-del', PT.t('common.delete')) : null;
        var row = h('div', { class: 'sg-row', role: 'button', tabindex: '0' },
          h('span', { class: 'sg-ico', html: PT.iconSvg(showsHistory() ? 'history' : 'search', 22) }), h('span', { class: 'sg-text', text: text }), del, fill);
        row.addEventListener('click', function () { submit(text); });
        fill.addEventListener('click', function (e) { e.stopPropagation(); input.value = text + ' '; clear.hidden = false; onInput(); input.focus(); });
        if (del) del.addEventListener('click', function (e) { e.stopPropagation(); PT.store.removeSearch(text); render(); });
        list.appendChild(row);
      });
    }
    function fetchSuggestions(q) {
      PT.api.suggestions(q).then(function (r) {
        if (query() !== q) return;
        suggestions = r;
        render();
      }, PT.noop);
    }
    function onInput() {
      var q = query();
      clear.hidden = !q;
      clearTimeout(timer);
      if (!q) { suggestions = []; render(); return; }
      timer = setTimeout(function () { fetchSuggestions(q); }, 180);
    }
    function submit(text) {
      var t = (text || '').trim();
      if (!t) return;
      input.blur();
      if (PT.router.open(t)) return;
      PT.router.openSearch(t);
    }
    field.addEventListener('submit', function (e) { e.preventDefault(); submit(input.value); });
    input.addEventListener('input', onInput);
    clear.addEventListener('click', function () { input.value = ''; clear.hidden = true; suggestions = []; render(); input.focus(); });
    list.addEventListener('scroll', function () { input.blur(); }, { passive: true });
    input.value = prefill || '';
    clear.hidden = !prefill;
    render();
    if (prefill) fetchSuggestions(prefill);
    return {
      el: el,
      onShow: function () { setTimeout(function () { input.focus(); }, 60); },
      onHide: function () { input.blur(); },
      destroy: function () { clearTimeout(timer); }
    };
  };

  // ---------------------------------------------------------------------------------------------------------------
  // Search results with the filter sheets
  // ---------------------------------------------------------------------------------------------------------------
  S.searchResults = function (query) {
    var filter = { sort: 0, date: 0, kind: 0, duration: 0, live: false, hd: false, subtitles: false, fourK: false };
    function isDefault() { return !filter.sort && !filter.date && !filter.kind && !filter.duration && !filter.live && !filter.hd && !filter.subtitles && !filter.fourK; }

    var back = PT.iconButton('arrow_back', 24, 'bar-back', PT.t('common.close'));
    back.addEventListener('click', function () { PT.nav.back(); });
    var qbtn = h('button', { class: 'sr-query', type: 'button', text: query });
    qbtn.addEventListener('click', function () { PT.nav.push(S.search(query)); });
    var filterBtn = PT.iconButton('tune', 24, 'sr-filter', PT.t('search.filters'));
    var feed = new PT.FeedView({
      refresh: true, endpoint: 'search',
      fetchFirst: function () { feed.endpoint = 'search'; return PT.api.search(query, isDefault() ? null : filter); }
    });
    var el = h('div', { class: 'screen-inner results' }, h('div', { class: 'bar searchbar' }, back, qbtn, filterBtn), feed.el);

    var names = {
      sort: [PT.t('search.relevance'), PT.t('search.ratingSort'), PT.t('search.dateSort'), PT.t('search.viewSort')],
      date: [PT.t('search.any'), PT.t('search.hour'), PT.t('search.today'), PT.t('search.week'), PT.t('search.month'), PT.t('search.year')],
      kind: [PT.t('search.any'), PT.t('search.video'), PT.t('search.channel'), PT.t('search.playlist'), PT.t('search.movie')],
      duration: [PT.t('search.any'), PT.t('search.short'), PT.t('search.long'), PT.t('search.medium')]
    };
    function apply() { feed.clear(); feed.reload(); }
    function pick(title, key, order, labelOf) {
      PT.sheet.show({ title: title, actions: order.map(function (val) {
        return { title: labelOf(val), checked: val === filter[key], handler: function () { filter[key] = val; apply(); } };
      }) });
    }
    filterBtn.addEventListener('click', function () {
      PT.sheet.show({ title: PT.t('search.filters'), actions: [
        { title: PT.t('search.sort'), icon: 'swap_vert', subtitle: names.sort[filter.sort], handler: function () { pick(PT.t('search.sort'), 'sort', [0, 2, 3, 1], function (v) { return names.sort[v]; }); } },
        { title: PT.t('search.uploadDate'), icon: 'schedule', subtitle: names.date[filter.date], handler: function () { pick(PT.t('search.uploadDate'), 'date', [0, 1, 2, 3, 4, 5], function (v) { return names.date[v]; }); } },
        { title: PT.t('search.type'), icon: 'video_library', subtitle: names.kind[filter.kind], handler: function () { pick(PT.t('search.type'), 'kind', [0, 1, 2, 3, 4], function (v) { return names.kind[v]; }); } },
        { title: PT.t('search.duration'), icon: 'timer', subtitle: names.duration[filter.duration], handler: function () { pick(PT.t('search.duration'), 'duration', [0, 1, 3, 2], function (v) { return names.duration[v]; }); } },
        { title: PT.t('search.reset'), icon: 'refresh', handler: function () {
          filter = { sort: 0, date: 0, kind: 0, duration: 0, live: false, hd: false, subtitles: false, fourK: false };
          apply();
        } }
      ] });
    });
    feed.reload();
    return { el: el, destroy: function () { feed.destroy(); }, scrollToTop: function (s) { feed.scrollToTop(s); } };
  };

  // ---------------------------------------------------------------------------------------------------------------
  // Subscriptions
  // ---------------------------------------------------------------------------------------------------------------
  function channelStrip(onChannel, onAll) {
    var scroll = h('div', { class: 'strip-scroll' });
    var el = h('div', { class: 'strip' }, scroll);
    var lazy = PT.lazyLoader(null);
    return {
      el: el,
      set: function (list) {
        PT.clear(scroll);
        el.hidden = !list.length;
        list.forEach(function (c) {
          var img = PT.mkImg('avatar');
          lazy.set(img, c.avatar);
          var item = h('button', { class: 'strip-item', type: 'button' }, img, h('span', { class: 'strip-name', text: c.name }));
          item.addEventListener('click', function () { onChannel(c); });
          scroll.appendChild(item);
        });
        var all = h('button', { class: 'strip-item all', type: 'button' }, h('span', { class: 'strip-all', text: PT.t('subs.all') }));
        all.addEventListener('click', onAll);
        scroll.appendChild(all);
      }
    };
  }

  var VIDEOS_TAB = 'EgZ2aWRlb3PyBgQKAjoA';

  S.subscriptions = function () {
    var bar = appBar();
    var accountChannels = [], shownIds = [], lastLoad = 0;
    var strip = channelStrip(function (c) { PT.router.openChannel(c.id, c.name); }, function () { PT.nav.push(S.channelsManager()); });
    var feed = new PT.FeedView({
      avatars: true, refresh: true,
      emptyTitle: PT.t('subs.empty'), emptyIcon: 'subscriptions', emptyDetail: PT.t('subs.emptyHint'), emptyButton: PT.t('subs.import'),
      onEmptyAction: function () { PT.nav.push(S.channelsManager()); },
      fetchFirst: function () { return PT.auth.signedIn ? fetchAccount() : fetchLocal(); }
    });
    var el = h('div', { class: 'screen-inner subs' }, bar.el, strip.el, feed.el);

    function signedIn() { return PT.auth.signedIn; }
    function stripChannels() { return signedIn() ? accountChannels : PT.store.subscriptions; }
    function ids() { return PT.store.subscriptions.map(function (c) { return c.id; }); }
    function refreshAll() {
      shownIds = ids();
      strip.set(stripChannels());
      feed.clear();
      feed.reload();
    }

    /** The account's own feed (TV client) plus its channel strip. */
    function fetchAccount() {
      feed.endpoint = 'tv';
      lastLoad = Date.now();
      return PT.api.get('acct/subscriptions', null, { auth: true }).then(function (r) {
        accountChannels = r.channels || [];
        // the feed's rows only name their channel; the strip knows the icons (see ChannelDirectory)
        accountChannels.forEach(PT.channelDirectory.learnChannel);
        strip.set(stripChannels());
        PT.store.mergeSubscriptions(accountChannels);
        return r.feed;
      });
    }

    /** Signed out: the subscriptions are stored on this device and the feed is built from each channel's Videos tab. */
    function fetchLocal() {
      feed.endpoint = 'browse';
      lastLoad = Date.now();
      var subs = PT.store.subscriptions.slice();
      if (!subs.length) return Promise.resolve({ items: [] });
      var chunks = [];
      for (var i = 0; i < subs.length; i += 30) chunks.push(subs.slice(i, i + 30).map(function (c) { return { id: c.id, name: c.name, avatar: c.avatar }; }));
      var all = [];
      var p = Promise.resolve();
      // two chunks at a time keep the server's load (and the wait) reasonable
      var results = [];
      for (var k = 0; k < chunks.length; k += 2) {
        (function (pair) {
          p = p.then(function () {
            return Promise.all(pair.map(function (c) { return PT.api.subsFeed(c).then(function (r) { return r.videos || []; }, function () { return []; }); }))
              .then(function (arrs) { arrs.forEach(function (a) { all = all.concat(a); }); });
          });
        })(chunks.slice(k, k + 2));
      }
      return p.then(function () {
        all.sort(function (a, b) { return a._age !== b._age ? a._age - b._age : a._order - b._order; });
        return { items: all.slice(0, 150).map(function (v) { return { type: 'video', video: v }; }) };
      });
    }

    shownIds = ids();
    strip.set(stripChannels());
    feed.reload();
    PT.on('accountChanged', function () { accountChannels = []; refreshAll(); });
    PT.on('store', function () {
      if (signedIn() || !el.parentNode) return;
      var now = ids();
      // changed while this tab is not on screen: reload when it is shown again
      if (now.join() !== shownIds.join() && !el.offsetParent) { shownIds = null; }
    });
    return {
      el: el, feed: feed,
      scrollToTop: function (smooth) { feed.scrollToTop(smooth); },
      onShow: function () {
        if (signedIn()) { if (Date.now() - lastLoad > 600000) refreshAll(); return; }
        if (!shownIds || ids().join() !== shownIds.join() || Date.now() - lastLoad > 600000) refreshAll();
      }
    };
  };

  /** "All channels" list with unsubscribe buttons, and the import of subscription files */
  S.channelsManager = function () {
    var feed = new PT.FeedView({ refresh: false, emptyTitle: PT.t('subs.empty') });
    function rebuild() { feed.setPage({ items: PT.store.subscriptions.map(function (c) { return { type: 'channel', channel: c }; }) }); }
    var file = h('input', { type: 'file', class: 'hidden-file', accept: '.csv,.json,.opml,.xml,.txt,text/*,application/json,application/xml' });
    var importBtn = h('button', { class: 'bar-text', type: 'button', text: PT.t('subs.import') });
    importBtn.addEventListener('click', function () { file.click(); });
    file.addEventListener('change', function () {
      var files = Array.prototype.slice.call(file.files || []);
      if (!files.length) return;
      Promise.all(files.map(function (f) { return readText(f); })).then(function (texts) {
        var all = [];
        texts.forEach(function (t) { all = all.concat(PT.parseSubscriptions(t)); });
        file.value = '';
        if (!all.length) { PT.toast(PT.t('subs.importFailed')); return; }
        importChannels(all, function (n) { PT.toast(PT.t('subs.imported', String(n))); });
      });
    });
    var scr = PT.navScreen(PT.t('subs.manage'), feed.el, { right: [importBtn, file] });
    var onStore = function () { rebuild(); };
    PT.on('store', onStore);
    rebuild();
    scr.destroy = function () { PT.off('store', onStore); feed.destroy(); };
    return scr;
  };

  function readText(f) {
    return new Promise(function (resolve) {
      var r = new FileReader();
      r.onload = function () { resolve(String(r.result || '')); };
      r.onerror = function () { resolve(''); };
      r.readAsText(f);
    });
  }

  /** Adds `channels` to the local subscriptions and fills in avatars / names in the background (3 at a time). */
  function importChannels(channels, done) {
    var merged = PT.store.subscriptions.slice();
    var known = {};
    merged.forEach(function (c) { known[c.id] = true; });
    var added = [];
    channels.forEach(function (c) { if (!known[c.id]) { known[c.id] = true; merged.push(c); added.push(c); } });
    PT.store.replaceSubscriptions(merged);
    done(added.length);
    var queue = added.slice(), running = 0;
    function pump() {
      while (running < 3 && queue.length) {
        running++;
        (function (c) {
          PT.api.channelBasics(c.id).then(function (info) {
            if (info && info.name) {
              var list = PT.store.subscriptions.slice();
              for (var i = 0; i < list.length; i++) {
                if (list[i].id === c.id) { list[i] = { id: info.id, name: info.name, handle: info.handle, avatar: info.avatar, subscribers: info.subscribers, videoCount: info.videoCount }; PT.store.replaceSubscriptions(list); break; }
              }
            }
          }, PT.noop).then(function () { running--; pump(); });
        })(queue.shift());
      }
    }
    pump();
  }

  /** Subscription files of other apps: Google Takeout CSV, NewPipe / Piped / FreeTube JSON, OPML; any channel id (UC...) otherwise. */
  PT.parseSubscriptions = function (text) {
    var found = {}, order = [];
    function add(id, name) {
      if (!found[id]) { found[id] = { id: id, name: name || '', handle: '', avatar: '', subscribers: '', videoCount: '' }; order.push(id); }
      else if (!found[id].name && name) found[id].name = name;
    }
    function firstId(strings) {
      for (var i = 0; i < strings.length; i++) {
        var m = /UC[0-9A-Za-z_-]{22}/.exec(strings[i] || '');
        if (m) return m[0];
      }
      return null;
    }
    var trimmed = text.trim();
    if (trimmed.charAt(0) === '{' || trimmed.charAt(0) === '[') {
      var root = null;
      try { root = JSON.parse(trimmed); } catch (e) { root = null; }
      (function walk(node) {
        if (Array.isArray(node)) { node.forEach(walk); return; }
        if (node && typeof node === 'object') {
          var sn = node.snippet || {};
          var id = firstId([node.channelId, node.id, node.url, sn.resourceId && sn.resourceId.channelId, node.xmlUrl].map(function (x) { return typeof x === 'string' ? x : ''; }));
          if (id) add(id, [node.name, node.title, sn.title].filter(function (x) { return typeof x === 'string' && x; })[0] || '');
          Object.keys(node).sort().forEach(function (k) { walk(node[k]); });
        }
      })(root);
    }
    if (!order.length && trimmed.indexOf(',') >= 0) {
      trimmed.split(/\r?\n/).forEach(function (line) {
        var id = firstId([line]);
        if (!id) return;
        var cols = [], cur = '', q = false;
        for (var i = 0; i < line.length; i++) {
          var ch = line.charAt(i);
          if (ch === '"') q = !q; else if (ch === ',' && !q) { cols.push(cur); cur = ''; } else cur += ch;
        }
        cols.push(cur);
        add(id, cols.length >= 3 ? cols[2] : '');
      });
    }
    if (!order.length && trimmed.indexOf('<outline') >= 0) {
      var re = /<outline[^>]*>/g, m;
      while ((m = re.exec(text)) !== null) {
        var tag = m[0], id2 = firstId([tag]);
        if (!id2) continue;
        var nm = /(?:text|title)="([^"]*)"/.exec(tag);
        add(id2, nm ? nm[1].replace(/&amp;/g, '&').replace(/&quot;/g, '"') : '');
      }
    }
    if (!order.length) {
      var re2 = /UC[0-9A-Za-z_-]{22}/g, m2;
      while ((m2 = re2.exec(text)) !== null) add(m2[0], '');
    }
    return order.map(function (id) { return found[id]; });
  };

  // ---------------------------------------------------------------------------------------------------------------
  // Library ("You" tab)
  // ---------------------------------------------------------------------------------------------------------------
  /**
   * Signed in, the history screens show the account's watch history, and the plays of this app that the account does not list
   * (not recorded, or not there yet) are put into it.
   *
   * The account's list says in which ORDER things were watched, not when; the plays of this app know their time.  A video that is in
   * both lists ties the two together (an "anchor").  Between the anchors the account's entries get a time in proportion to their
   * place, and a play that the account does not list goes where its time falls.  Putting them all in front (what this used to do)
   * is only right for a play of the last minutes: anything older that the first page does not show (it is further down the account's
   * list, or it is a Short inside a "Shorts" shelf) jumped to the top out of its place.
   *
   * The pages are merged one after the other, each against everything loaded before it, so a play older than what is loaded
   * appears when the list reaches its time (and at the very end of the list when the account never had it).
   */
  var HistoryMerge = {
    days: 30,
    limit: 40,                              // what is shown when the account's list cannot be loaded at all
    /** With nothing to compare with (no play of this app on the page), plays of the last two hours still go in front. */
    freshMs: 2 * 3600 * 1000,

    /** Plays of this app, newest first: [{video, t}]. */
    entries: function () {
      return PT.store.history.map(function (e) { return { video: e.video, t: e.watchedAt }; });
    },

    /** The videos of an account item: a video, or the Shorts of a shelf. */
    videosOf: function (it) {
      return it.type === 'video' ? [it.video] : (it.type === 'shorts' ? it.videos : []);
    },

    /**
     * A time for every video of the account's list (`ids`, in its order), from the ones this app played; null when none was.
     * The order is the true one: a time that rises on the way down was a replay somewhere else, so it only lifts those above it.
     */
    estimate: function (ids, byId, now) {
      var anchors = [], i, n = ids.length;
      for (i = 0; i < n; i++) { var e = byId[ids[i]]; if (e) anchors.push({ i: i, t: e.t }); }
      if (!anchors.length) return null;
      for (i = anchors.length - 2; i >= 0; i--) if (anchors[i].t < anchors[i + 1].t) anchors[i].t = anchors[i + 1].t;
      for (i = 0; i < anchors.length; i++) if (anchors[i].t > now) anchors[i].t = now;
      var ctrl = [{ i: -1, t: now }].concat(anchors), last = ctrl[ctrl.length - 1];
      var pace = Math.max(60000, (now - last.t) / (last.i + 1));          // below the last anchor: the pace of everything above it
      var est = new Array(n), c = 0;
      for (i = 0; i < n; i++) {
        while (c + 1 < ctrl.length && ctrl[c + 1].i <= i) c++;
        var lo = ctrl[c], hi = ctrl[c + 1];
        est[i] = hi ? lo.t + (hi.t - lo.t) * (i - lo.i) / (hi.i - lo.i) : lo.t - pace * (i - lo.i);
      }
      return est;
    },

    /**
     * One merge per list.  `session.page(items, last)` takes the account's items of the next page (`last`: there is no page after it)
     * and returns them with this app's plays in their places; `session.inserted` holds the ids of those plays.
     * Options (for tests): `entries`, `now`.
     */
    session: function (o) {
      o = o || {};
      var now = o.now !== undefined ? o.now : Date.now();
      var entries = o.entries || HistoryMerge.entries();
      var byId = {}, i;
      for (i = 0; i < entries.length; i++) {
        if (!(entries[i].t > 0)) continue;                                                 // no time, no place
        if (!byId[entries[i].video.id]) byId[entries[i].video.id] = entries[i];            // the newest play of a video
      }
      var cutoff = now - HistoryMerge.days * 86400000;
      var pending = entries.filter(function (e) { return e.t >= cutoff && byId[e.video.id] === e; });
      var ids = [], listed = {}, pages = 0;
      var s = { inserted: {} };

      function asItem(e) { s.inserted[e.video.id] = true; return { type: 'video', video: e.video }; }

      s.page = function (items, last) {
        var first = pages++ === 0, starts = [];
        items.forEach(function (it) {
          var vs = HistoryMerge.videosOf(it);
          starts.push(vs.length ? ids.length : -1);
          vs.forEach(function (v) { ids.push(v.id); listed[v.id] = true; });
        });
        pending = pending.filter(function (e) { return !listed[e.video.id]; });          // the account lists it after all
        if (!pending.length) return items;
        var est = HistoryMerge.estimate(ids, byId, now);
        var before = items.map(function () { return []; }), keep = [], tail = [];
        pending.forEach(function (e) {
          var k = -1, j;
          if (est) {
            for (j = 0; j < items.length; j++) if (starts[j] >= 0 && est[starts[j]] < e.t) { k = j; break; }
            // directly after the video that is newer: in front of the headers that lead to the older one, never above the first header
            var m = k;
            while (m > 0 && starts[m - 1] < 0) m--;
            if (k > 0 && m > 0) k = m;
          } else if (first && e.t >= now - HistoryMerge.freshMs && items.length) k = 0;
          if (k >= 0) before[k].push(e); else keep.push(e);
        });
        if (last) { tail = keep; keep = []; }                                              // the account's list is over: the rest is not in it
        pending = keep;
        var out = [];
        items.forEach(function (it, j) {
          before[j].forEach(function (e) { out.push(asItem(e)); });
          out.push(it);
        });
        tail.forEach(function (e) { out.push(asItem(e)); });
        return out;
      };
      return s;
    },

    /** The videos for a short shelf (the "You" tab): the account's, with this app's plays among them. */
    shelf: function (accountVideos, limit) {
      var s = HistoryMerge.session();
      var out = s.page(accountVideos.map(function (v) { return { type: 'video', video: v }; }), false);
      return out.map(function (it) { return it.video; }).slice(0, limit);
    }
  };
  PT.historyMerge = HistoryMerge;

  S.library = function () {
    var searchBtn = PT.iconButton('search', 24, 'bar-search', PT.t('search.placeholder'));
    var settingsBtn = PT.iconButton('settings_outline', 24, 'bar-settings', PT.t('library.settings'));
    searchBtn.addEventListener('click', function () { PT.router.openSearchScreen(); });
    settingsBtn.addEventListener('click', function () { PT.router.openSettings(); });
    var title = h('div', { class: 'bar-title big', text: PT.t('tab.you') });
    var accountHead = h('button', { class: 'acchead', type: 'button' });
    var shelfHost = h('div', { class: 'shelf-host' });
    var rowsHost = h('div', { class: 'lib-rows' });
    var scroller = h('div', { class: 'scroll lib' }, accountHead, shelfHost, rowsHost);
    var el = h('div', { class: 'screen-inner library' }, h('div', { class: 'bar' }, title, h('span', { class: 'grow' }), searchBtn, settingsBtn), scroller);
    var accountHistory = [], accountHistoryLoaded = 0;
    var lazy = PT.lazyLoader(null);

    function signedIn() { return PT.auth.signedIn; }

    function renderAccountHead() {
      accountHead.innerHTML = '';
      var p = PT.auth.profile;
      var av;
      if (signedIn()) {
        if (p && p.avatar) { av = PT.mkImg('avatar xl'); lazy.set(av, p.avatar); }
        else av = h('span', { class: 'avatar-ico', html: PT.iconSvg('account_circle', 52) });
        accountHead.appendChild(av);
        accountHead.appendChild(h('div', { class: 'acc-txt' }, h('div', { class: 'acc-name', text: (p && p.name) || PT.t('account.signedIn') }), h('div', { class: 'acc-sub', text: (p && p.handle) || '' })));
      } else {
        accountHead.appendChild(h('span', { class: 'avatar-ico', html: PT.iconSvg('account_circle_outline', 52) }));
        accountHead.appendChild(h('div', { class: 'acc-txt' }, h('div', { class: 'acc-name', text: PT.t('account.signIn') }), h('div', { class: 'acc-sub', text: PT.t('account.signInHint') })));
      }
      accountHead.appendChild(h('span', { class: 'acc-chev', html: PT.iconSvg('chevron_right', 22) }));
    }
    accountHead.addEventListener('click', function () {
      if (signedIn()) {
        var name = (PT.auth.profile && PT.auth.profile.name) || PT.t('account.signedIn');
        PT.sheet.show({ title: name, actions: [{ title: PT.t('account.signOut'), icon: 'logout', destructive: true, handler: function () { PT.account.signOut(); } }] });
      } else PT.nav.push(S.signIn());
    });

    function shelfVideos() {
      // (until the account's list has arrived, what was played here stands in for it)
      if (signedIn() && accountHistory.length) return HistoryMerge.shelf(accountHistory, 12);
      return PT.store.history.slice(0, 12).map(function (e) { return e.video; });
    }
    function renderShelf() {
      PT.clear(shelfHost);
      var vids = shelfVideos();
      if (!vids.length) return;
      var row = h('div', { class: 'hshelf-row' });
      vids.forEach(function (v) {
        var img = PT.mkImg('thumb-img');
        lazy.set(img, PT.thumbUrl(v));
        var f = PT.store.progress(v.id) || 0;
        var card = h('div', { class: 'hcard', role: 'button', tabindex: '0' },
          h('div', { class: 'thumb' }, img, h('span', { class: 'dur', text: v.duration, hidden: !v.duration }), h('i', { class: 'prog', style: 'width:' + Math.round(f * 100) + '%', hidden: f <= 0.01 })),
          h('div', { class: 'hc-title', text: v.title }), h('div', { class: 'hc-sub', text: v.channelName }));
        card.addEventListener('click', function () { PT.router.play(v); });
        row.appendChild(card);
      });
      var all = h('button', { class: 'bar-text', type: 'button', text: PT.t('library.viewAll') });
      all.addEventListener('click', function () { PT.nav.push(signedIn() ? S.accountList('history') : S.storedList('history')); });
      shelfHost.appendChild(h('div', { class: 'shelf' }, h('div', { class: 'shelf-head' }, h('span', { class: 'shelf-title', text: PT.t('library.history') }), all), row));
    }

    function rows() {
      var dm = PT.downloads, dcount = dm ? dm.records.length + Object.keys(dm.pending).length : 0;
      var s = PT.store;
      function n(x) { return x ? String(x) : null; }
      if (signedIn()) {
        return [
          ['history', PT.t('library.history'), null, function () { PT.nav.push(S.accountList('history')); }],
          ['file_download', PT.t('library.downloads'), n(dcount), function () { PT.nav.push(S.downloads()); }],
          ['playlist_play', PT.t('library.playlists'), null, function () { PT.nav.push(S.accountList('playlists')); }],
          ['watch_later_outline', PT.t('library.watchLater'), null, function () { PT.nav.push(S.accountList('watchLater')); }],
          ['thumb_up_outline', PT.t('library.liked'), null, function () { PT.nav.push(S.accountList('liked')); }],
          ['settings_outline', PT.t('library.settings'), null, function () { PT.router.openSettings(); }]
        ];
      }
      return [
        ['history', PT.t('library.history'), n(s.history.length), function () { PT.nav.push(S.storedList('history')); }],
        ['file_download', PT.t('library.downloads'), n(dcount), function () { PT.nav.push(S.downloads()); }],
        ['playlist_play', PT.t('library.playlists'), n(s.playlists.length), function () { PT.nav.push(S.userPlaylists()); }],
        ['watch_later_outline', PT.t('library.watchLater'), n(s.watchLater.length), function () { PT.nav.push(S.storedList('watchLater')); }],
        ['thumb_up_outline', PT.t('library.liked'), n(s.liked.length), function () { PT.nav.push(S.storedList('liked')); }],
        ['settings_outline', PT.t('library.settings'), null, function () { PT.router.openSettings(); }]
      ];
    }
    function renderRows() {
      PT.clear(rowsHost);
      rows().forEach(function (r) {
        var b = h('button', { class: 'librow', type: 'button' }, h('span', { class: 'lr-ico', html: PT.iconSvg(r[0], 24) }),
          h('span', { class: 'lr-title', text: r[1] }), h('span', { class: 'lr-count', text: r[2] || '' }), h('span', { class: 'lr-chev', html: PT.iconSvg('chevron_right', 22) }));
        b.addEventListener('click', r[3]);
        rowsHost.appendChild(b);
      });
    }
    function renderAll() {
      title.textContent = PT.t('tab.you');
      renderAccountHead(); renderShelf(); renderRows();
    }
    function loadAccountHistory() {
      if (!signedIn() || Date.now() - accountHistoryLoaded < 120000) return;
      accountHistoryLoaded = Date.now();
      PT.api.post('acct/browse', { browseId: 'FEhistory' }, { auth: true }).then(function (page) {
        if (!signedIn()) return;
        var vids = [];
        (page.items || []).forEach(function (it) { if (it.type === 'video') vids.push(it.video); else if (it.type === 'shorts') vids = vids.concat(it.videos); });
        accountHistory = vids.slice(0, 40);              // more than the 12 shown: the rest tells where this app's plays belong
        renderShelf();
      }, PT.noop);
    }
    PT.on('accountChanged', function () { accountHistory = []; accountHistoryLoaded = 0; renderAll(); loadAccountHistory(); });
    PT.on('accountProfile', renderAccountHead);
    PT.on('store', function () { renderShelf(); renderRows(); });
    PT.on('downloads', renderRows);
    PT.on('settings', renderAll);
    PT.on('theme', renderAll);
    renderAll();
    return {
      el: el,
      onShow: function () { loadAccountHistory(); renderShelf(); },
      scrollToTop: function (smooth) { try { scroller.scrollTo({ top: 0, behavior: smooth ? 'smooth' : 'auto' }); } catch (e) { scroller.scrollTop = 0; } }
    };
  };

  // stored lists: history, watch later, liked, a local playlist
  S.storedList = function (kind, playlistId) {
    var titles = { history: PT.t('library.history'), watchLater: PT.t('library.watchLater'), liked: PT.t('library.liked') };
    function pl() { return PT.store.playlists.filter(function (p) { return p.id === playlistId; })[0]; }
    function videos() {
      if (kind === 'history') return PT.store.history.map(function (e) { return e.video; });
      if (kind === 'watchLater') return PT.store.watchLater;
      if (kind === 'liked') return PT.store.liked;
      var p = pl(); return p ? p.videos : [];
    }
    var feed = new PT.FeedView({
      refresh: false, avatars: kind === 'history',
      emptyTitle: kind === 'history' ? PT.t('library.emptyHistory') : PT.t('common.empty'),
      play: function (v, fv) {
        if (kind === 'history') PT.router.play(v);
        else PT.router.play(v, fv.allVideos(), null);
      },
      extraActions: function (v) {
        if (kind === 'history') return [{ title: PT.t('video.notInterested'), icon: 'delete', handler: function () { PT.store.removeHistory(v.id); } }];
        if (kind === 'playlist') return [{ title: PT.t('common.delete'), icon: 'delete', handler: function () { PT.store.removeFromPlaylist(v.id, playlistId); } }];
        if (kind === 'liked') return [{ title: PT.t('common.delete'), icon: 'delete', handler: function () { PT.store.toggleLike(v); } }];
        return [];
      }
    });
    function rebuild() { feed.setPage({ items: videos().map(function (v) { return { type: 'video', video: v }; }) }); }
    var right = [];
    if (kind === 'history') {
      var del = h('button', { class: 'bar-text', type: 'button', text: PT.t('common.delete') });
      del.addEventListener('click', function () {
        PT.dialog.confirm(PT.t('library.confirmClear'), { okText: PT.t('common.delete'), destructive: true }).then(function (ok) { if (ok) PT.store.clearHistory(); });
      });
      right.push(del);
    }
    var scr = PT.navScreen(kind === 'playlist' ? (pl() ? pl().name : '') : titles[kind], feed.el, { right: right });
    var onStore = function () { rebuild(); };
    PT.on('store', onStore);
    rebuild();
    scr.destroy = function () { PT.off('store', onStore); feed.destroy(); };
    return scr;
  };

  /** The user's own (local) playlists. */
  S.userPlaylists = function () {
    var list = h('div', { class: 'ul-list scroll' });
    var add = PT.iconButton('add', 24, 'bar-add', PT.t('video.newPlaylist'));
    add.addEventListener('click', function () { PT.router.promptNewPlaylist(null); });
    function render() {
      PT.clear(list);
      PT.store.playlists.forEach(function (p) {
        var del = PT.iconButton('delete_outline', 22, 'ul-del', PT.t('common.delete'));
        var row = h('div', { class: 'ul-row', role: 'button', tabindex: '0' }, h('span', { class: 'ul-ico', html: PT.iconSvg('playlist_play', 28) }),
          h('div', { class: 'ul-txt' }, h('div', { class: 'ul-name', text: p.name }), h('div', { class: 'ul-sub', text: String(p.videos.length) })), del,
          h('span', { class: 'lr-chev', html: PT.iconSvg('chevron_right', 22) }));
        row.addEventListener('click', function () { PT.nav.push(S.storedList('playlist', p.id)); });
        del.addEventListener('click', function (e) {
          e.stopPropagation();
          PT.dialog.confirm(p.name, { okText: PT.t('common.delete'), destructive: true }).then(function (ok) { if (ok) PT.store.deletePlaylist(p.id); });
        });
        list.appendChild(row);
      });
      if (!PT.store.playlists.length) list.appendChild(h('div', { class: 'ul-empty', text: PT.t('library.emptyPlaylists') }));
    }
    var scr = PT.navScreen(PT.t('library.playlists'), list, { right: [add] });
    PT.on('store', render);
    render();
    scr.destroy = function () { PT.off('store', render); };
    return scr;
  };

  /** A list that lives in the signed-in account (history, Watch later, liked videos, playlists). */
  S.accountList = function (kind) {
    var browseId = { history: 'FEhistory', watchLater: 'VLWL', liked: 'VLLL', playlists: 'FEplaylist_aggregation' }[kind];
    var titles = { history: PT.t('library.history'), watchLater: PT.t('library.watchLater'), liked: PT.t('library.liked'), playlists: PT.t('library.playlists') };
    var merge = null;                                 // history: this app's plays among the account's entries (see HistoryMerge)
    var feed = new PT.FeedView({
      refresh: true, endpoint: 'tv', avatars: kind === 'history',
      emptyTitle: kind === 'history' ? PT.t('library.emptyHistory') : PT.t('common.empty'),
      play: function (v, fv) {
        if (kind === 'watchLater' || kind === 'liked') PT.router.play(v, fv.allVideos(), null);
        else PT.router.play(v);
      },
      fetchFirst: function () {
        feed.endpoint = 'tv';
        if (!PT.auth.signedIn) return Promise.reject(Object.assign(new Error(PT.t('account.signInRequired')), { code: 'auth' }));
        merge = kind === 'history' ? HistoryMerge.session() : null;
        return PT.api.post('acct/browse', { browseId: browseId }, { auth: true }).then(function (page) {
          if (merge) page.items = merge.page(page.items || [], !page.continuation);
          return page;
        }, function (e) {
          // the account's list could not be loaded: what was played here is better than nothing
          if (merge && e.code !== 'auth') return { items: merge.page([], true).slice(0, HistoryMerge.limit) };
          throw e;
        });
      },
      // the next pages of the account's list: this app's plays that belong between them come in as the list reaches their time
      fetchMore: function (token, endpoint) {
        return PT.api.continuation(token, endpoint).then(function (page) {
          if (merge) page.items = merge.page(page.items || [], !page.continuation);
          return page;
        });
      },
      extraActions: function (v) {
        if (kind === 'watchLater') return [{ title: PT.t('video.removeWatchLater'), icon: 'delete', handler: function () { PT.account.setWatchLater(v, false); feed.removeVideo(v.id); } }];
        if (kind === 'liked') return [{ title: PT.t('video.unlike'), icon: 'delete', handler: function () { PT.account.setLike(v, 'none'); feed.removeVideo(v.id); } }];
        if (kind === 'history' && merge && merge.inserted[v.id]) return [{ title: PT.t('video.notInterested'), icon: 'delete', handler: function () { PT.store.removeHistory(v.id); feed.removeVideo(v.id); } }];
        return [];
      }
    });
    var scr = PT.navScreen(titles[kind], feed.el, {});
    var onAcc = function () { feed.clear(); feed.reload(); };
    PT.on('accountChanged', onAcc);
    feed.reload();
    scr.destroy = function () { PT.off('accountChanged', onAcc); feed.destroy(); };
    return scr;
  };
})(window.PT);
