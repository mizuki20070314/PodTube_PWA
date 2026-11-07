"""Bottom sheets with long lists (60 chapters, 24 audio tracks ...): they must scroll under a finger, and still be pulled down to close.

The sheet closes when it is pulled down from the top of its list; a swipe UP at the top is the list scrolling.  (Before the fix
the pull-down handler swallowed every vertical move, so a long list could never be scrolled by touch; the mouse wheel was fine.)

usage: python tests/t_sheet.py [url]        (the dev server must run: python tests/devserver.py 8080)
"""
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
    print("%s %-66s %s" % ("PASS" if ok else "FAIL", name, detail))


def num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else -1


def top(b):
    """scrollTop of the open sheet's list (-1 when no sheet is open)"""
    return num(b.js("(document.querySelector('.sheet-list')||{scrollTop:-1}).scrollTop"))


def open_chapters(b, n=60):
    b.js("PT.player.chapters = Array.from({length: %d}, function (_, i) { return {start: i, title: 'Chapter ' + (i + 1)}; }); PT.watch.showChapters()" % n)
    b.pump(0.6)


def list_rect(b):
    return cdp.rect(b, ".sheet-list")


def sheet_open(b):
    return b.js("!!document.querySelector('.sheet-root')")


def close_sheet(b):
    b.js("(function(){var d=document.querySelector('.sheet-dim'); if (d) d.click()})()")
    b.pump(0.5)


