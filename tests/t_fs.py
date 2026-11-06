"""CSS full screen on a portrait phone (the player turned on its side) + light theme."""
import os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cdp  # noqa: E402

with cdp.Browser(size=(430, 900), scale=2.0) as b:
    cdp.emulate(b, 390, 800, mobile=True, scale=2.0)
    b.open("http://localhost:8080/podtube/", wait=4)
    b.js("PT.settings.theme = 'light'"); b.pump(1.5)
    b.shot("shots/fs_light_home.png")
    cdp.tap(b, 195, 200); b.pump(8)
    b.shot("shots/fs_light_watch.png")
    b.js("PT.watch.debugCssFullscreen(true)"); b.pump(1.2)
    print("rot:", b.js("PT.view.rot"), "watch rect:", b.js("JSON.stringify(document.querySelector('.watch').getBoundingClientRect())"))
    cdp.tap(b, 200, 400); b.pump(0.6)             # a tap anywhere on the (rotated) player shows the controls
    b.shot("shots/fs_rot.png")
    # scrub in rotated mode: the bar runs top-to-bottom on screen along the right edge... drag along it
    r = cdp.rect(b, ".seekbar"); print("seekbar screen rect:", r)
    t0 = b.js("PT.player.currentTime")
    cdp.swipe(b, r["x"] + r["w"] / 2, r["y"] + r["h"] * 0.1, r["x"] + r["w"] / 2, r["y"] + r["h"] * 0.5, steps=8)
    b.pump(1.5)
    print("rotated scrub: %.1f -> %.1f of %.1f" % (t0, b.js("PT.player.currentTime"), b.js("PT.player.duration")))
    b.js("PT.watch.debugCssFullscreen(false)"); b.pump(0.6)
    print("after exit rot:", b.js("PT.view.rot"))
