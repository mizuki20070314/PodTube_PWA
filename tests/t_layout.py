"""Light theme and the wide layouts (iPad portrait / landscape, desktop)."""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.makedirs(os.path.join(HERE, "shots"), exist_ok=True)
import cdp  # noqa: E402

URL = "http://localhost:8080/podtube/"


def run(name, w, h, mobile, light=False, watch=True):
    with cdp.Browser(size=(w + 40, h + 100), scale=1.0) as b:
        cdp.emulate(b, w, h, mobile=mobile, scale=1.0, touch=mobile)
        b.open(URL, wait=4)
        if light:
            b.js("PT.settings.theme = 'light'")
        b.pump(2.5)
        cols = b.js("(function(){var l=document.querySelector('.feed-list'); return getComputedStyle(l).gridTemplateColumns})()")
        print("%-10s home grid columns: %s" % (name, cols))
        b.shot("shots/ly_%s_home.png" % name)
        if watch:
            cdp.tap(b, w / 2, 160) if not mobile else cdp.tap(b, w / 2, 220)
            if not mobile:
                b.click(w / 2, 220)
            b.pump(8)
            print("%-10s split: %s  watch rect: %s  player: %s" % (name, b.js("document.querySelector('.watch').classList.contains('split')"),
                  b.js("JSON.stringify(document.querySelector('.watch').getBoundingClientRect())"),
                  b.js("JSON.stringify(document.querySelector('.w-player').getBoundingClientRect())")))
            b.shot("shots/ly_%s_watch.png" % name)


ONLY = sys.argv[1:]
for args in (("light", 390, 800, True, True, False), ("ipad_p", 820, 1180, True), ("ipad_l", 1180, 820, True), ("desktop", 1280, 800, False)):
    if not ONLY or args[0] in ONLY:
        run(*args)
