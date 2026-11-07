"""When YouTube refuses the server's IP (api.cgi/play answers 429 `botcheck`), the video plays in YouTube's own embedded player,
which goes out over THIS device's connection.  `PT.api.play` is made to answer `botcheck`, the rest (YouTube's embed, the watch page)
is real.

What is checked: the switch itself; the state follows the embed (play / pause / seek / the clock); the mini player keeps it going;
"the server was refused" is remembered for five minutes (new videos go straight to the embed, the server is not asked again);
the next video of a queue starts when the embed ends; an embed that cannot play (the owner forbids embedding, the API script not
loading) ends in a message and a way out to YouTube; the setting that turns the switch off; and the way back once the server is
let through again.

usage: python tests/t_embed.py [url]        (the dev server must run: python tests/devserver.py 8080)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.makedirs(os.path.join(HERE, "shots"), exist_ok=True)
import cdp  # noqa: E402

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080/podtube/"
ZOO = "jNQXAC9IVRw"            # 19 seconds
RICK = "dQw4w9WgXcQ"
results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print("%s %-74s %s" % ("PASS" if ok else "FAIL", name, detail))


def st(b):
    return b.js("PT.player.state")


def t(b):
    return b.js("+PT.player.currentTime.toFixed(1)")


def iframe_src(b):
    return b.js("(document.querySelector('.embed-layer iframe')||{}).src || ''")


def wait_state(b, want, secs=15):
    waited = 0.0
    while waited < secs:
        if st(b) == want:
            return True
        b.pump(0.5)
        waited += 0.5
    return st(b) == want


with cdp.Browser(size=(430, 900), scale=1.0) as b:
    cdp.emulate(b, 390, 800, mobile=True, scale=1.0)
    b.open(URL, wait=4)
    b.js("localStorage.clear()")
    b.js("PT.settings.uiLanguage = 'ja'")
    # the server's answer when YouTube refuses its IP
    b.js("window.__plays = 0; window.__origPlay = PT.api.play; "
         "PT.api.play = function (id) { __plays++; var e = new Error('bot'); e.code = 'botcheck'; return Promise.reject(e); }")

    print("-- the switch")
    b.js("PT.router.play({id:'%s', title:'Me at the zoo', channelName:'jawed'})" % ZOO)
    ok = wait_state(b, "playing", 20)
    check("the server is refused -> the video plays in the embedded player", ok and b.js("PT.player.embedActive") is True, "state=%s" % st(b))
    check("  ... the iframe is YouTube's own embed of that video", "youtube.com/embed/" + ZOO in iframe_src(b), iframe_src(b)[:70])
    check("  ... the server was asked once", b.js("__plays") == 1)
    check("  ... the source is named", b.js("PT.player.sourceName") == "YouTube embed")
    check("  ... the app's controls give way to the embed's", b.js("getComputedStyle(document.querySelector('.ctl')).display") == "none")
    banner = b.js("(function(){var e=document.querySelector('.embed-bar');return {hidden:e.hidden,title:e.querySelector('.eb-title').textContent,note:e.querySelector('.eb-note').textContent,href:e.querySelector('.eb-open').href}})()")
    check("  ... the note says why, and links to YouTube itself", isinstance(banner, dict) and not banner["hidden"] and "制限" in banner["title"] and banner["href"] == "https://www.youtube.com/watch?v=" + ZOO, str(banner)[:110])
    b.shot("shots/embed_playing.png")
    t0 = t(b); b.pump(2.5); t1 = t(b)
    check("the clock follows the embed", t1 > t0 + 1.5, "%s -> %s of %s" % (t0, t1, b.js("+PT.player.duration.toFixed(0)")))
    check("the length is known (the zoo video: 19 s)", 15 < b.js("PT.player.duration") < 25)

    print("-- transport")
    b.js("PT.player.toggle()"); b.pump(1.5)
    check("toggle -> paused", st(b) == "paused", st(b))
    p0 = t(b); b.pump(2.0); p1 = t(b)
    check("  ... and the clock stands still", abs(p1 - p0) < 0.4, "%s -> %s" % (p0, p1))
    b.js("PT.player.toggle()")
    check("toggle again -> playing", wait_state(b, "playing", 8), st(b))
    b.js("PT.player.seek(12)"); b.pump(1.8)
    check("seek(12) -> the embed jumps", t(b) >= 11.5, "t=%s" % t(b))

    print("-- the mini player")
    b.js("PT.watch.setMinimized(true, false)"); b.pump(0.6)
    m0 = t(b); b.pump(1.5); m1 = t(b)
    check("minimised: the embed goes on", st(b) in ("playing", "buffering") and (m1 > m0 + 0.8 or st(b) == "ended"), "%s -> %s state=%s" % (m0, m1, st(b)))
    check("  ... a tap on the mini player is not swallowed by the embed", b.js("document.querySelector('.embed-layer').style.pointerEvents") == "none")
    b.js("PT.watch.setMinimized(false, false)"); b.pump(0.6)
    check("expanded again: the embed takes touches again", b.js("document.querySelector('.embed-layer').style.pointerEvents") == "")
    check("the chevron on the embed is the way back to the mini player", b.js("!!document.querySelector('.embed-layer .embed-collapse')") is True)
    b.js("document.querySelector('.embed-collapse').click()"); b.pump(0.8)
    check("  ... and it minimises", b.js("PT.watch.progress") > 0.5)
    b.js("PT.watch.setMinimized(false, false)"); b.pump(0.5)

    print("-- the refusal is remembered")
    b.js("PT.router.play({id:'%s', title:'Rick', channelName:'x'})" % RICK)
    ok = wait_state(b, "playing", 20)
    check("the next video goes straight to the embed", ok and "youtube.com/embed/" + RICK in iframe_src(b), iframe_src(b)[-40:])
    check("  ... without asking the server again", b.js("__plays") == 1, "asked %s times" % b.js("__plays"))
    check("  ... one iframe only (the old embed was torn down)", b.js("document.querySelectorAll('.embed-layer iframe').length") == 1)
    check("  ... remembered for about five minutes", 200000 < b.js("PT.ls.get('restrictedUntil', 0) - Date.now()") <= 300000, str(b.js("PT.ls.get('restrictedUntil', 0) - Date.now()")))
    check("history: what was watched in the embed is in the history", b.js("PT.store.history.slice(0,2).map(function(e){return e.video.id}).join(',')") == RICK + "," + ZOO)

    print("-- the next video of a queue")
    b.js("PT.router.play({id:'%s', title:'Me at the zoo', channelName:'jawed'}, [{id:'%s', title:'Me at the zoo'}, {id:'%s', title:'Rick'}], null)" % (ZOO, ZOO, RICK))
    wait_state(b, "playing", 20)
    b.js("PT.player.seek(16)")
    waited = 0
    while waited < 25 and b.js("PT.player.current && PT.player.current.id") != RICK:
        b.pump(1.0); waited += 1
    check("the embed ends -> the next video of the queue starts (autoplay)", b.js("PT.player.current && PT.player.current.id") == RICK, "after %ss" % waited)
    check("  ... in the embed", wait_state(b, "playing", 15) and b.js("PT.player.embedActive") is True)

    print("-- an embed that cannot play")
    b.js("window.__openReal = PT.embed.open; "
         "PT.embed.open = function (id, o) { setTimeout(function () { o.onError(150); }, 50); return { destroy: function () {}, time: function () { return 0; }, duration: function () { return 0; }, play: function () {}, pause: function () {}, seek: function () {}, setSpeed: function () {}, state: function () { return -1; } }; }")
    b.js("PT.router.play({id:'NOEMBED00001', title:'Not embeddable', channelName:'x'})"); b.pump(2.0)
    check("owner forbids embedding (error 150) -> a message, not a silent black box", st(b) == "failed" and "埋め込み" in (b.js("PT.player.errorMessage") or ""), b.js("PT.player.errorMessage"))
    check("  ... no embed left over", b.js("PT.player.embedActive") is False and b.js("!document.querySelector('.embed-layer').children.length || document.querySelector('.embed-layer').hidden") is True)
    banner = b.js("(function(){var e=document.querySelector('.embed-bar');return {hidden:e.hidden,href:e.querySelector('.eb-open').href}})()")
    check("  ... the way out to YouTube stays", isinstance(banner, dict) and not banner["hidden"] and banner["href"].endswith("NOEMBED00001"), str(banner))
    b.js("PT.embed.open = function (id, o) { setTimeout(function () { o.onError(-1); }, 50); return { destroy: function () {} }; }")
    b.js("PT.router.play({id:'NOEMBED00002', title:'x', channelName:'x'})"); b.pump(2.0)
    check("the API script cannot be loaded -> a message too", st(b) == "failed" and "埋め込みプレーヤー" in (b.js("PT.player.errorMessage") or ""), b.js("PT.player.errorMessage"))
    b.js("PT.embed.open = window.__openReal")

    print("-- the setting")
    b.js("PT.settings.embedFallback = false; PT.ls.set('restrictedUntil', 0)")
    b.js("PT.router.play({id:'%s', title:'Rick', channelName:'x'})" % RICK); b.pump(2.5)
    check("switched off: the old message, no embed", st(b) == "failed" and "制限" in (b.js("PT.player.errorMessage") or "") and b.js("document.querySelectorAll('.embed-layer iframe').length") == 0, b.js("PT.player.errorMessage"))
    banner = b.js("(function(){var e=document.querySelector('.embed-bar');return {hidden:e.hidden,note:e.querySelector('.eb-note').hidden}})()")
    check("  ... the link to YouTube is still offered", isinstance(banner, dict) and not banner["hidden"] and banner["note"] is True, str(banner))
    b.shot("shots/embed_off.png")
    b.js("PT.settings.embedFallback = true")

    print("-- the way back")
    b.js("PT.api.play = window.__origPlay")
    b.js("PT.player.retry()")
    ok = wait_state(b, "playing", 25)
    check("the server let through again -> the normal player", ok and b.js("PT.player.embedActive") is False and b.js("PT.player.sourceName").startswith("HLS"), "%s / %s" % (st(b), b.js("PT.player.sourceName")))
    check("  ... the embed is gone and the memory is cleared", b.js("document.querySelectorAll('.embed-layer iframe').length") == 0 and b.js("PT.ls.get('restrictedUntil', 0)") == 0)
    check("  ... the app's own controls are back", b.js("getComputedStyle(document.querySelector('.ctl')).display") != "none")
    b.shot("shots/embed_back.png")

    print("-- a Short while the server is refused")
    b.js("PT.watch.closePlayer()"); b.pump(1.0)
    b.js("PT.api.play = function (id) { var e = new Error('bot'); e.code = 'botcheck'; return Promise.reject(e); }")
    b.js("document.querySelectorAll('.tabitem')[1].click()"); b.pump(7)
    notice = b.js("(function(){var n=document.querySelector('.short .sh-notice:not([hidden])');"
                  "return n ? {text:n.querySelector('.sh-notice-text').textContent, href:n.querySelector('a').href} : null})()")
    check("the Short says why it does not play, and offers YouTube", isinstance(notice, dict) and "制限" in notice["text"]
          and notice["href"].startswith("https://www.youtube.com/shorts/"), str(notice)[:110])
    b.shot("shots/embed_short.png")
    b.js("PT.api.play = window.__origPlay"); b.js("document.querySelectorAll('.tabitem')[0].click()"); b.pump(0.5)

    errs = [m for m in b.console_messages() if m.startswith(("EXCEPTION", "error"))]
    check("no script errors in the console", not errs, str(errs[:3]))

print("\n%d/%d passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
