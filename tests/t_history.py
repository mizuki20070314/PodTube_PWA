"""The signed-in history: plays of this app among the account's entries (HistoryMerge in js/09a-screens.js).

The account's list gives the ORDER of what was watched, not the times; the plays of this app know their time.  A play the account
does not list used to be put in front of everything; that is only right for a play of the last minutes.  What this checks:
  * a video that sits inside a Shorts shelf of the account is "listed" (it used to be repeated at the top: a few videos out of place)
  * a play that is further down the account's list (a later page) does not jump to the top
  * a play the account never had goes where its time falls between the entries that are in both lists
  * the pages are merged one after the other, and what the account never had comes at the very end of the list
Then the history screen itself, with the account's pages faked.

usage: python tests/t_history.py [url]        (the dev server must run: python tests/devserver.py 8080)
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.makedirs(os.path.join(HERE, "shots"), exist_ok=True)
import cdp  # noqa: E402

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080/podtube/"
results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print("%s %-72s %s" % ("PASS" if ok else "FAIL", name, detail))


UNIT = r"""
(function () {
  var NOW = 1700000000000, M = 60000, H = 60 * M, D = 24 * H;
  function V(id) { return { id: id, title: id, channelName: 'c', thumbnail: '', duration: '1:00', views: '', published: '' }; }
  function E(id, minAgo) { return { video: V(id), t: NOW - minAgo * M }; }
  function A(ids) { return ids.map(function (id) { return { type: 'video', video: V(id) }; }); }
  function SH(ids) { return { type: 'shorts', videos: ids.map(V) }; }
  function show(items) {
    return items.map(function (it) {
      return it.type === 'video' ? it.video.id : it.type === 'shorts' ? '[' + it.videos.map(function (v) { return v.id; }).join(',') + ']' : '#' + (it.text || it.type);
    }).join(' ');
  }
  function run(entries, pages) {                       // pages: [[items, last], ...]
    var s = PT.historyMerge.session({ entries: entries, now: NOW });
    var out = pages.map(function (p) { return show(s.page(p[0], p[1])); });
    return { pages: out, inserted: Object.keys(s.inserted).sort().join(',') };
  }
  var R = {};

  // 1. a Short inside the account's Shorts shelf: listed, not repeated on top
  R.shorts = run([E('A', 5), E('S1', 30), E('C', 120)], [[[].concat(A(['A', 'B']), [SH(['S1', 'S2'])], A(['C'])), false]]);

  // 2. a play that is on a later page of the account's list: not on top of page 1, and not added again on page 2
  R.paging = run([E('A', 10), E('X', 3 * 1440)], [[A(['A', 'B', 'C']), false], [A(['D', 'X', 'E']), true]]);

  // 3. not in the account at all, between two anchors: goes between them
  R.between = run([E('A', 60), E('B', 180), E('C', 300), E('L', 120)], [[A(['N1', 'A', 'N2', 'B', 'N3', 'C', 'N4']), true]]);

  // 4. newer than everything: on top
  R.top = run([E('A', 10), E('L', 1)], [[A(['N1', 'A']), true]]);

  // 5. no anchor at all: a play of the last two hours is on top, an older one waits (and is last on the last page)
  R.noAnchorWaits = run([E('F', 30), E('O', 300)], [[A(['N1', 'N2', 'N3']), false]]);
  R.noAnchorEnd = run([E('F', 30), E('O', 300)], [[A(['N1', 'N2', 'N3']), true]]);

  // 6. a pending play is placed when a later page reaches its time
  R.later = run([E('A', 10), E('B', 200), E('P', 180)], [[A(['A', 'N1', 'N2']), false], [A(['N3', 'B']), true]]);

  // 7. two plays newer than the same entry keep their order (newest first)
  R.twoOnTop = run([E('A', 60), E('L1', 5), E('L2', 20)], [[A(['A', 'N1']), true]]);

  // 8. a time that rises on the way down (replayed elsewhere later) does not break anything
  R.lifted = run([E('A', 100), E('B', 20), E('L', 30)], [[A(['A', 'B', 'C']), true]]);

  // 9. nothing to add / older than 30 days / the same video twice in the local list
  R.none = run([], [[A(['A', 'B']), true]]);
  R.old = run([E('OLD', 31 * 1440)], [[A(['A', 'B']), true]]);
  R.empty = run([E('F', 3)], [[[], true]]);

  // 10. the account's list cannot be loaded: the plays of this app, newest first
  R.fallback = run([E('X', 5), E('Y', 50), E('Z', 500)], [[[], true]]);

  // 11. headers and other items stay where they were; a play is put before the first older VIDEO
  R.headers = run([E('A', 60), E('L', 90)], [[[{ type: 'text', text: 'today' }].concat(A(['A']), [{ type: 'text', text: 'older' }], A(['B'])), true]]);
  R.headerTop = run([E('A', 60), E('L', 5)], [[[{ type: 'text', text: 'today' }].concat(A(['A', 'B'])), true]]);

  // 12. the short shelf of the You tab
  var shelf = PT.historyMerge.shelf(A(['a1', 'a2', 'a3', 'a4']).map(function (x) { return x.video; }), 3);
  R.shelfLen = shelf.length;

  // the estimate itself
  var est = PT.historyMerge.estimate(['n', 'a', 'm', 'b'], { a: { t: NOW - 60 * M }, b: { t: NOW - 180 * M } }, NOW);
  R.est = est.map(function (t) { return Math.round((NOW - t) / M); });
  R.estNone = PT.historyMerge.estimate(['n', 'm'], {}, NOW);
  return JSON.stringify(R);
})()
"""

with cdp.Browser(size=(430, 900), scale=2.0) as b:
    cdp.emulate(b, 390, 800, mobile=True, scale=2.0)
    b.open(URL, wait=4)
    b.js("localStorage.clear()")
    b.js("PT.settings.uiLanguage = 'ja'")

    print("-- the merge, with made-up data and a fixed clock")
    raw = b.js(UNIT)
    try:
        R = json.loads(raw)
    except Exception:
        print(raw)
        sys.exit(1)

    check("Shorts shelf: a Short listed there is NOT put on top again", R["shorts"]["pages"][0] == "A B [S1,S2] C" and R["shorts"]["inserted"] == "", R["shorts"]["pages"][0])
    check("paging: a play further down the account's list stays off the top of page 1", R["paging"]["pages"][0] == "A B C", R["paging"]["pages"][0])
    check("paging: ... and is not added again on page 2", R["paging"]["pages"][1] == "D X E" and R["paging"]["inserted"] == "", R["paging"]["pages"][1])
    check("between two anchors: goes where its time falls", R["between"]["pages"][0] == "N1 A N2 L B N3 C N4", R["between"]["pages"][0])
    check("newer than everything: on top", R["top"]["pages"][0] == "L N1 A", R["top"]["pages"][0])
    check("no anchor: a play of the last two hours is on top; an older one waits", R["noAnchorWaits"]["pages"][0] == "F N1 N2 N3", R["noAnchorWaits"]["pages"][0])
    check("no anchor, last page: the older one comes at the very end", R["noAnchorEnd"]["pages"][0] == "F N1 N2 N3 O", R["noAnchorEnd"]["pages"][0])
    check("a pending play is placed when a later page reaches its time", R["later"]["pages"] == ["A N1 N2", "N3 P B"], str(R["later"]["pages"]))
    check("two plays above the same entry keep their order", R["twoOnTop"]["pages"][0] == "L1 L2 A N1", R["twoOnTop"]["pages"][0])
    check("a time that rises on the way down is tolerated", R["lifted"]["pages"][0].replace(" ", "").startswith("AB") and "L" in R["lifted"]["pages"][0], R["lifted"]["pages"][0])
    check("nothing local: the page is returned as it is", R["none"]["pages"][0] == "A B")
    check("older than 30 days: ignored", R["old"]["pages"][0] == "A B")
    check("an empty account page: the plays of this app, as the very end", R["empty"]["pages"][0] == "F", R["empty"]["pages"][0])
    check("account list unavailable: this app's plays, newest first", R["fallback"]["pages"][0] == "X Y Z", R["fallback"]["pages"][0])
    check("headers stay in place; a play follows the newer video, in front of the next header", R["headers"]["pages"][0] == "#today A L #older B", R["headers"]["pages"][0])
    check("the newest play goes under the first header, not above it", R["headerTop"]["pages"][0] == "#today L A B", R["headerTop"]["pages"][0])
    check("the shelf of the You tab is cut to its length", R["shelfLen"] == 3)
    check("estimate: in proportion between the anchors, extrapolated below", R["est"] == [30, 60, 120, 180], str(R["est"]))
    check("estimate: null without an anchor", R["estNone"] is None)

    # ------------------------------------------------------------------------------------------------------------------
    print("\n-- the history screen with a faked account (three pages)")
    b.js("""
      (function () {
        var NOW = Date.now(), M = 60000;
        function V(id) { return { id: id, title: 'T-' + id, channelName: 'c', channelId: '', channelAvatar: '', thumbnail: '', duration: '1:00', views: '', published: '', isLive: false, isUpcoming: false, isShort: /^S/.test(id) }; }
        function A(ids) { return ids.map(function (id) { return { type: 'video', video: V(id) }; }); }
        function SH(ids) { return { type: 'shorts', videos: ids.map(V) }; }
        // what this app played (newest first), with the times it played them
        var plays = [['C1', 2], ['SX', 40], ['B2', 90], ['U1', 130], ['OLD', 4 * 1440]];
        PT.store.history.length = 0;
        plays.forEach(function (p) { PT.store.history.push({ video: V(p[0]), watchedAt: NOW - p[1] * M, position: 0, duration: 60 }); });
        // the account's list: C1 is recorded and on top; a Short shelf holds SX; B2 is recorded; U1 was never recorded; OLD is on page 3
        window.__pages = {
          first: { items: [].concat(A(['O1', 'C1']), [SH(['SX', 'S9'])], A(['O2', 'B2', 'O3'])), continuation: 'tok2' },
          tok2: { items: A(['O4', 'O5', 'O6']), continuation: 'tok3' },
          tok3: { items: A(['O7', 'OLD', 'O8']), continuation: null }
        };
        window.__calls = [];
        var origPost = PT.api.post;
        PT.api.post = function (route, body, opts) {
          if (route === 'acct/browse' && body && body.browseId === 'FEhistory') { __calls.push('browse'); return Promise.resolve(JSON.parse(JSON.stringify(__pages.first))); }
          if (route === 'continuation' && body && __pages[body.token]) { __calls.push(body.token); return Promise.resolve(JSON.parse(JSON.stringify(__pages[body.token]))); }
          if (route.indexOf('acct/') === 0 || route.indexOf('auth/') === 0) return Promise.resolve({});
          return origPost.apply(PT.api, arguments);
        };
        PT.auth.setProfile({ name: 'Test', handle: '@test', avatar: '' });
        PT.auth.adopt({ accessToken: 'x', refreshToken: 'y', expiresIn: 3600 });
      })()
    """)
    b.js("PT.nav.push(PT.screens.accountList('history'))"); b.pump(2.5)
    order = b.js("(function(){var sc=document.querySelector('.screen:not(.under)');var out=[];"
                 "Array.prototype.forEach.call(sc.querySelectorAll('.vcard, .shorts-shelf, .shelf-shorts, [class*=shorts]'),function(e){"
                 "if(e.classList.contains('vcard'))out.push(e.getAttribute('data-id')||(e._video&&e._video.id));});return out})()")
    print("   first page, as shown:", order)
    check("screen: C1 (recorded) keeps its place; SX is not repeated on top", isinstance(order, list) and order[:2] == ["O1", "C1"], str(order[:4]))
    check("screen: U1 (never recorded, 130 min ago) is not put on top of page 1", isinstance(order, list) and "U1" not in order[:3], str(order))
    check("screen: OLD (on page 3 of the account) is not shown yet", isinstance(order, list) and "OLD" not in order)
    b.shot("shots/history_merge_page1.png")
    # scroll to load the other pages
    for _ in range(4):
        b.js("var s=document.querySelector('.screen:not(.under) .scroll.feed'); s.scrollTop = s.scrollHeight"); b.pump(1.2)
    allids = b.js("Array.prototype.map.call(document.querySelectorAll('.screen:not(.under) .vcard'),function(e){return e.getAttribute('data-id')||(e._video&&e._video.id)})")
    print("   all pages, as shown:", allids)
    check("screen: pages 2 and 3 were loaded through the continuation", b.js("__calls.join(',')") == "browse,tok2,tok3", b.js("__calls.join(',')"))
    check("screen: OLD appears once, at its place in the account's list (page 3)", isinstance(allids, list) and allids.count("OLD") == 1 and allids.index("OLD") == allids.index("O7") + 1, str(allids))
    check("screen: U1 comes at its time: after B2 (90 min), where page 2 reaches 130 min", isinstance(allids, list) and "U1" in allids and allids.index("U1") > allids.index("B2"), str(allids))
    check("screen: nothing is listed twice", isinstance(allids, list) and len(allids) == len(set(allids)), "")
    b.js("PT.nav.popToRoot()"); b.pump(0.5)

    print("\n-- the shelf of the You tab")
    b.js("document.querySelectorAll('.tabitem')[3].click()"); b.pump(2.5)
    shelf = b.js("Array.prototype.map.call(document.querySelectorAll('.library .hcard .hc-title'),function(e){return e.textContent})")
    print("   shelf:", shelf)
    check("shelf: the account's newest entries lead, in its order", isinstance(shelf, list) and shelf[:2] == ["T-O1", "T-C1"], str(shelf[:4]))
    check("shelf: plays of this app that the first page does not reach are not put in front", isinstance(shelf, list) and "T-U1" not in shelf and "T-OLD" not in shelf, str(shelf))
    b.shot("shots/history_merge_shelf.png")

    errs = [m for m in b.console_messages() if m.startswith(("EXCEPTION", "error"))]
    check("no script errors in the console", not errs, str(errs[:3]))

print("\n%d/%d passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
