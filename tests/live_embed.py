"""End to end on the deployed site, nothing faked: a video that the server's IP is refused for (YouTube answers `botcheck`) must play in
YouTube's embedded player over THIS machine's connection.  Which videos the server is refused for changes from hour to hour (it is
YouTube's judgement of the server's IP), so the check asks the real server about a few videos and then plays the first refused one;
when the server is not refused for any of them there is nothing to switch and the check says so.

usage: PT_KEY=<access key> python tests/live_embed.py [url]       url defaults to https://my-dev.sakura.ne.jp/podtube/
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cdp  # noqa: E402

URL = sys.argv[1] if len(sys.argv) > 1 else "https://my-dev.sakura.ne.jp/podtube/"
KEY = os.environ.get("PT_KEY", "")
if not KEY:
    sys.exit("set PT_KEY")
CANDIDATES = ["T5EZXMH9W3M", "jNQXAC9IVRw", "9bZkp7q19f0", "kJQP7kiw5Fk"]
results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print("%s %-70s %s" % ("PASS" if ok else "FAIL", name, detail))


with cdp.Browser(size=(430, 900), scale=1.0) as b:
    cdp.emulate(b, 390, 800, mobile=True, scale=1.0)
    b.open(URL + "#key=" + KEY, wait=7)
    b.js("PT.settings.uiLanguage = 'ja'; PT.ls.set('restrictedUntil', 0)")
    # ask the real server (a failing play is cheap to look at: it is a 429 after a few seconds)
    refused = None
    for vid in CANDIDATES:
        code = b.js("PT.api.play('%s').then(function () { return 'ok'; }, function (e) { return e.code || 'error'; })" % vid)
        print("   server, %s: %s" % (vid, code))
        if code == "botcheck":
            refused = vid
            break
    if refused is None:
        print("   the server is not refused for any of these videos right now: nothing to switch (not a failure)")
        sys.exit(0)
    b.js("PT.ls.set('restrictedUntil', 0)")
    b.js("window.__codes = []; window.__orig = PT.api.play; PT.api.play = function (id) { return __orig.apply(PT.api, arguments).then(function (r) { __codes.push('ok'); return r; }, function (e) { __codes.push(e.code); throw e; }); }")
    b.js("PT.router.play({id:'%s', title:'refused video', channelName:'x'})" % refused)
    waited = 0
    while waited < 40 and b.js("PT.player.state") != "playing":
        b.pump(1.0); waited += 1
    check("a video the server is refused for plays", b.js("PT.player.state") == "playing", "after %ss" % waited)
    check("  ... the server really answered botcheck", b.js("__codes.join(',')") == "botcheck", b.js("__codes.join(',')"))
    check("  ... in YouTube's embedded player", b.js("PT.player.embedActive") is True and b.js("(document.querySelector('.embed-layer iframe')||{}).src || ''").find("/embed/" + refused) > 0)
    t0 = b.js("+PT.player.currentTime.toFixed(1)"); b.pump(3.0); t1 = b.js("+PT.player.currentTime.toFixed(1)")
    check("  ... and it is really playing", t1 > t0 + 2, "%s -> %s" % (t0, t1))
    b.shot("shots/live_embed.png")

print("\n%d/%d passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
