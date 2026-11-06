"""Controls, settings sheets, mini player, comments, scrubbing, fullscreen."""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.makedirs(os.path.join(HERE, "shots"), exist_ok=True)
import cdp  # noqa: E402

URL = "http://localhost:8080/podtube/"
STATE = """JSON.stringify({state: PT.player.state, t: +PT.player.currentTime.toFixed(1), h: PT.player.video.videoHeight, cap: PT.player.maxHeight,
  prog: +PT.watch.progress.toFixed(2), vol: PT.player.video.volume, sb: !!PT.player.storyboard, speed: PT.player.video.playbackRate,
  ctlChrome: document.querySelector('.ctl').classList.contains('chrome'), sheet: !!document.querySelector('.sheet-root'), errs: window.__errs})"""


def S(b, label):
    print("%-26s %s" % (label, b.js(STATE)))


def shot(b, name):
    return b.shot("shots/" + name + ".png")


with cdp.Browser(size=(430, 900), scale=2.0) as b:
    cdp.emulate(b, 390, 800, mobile=True, scale=2.0)
    b.open(URL, wait=5)
    b.js("window.__errs = []; window.addEventListener('error', e => __errs.push(e.message)); window.addEventListener('unhandledrejection', e => __errs.push('rej: ' + (e.reason && e.reason.message || e.reason)))")
    # open the second card so that it is a long video with chapters/storyboards if possible
    cdp.tap(b, 195, 200)
    b.pump(7)
    S(b, "playing")
    # 1. controls appear on a tap on the player
    cdp.tap(b, 195, 110); b.pump(0.6)
    S(b, "tap on player"); shot(b, "w2_controls")
    # 2. settings sheet
    print("settings btn:", cdp.tap_sel(b, ".ctl-set")); b.pump(0.6)
    S(b, "settings sheet"); shot(b, "w2_settings")
    # 3. quality sheet -> 360p
    rows = b.js("Array.from(document.querySelectorAll('.sheet-row .t')).map(e=>e.textContent)")
    print("settings rows:", rows)
    cdp.tap_sel(b, ".sheet-row", 0); b.pump(0.6)       # quality
    print("quality rows:", b.js("Array.from(document.querySelectorAll('.sheet-row .t')).map(e=>e.textContent)"))
    shot(b, "w2_quality")
    idx = b.js("Array.from(document.querySelectorAll('.sheet-row .t')).findIndex(e=>e.textContent==='360p')")
    cdp.tap_sel(b, ".sheet-row", idx); b.pump(4)
    S(b, "after 360p")
    # 4. speed 1.5x via API (sheet already tested) and stats overlay
    b.js("PT.player.setSpeed(1.5); PT.player.showsStats = true; PT.watch.controls().refreshStats(); PT.watch.controls().setVisible(true)")
    b.pump(1.2); S(b, "speed + stats"); shot(b, "w2_stats")
    b.js("PT.player.setSpeed(1); PT.player.showsStats = false; PT.watch.controls().refreshStats()")
    # 5. collapse to the mini player
    print("collapse:", cdp.tap_sel(b, ".ctl-collapse")); b.pump(1.0)
    S(b, "minimised"); shot(b, "w2_mini")
    # 6. expand again by tapping the mini bar text
    cdp.tap(b, 200, b.js("document.querySelector('.w-mini').getBoundingClientRect().top + 28")); b.pump(1.0)
    S(b, "expanded again")
    # 7. comments panel
    print("comments card:", cdp.tap_sel(b, ".wh-comments")); b.pump(2.5)
    S(b, "comments open"); shot(b, "w2_comments")
    print("comments:", b.js("document.querySelectorAll('.comment').length"))
    print("close:", cdp.tap_sel(b, ".cp-close")); b.pump(0.6)
    # 8. scrub with the film strip: finger down on the bar, slide up, then sideways
    cdp.tap(b, 195, 110); b.pump(0.5)
    r = cdp.rect(b, ".seekbar")
    print("seekbar rect:", r)
    y = r["y"] + r["h"] / 2
    cdp.touch(b, "touchStart", r["x"] + r["w"] * 0.3, y)
    for i in range(1, 7):
        cdp.touch(b, "touchMove", r["x"] + r["w"] * (0.3 + 0.02 * i), y - 12 * i); time.sleep(0.05)
    b.pump(1.2)
    S(b, "scrubbing (fine)"); shot(b, "w2_scrub")
    print("strip tiles:", b.js("document.querySelectorAll('.fs-tile').length"), "pill:", b.js("document.querySelector('.ctl-pill').textContent"))
    cdp.touch(b, "touchEnd", r["x"] + r["w"] * 0.42, y - 72); b.pump(2)
    S(b, "scrub end")
    # 9. double tap on the right third = +10 s
    t0 = b.js("PT.player.currentTime")
    cdp.tap(b, 330, 110); time.sleep(0.12); cdp.tap(b, 330, 110); b.pump(1.0)
    print("double tap right: %.1f -> %.1f" % (t0, b.js("PT.player.currentTime")))
    # 10. fullscreen (CSS, rotated on a portrait phone)
    b.js("PT.watch.toggleFullscreen()"); b.pump(1.0)
    S(b, "fullscreen"); shot(b, "w2_fullscreen")
    print("rot:", b.js("PT.view.rot"), "watch rect:", b.js("JSON.stringify(document.querySelector('.watch').getBoundingClientRect())"))
    b.js("PT.watch.exitFullscreen()"); b.pump(0.6)
    S(b, "after fullscreen")
    print("errs:", b.js("JSON.stringify(__errs)"))
    for m in b.console_messages():
        if "Tracking Prevention" not in m and "Manifest" not in m:
            print("  console:", m[:300])
