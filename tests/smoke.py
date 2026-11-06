"""Opens the PWA in a phone-sized headless Edge and reports what happened (screenshot in tests/shots/)."""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.makedirs(os.path.join(HERE, "shots"), exist_ok=True)
import cdp  # noqa: E402

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080/podtube/"

with cdp.Browser(size=(430, 900), scale=2.0) as b:
    cdp.emulate(b, 390, 800, mobile=True, scale=2.0)
    b.open(URL, wait=6)
    print("title:", b.js("document.title"))
    print("cards:", b.js("document.querySelectorAll('.vcard').length"), "| chips:", b.js("document.querySelectorAll('.chip').length"))
    print("errors:", b.js("window.__errs ? window.__errs.length : 'n/a'"))
    for m in b.console_messages():
        print("  console:", m[:300])
    print("shot:", b.shot("shots/smoke_home.png"))