with cdp.Browser(size=(430, 900), scale=2.0) as b:
    cdp.emulate(b, 390, 800, mobile=True, scale=2.0)
    b.open(URL, wait=4)
    b.js("localStorage.clear()")
    b.js("PT.settings.uiLanguage = 'ja'")

    print("-- 60 chapters, portrait phone")
    open_chapters(b)
    r = list_rect(b)
    overflow = b.js("(function(){var l=document.querySelector('.sheet-list');return l.scrollHeight-l.clientHeight})()")
    check("the list is taller than its window (60 rows)", overflow > 500, "overflow=%s px, window=%s px" % (overflow, r["h"]))
    check("the list starts at the top", top(b) == 0)
    cx, cy = r["x"] + r["w"] / 2, r["y"] + r["h"] * 0.8
    cdp.swipe(b, cx, cy, cx, cy - r["h"] * 0.7, steps=12); b.pump(0.8)
    t1 = top(b)
    check("a swipe up from the top scrolls the list", t1 > 100, "scrollTop=%s" % t1)
    check("  ... and the sheet stays open", sheet_open(b) is True)
    cdp.swipe(b, cx, cy - r["h"] * 0.7, cx, cy, steps=12); b.pump(0.8)
    t2 = top(b)
    check("a swipe down in the middle of the list scrolls back (does not close)", sheet_open(b) is True and 0 <= t2 < t1, "scrollTop=%s" % t2)
    if not sheet_open(b):
        open_chapters(b)
    b.shot("shots/sheet_chapters.png")
    # flick to the very end
    for _ in range(6):
        cdp.swipe(b, cx, cy, cx, cy - r["h"] * 0.75, steps=6, delay=0.01); b.pump(0.5)
    end = num(b.js("(function(){var l=document.querySelector('.sheet-list');return l?Math.round(l.scrollHeight-l.clientHeight-l.scrollTop):-1})()"))
    check("repeated swipes reach the last chapter", 0 <= end <= 2, "px left=%s" % end)
    last = b.js("(function(){var rows=document.querySelectorAll('.sheet-row');var le=document.querySelector('.sheet-list');if(!le)return false;var l=le.getBoundingClientRect();var r=rows[rows.length-1].getBoundingClientRect();return r.bottom<=l.bottom+1 && r.top>=l.top-1})()")
    check("  ... and the last row is fully visible", last is True)
    b.shot("shots/sheet_chapters_end.png")
    # scroll back to the top, then pull the sheet down: it closes
    if not sheet_open(b):
        open_chapters(b)
    b.js("document.querySelector('.sheet-list').scrollTop = 0"); b.pump(0.3)
    cdp.swipe(b, cx, r["y"] + 30, cx, r["y"] + 30 + 360, steps=14); b.pump(0.9)
    check("pulling down from the top of the list closes the sheet", sheet_open(b) is False)

    print("-- the mouse wheel (desktop) still works")
    open_chapters(b)
    r = list_rect(b)
    b.call("Input.dispatchMouseEvent", type="mouseWheel", x=r["x"] + r["w"] / 2, y=r["y"] + r["h"] / 2, deltaX=0, deltaY=400); b.pump(0.6)
    check("wheel scrolls the list", top(b) > 100, "scrollTop=%s" % top(b))
    close_sheet(b)

    print("-- a short list (the quality sheet) is unchanged")
    b.js("PT.router.play({id:'dQw4w9WgXcQ', title:'x'})"); b.pump(7)
    b.js("PT.watch.showQuality()"); b.pump(0.6)
    r = list_rect(b)
    cx, cy = r["x"] + r["w"] / 2, r["y"] + 20
    cdp.swipe(b, cx, cy, cx, cy - 60, steps=8); b.pump(0.5)
    check("short list: a swipe up changes nothing", sheet_open(b) is True and top(b) == 0)
    cdp.swipe(b, cx, cy, cx, cy + 300, steps=12); b.pump(0.9)
    check("short list: pulling down closes it", sheet_open(b) is False)

    print("-- the sheet opens at the chapter that is playing")
    b.js("PT.player.chapters = Array.from({length: 60}, function (_, i) { return {start: i, title: 'Chapter ' + (i + 1)}; })")
    b.js("PT.player.seek(50)"); b.pump(2.5)
    b.js("PT.watch.showChapters()"); b.pump(0.7)
    now = b.js("(function(){var c=document.querySelector('.sheet-chk');if(!c)return 'no check';var row=c.parentNode;var l=document.querySelector('.sheet-list').getBoundingClientRect();var r=row.getBoundingClientRect();return {t:row.querySelector('.t').textContent,visible:r.top>=l.top-1&&r.bottom<=l.bottom+1,scroll:document.querySelector('.sheet-list').scrollTop}})()")
    check("the playing chapter is in view when the list opens", isinstance(now, dict) and now.get("visible") is True, str(now))
    b.shot("shots/sheet_chapters_current.png")
    # from the title bar the sheet can always be pulled down, even with the list scrolled
    tr = cdp.rect(b, ".sheet-title")
    tx, ty = tr["x"] + tr["w"] / 2, tr["y"] + tr["h"] / 2
    cdp.swipe(b, tx, ty, tx, ty + 360, steps=14); b.pump(0.9)
    check("scrolled list: pulling down by the title bar still closes the sheet", sheet_open(b) is False)
    if not sheet_open(b):
        b.js("PT.watch.showChapters()"); b.pump(0.7)
    # at the scrolled position a pull-down is the list scrolling up, not a dismissal
    r = list_rect(b)
    cx, cy = r["x"] + r["w"] / 2, r["y"] + r["h"] * 0.3
    cdp.swipe(b, cx, cy, cx, cy + 150, steps=10); b.pump(0.7)
    check("scrolled: a swipe down scrolls up instead of closing", sheet_open(b) is True)
    close_sheet(b)

    print("-- landscape phone (a window of about three rows)")
    cdp.emulate(b, 800, 390, mobile=True, scale=2.0); b.pump(1.5)
    open_chapters(b)
    r = list_rect(b)
    cx, cy = r["x"] + r["w"] / 2, r["y"] + r["h"] * 0.85
    cdp.swipe(b, cx, cy, cx, cy - r["h"] * 0.7, steps=10); b.pump(0.7)
    check("landscape: the list scrolls (window %.0f px)" % r["h"], top(b) > 50, "scrollTop=%s" % top(b))
    b.shot("shots/sheet_landscape.png")
    close_sheet(b)

    errs = [m for m in b.console_messages() if m.startswith(("EXCEPTION", "error"))]
    check("no script errors in the console", not errs, str(errs[:3]))

print("\n%d/%d passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
