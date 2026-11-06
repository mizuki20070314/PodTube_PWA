"""The access-key gate of a deployed site, seen by a first-time visitor (a fresh headless Edge profile each time).

usage: PT_KEY=<access key> python tests/live_gate.py [url]       url defaults to https://my-dev.sakura.ne.jp/podtube/
(the key comes from the environment so that it never ends up in a file)
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.makedirs(os.path.join(HERE, "shots"), exist_ok=True)
import cdp  # noqa: E402

URL = sys.argv[1] if len(sys.argv) > 1 else "https://my-dev.sakura.ne.jp/podtube/"
KEY = os.environ.get("PT_KEY", "")
if not KEY:
    sys.exit("set PT_KEY")
results = []


def check(name, ok, detail=""):
    results.append(ok)
    print("%s %-52s %s" % ("PASS" if ok else "FAIL", name, detail))


def cards(b):
    return b.js("document.querySelectorAll('.vcard').length")


def gate_shown(b):
    return b.js("!!document.querySelector('.gate-input')")


def submit(b, text):
    b.js("var i=document.querySelector('.gate-input'); i.value=%s; document.querySelector('.gate .btn-pill').click()" % json.dumps(text))


# --- 1. a visitor without a key: gate, wrong key, right key, reload
with cdp.Browser(size=(430, 900), scale=2.0) as b:
    cdp.emulate(b, 390, 800, mobile=True, scale=2.0)
    b.open(URL, wait=6)
    check("gate is shown (no key)", gate_shown(b) is True)
    check("no video cards before the key", cards(b) == 0)
    b.shot("shots/live_gate_1_gate.png")
    submit(b, "not-the-key")
    time.sleep(3)
    msg = b.js("document.querySelector('.gate-msg').textContent")
    check("wrong key: message shown, gate stays", bool(msg) and gate_shown(b) is True, repr(msg))
    submit(b, KEY)
    time.sleep(9)
    check("right key: gate gone, home loads", gate_shown(b) is False and cards(b) > 5, "cards=%s" % cards(b))
    b.shot("shots/live_gate_2_home.png")
    b.open(URL, wait=7)
    check("reload: no gate again (key remembered)", gate_shown(b) is False and cards(b) > 5, "cards=%s" % cards(b))

# --- 2. the magic link: #key=... opens straight to the home and the key leaves the address bar
with cdp.Browser(size=(430, 900), scale=2.0) as b:
    cdp.emulate(b, 390, 800, mobile=True, scale=2.0)
    b.open(URL + "#key=" + KEY, wait=8)
    check("#key= link: no gate, home loads", gate_shown(b) is False and cards(b) > 5, "cards=%s" % cards(b))
    check("#key= link: the key is removed from the address", b.js("location.hash.indexOf('key')<0 && location.href.indexOf('key=')<0") is True)

print("\n%d/%d passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
