"""Open a video from the home feed and play it: watch page, controls, mini player."""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.makedirs(os.path.join(HERE, "shots"), exist_ok=True)
import cdp  # noqa: E402

URL = "http://localhost:8080/podtube/"
STATE = """JSON.stringify({state: PT.player.state, t: +PT.player.currentTime.toFixed(2), dur: +PT.player.duration.toFixed(1),
  ready: PT.player.video.readyState, w: PT.player.video.videoWidth, h: PT.player.video.videoHeight, src: (PT.player.video.currentSrc||'').slice(0,60),
  err: PT.player.errorMessage, title: PT.player.current && PT.player.current.title, prog: +PT.watch.progress.toFixed(2), eng: PT.player.sourceName,
  buffered: +PT.player.bufferedEnd.toFixed(1), live: PT.player.isLive})"""


def show(b, label):
    print(label, b.js(STATE))


with cdp.Browser(size=(430, 900), scale=2.0) as b:
    cdp.emulate(b, 390, 800, mobile=True, scale=2.0)
    b.js("window.__errs = []; window.addEventListener('error', e => __errs.push(e.message + ' @' + e.filename + ':' + e.lineno)); window.addEventListener('unhandledrejection', e => __errs.push('rej: ' + (e.reason && e.reason.message || e.reason)))")
    b.open(URL, wait=6)
    b.js("window.__errs = []; window.addEventListener('error', e => __errs.push(e.message + ' @' + e.filename + ':' + e.lineno)); window.addEventListener('unhandledrejection', e => __errs.push('rej: ' + (e.reason && e.reason.message || e.reason)))")
    cdp.tap(b, 195, 200)                      # first card's thumbnail
    for i in range(5):
        b.pump(2)
        show(b, "t+%ds" % ((i + 1) * 2))
    print("shot:", b.shot("shots/watch_1.png"))
    print("errs:", b.js("JSON.stringify(__errs)"))
    for m in b.console_messages():
        if "Tracking Prevention" not in m:
            print("  console:", m[:300])
