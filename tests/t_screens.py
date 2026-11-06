"""Visits every screen once and saves a screenshot of each (tests/shots/sc_*.png)."""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.makedirs(os.path.join(HERE, "shots"), exist_ok=True)
import cdp  # noqa: E402

URL = "http://localhost:8080/podtube/"


def shot(b, name):
    p = b.shot("shots/sc_" + name + ".png")
    print("   shot", name)
    return p


def info(b, label):
    print("%-22s feedItems=%s cards=%s stack=%s errs=%s" % (label,
          b.js("(PT.nav.top().feed ? PT.nav.top().feed.items.length : -1)"),
          b.js("document.querySelectorAll('.tabpane.active .screen:not(.under) .vcard').length"),
          b.js("PT.nav.current().stack.length"), b.js("JSON.stringify(window.__errs)")))


with cdp.Browser(size=(430, 900), scale=2.0) as b:
    cdp.emulate(b, 390, 800, mobile=True, scale=2.0)
    b.open(URL, wait=4)
    b.js("window.__errs = []; window.addEventListener('error', e => __errs.push(e.message)); window.addEventListener('unhandledrejection', e => __errs.push('rej: ' + (e.reason && e.reason.message || e.reason)))")

    # --- chips: tap "音楽"
    print("chip music:", cdp.tap_sel(b, ".chip", 1)); b.pump(3.5)
    info(b, "home/music"); shot(b, "home_music")
    cdp.tap_sel(b, ".chip", 0); b.pump(2.5)

    # --- search: tap the magnifier, type, suggestions, submit
    print("search icon:", cdp.tap_sel(b, ".appbar .bar-search")); b.pump(1.0)
    b.js("document.querySelector('.sf-input').focus()")
    b.type_text("cat", delay=0.05); b.pump(1.5)
    print("suggestions:", b.js("Array.from(document.querySelectorAll('.sg-text')).map(e=>e.textContent).slice(0,5)"))
    shot(b, "search_suggest")
    b.key("Enter", "Enter", 13, "\r"); b.pump(4)
    info(b, "results"); shot(b, "results")
    # filter sheet
    print("filter btn:", cdp.tap_sel(b, ".sr-filter")); b.pump(0.6); shot(b, "filter_sheet")
    print("filter rows:", b.js("Array.from(document.querySelectorAll('.sheet-row .t')).map(e=>e.textContent)"))
    cdp.tap_sel(b, ".sheet-row", 0); b.pump(0.5)          # sort by
    print("sort rows:", b.js("Array.from(document.querySelectorAll('.sheet-row .t')).map(e=>e.textContent)"))
    cdp.tap_sel(b, ".sheet-row", 1); b.pump(3.5)          # upload date order
    info(b, "results sorted")
    # back
    cdp.tap_sel(b, ".searchbar .bar-back"); b.pump(0.8)
    cdp.tap_sel(b, ".searchbar .bar-back"); b.pump(0.8)
    info(b, "back at home")

    # --- channel
    b.js("PT.router.openChannel('UCuAXFkgsw1L7xaCfnd5JJOw', 'Rick Astley')"); b.pump(4)
    info(b, "channel"); shot(b, "channel")
    print("tab titles:", b.js("Array.from(document.querySelectorAll('.chh-tab')).map(e=>e.textContent)"))
    cdp.tap_sel(b, ".chh-tab", 1); b.pump(3)
    info(b, "channel/videos"); shot(b, "channel_videos")
    cdp.tap_sel(b, ".chh-tab", 3); b.pump(2.5)
    shot(b, "channel_about")
    cdp.tap_sel(b, ".screen:not(.under) .bar-back"); b.pump(0.8)

    # --- playlist
    b.js("PT.router.openPlaylist('PLFgquLnL59alCl_2TQvOiD5Vgm1hCaGSI', '')"); b.pump(4)
    info(b, "playlist"); shot(b, "playlist")
    cdp.tap_sel(b, ".screen:not(.under) .bar-back"); b.pump(0.8)

    # --- shorts tab
    cdp.tap_sel(b, ".tabitem", 1); b.pump(7)
    print("shorts:", b.js("document.querySelectorAll('.short').length"), "video src:", b.js("(document.querySelector('.short-video')||{}).currentSrc"))
    shot(b, "shorts")
    b.js("document.querySelector('.shorts-pager').scrollTo(0, document.querySelector('.shorts-pager').clientHeight)"); b.pump(6)
    shot(b, "shorts_2")
    print("shorts errs:", b.js("JSON.stringify(window.__errs)"))

    # --- subscriptions (empty), library
    cdp.tap_sel(b, ".tabitem", 2); b.pump(2.0); shot(b, "subs_empty")
    cdp.tap_sel(b, ".tabitem", 3); b.pump(2.0); shot(b, "library")

    # --- settings / sign in / diagnostics
    b.js("PT.router.openSettings()"); b.pump(1.0); shot(b, "settings")
    b.js("document.querySelector('.settings').scrollTop = 600"); b.pump(0.5); shot(b, "settings_2")
    b.js("PT.nav.push(PT.screens.signIn())"); b.pump(4); shot(b, "signin")
    print("device code:", b.js("document.querySelector('.si-code').textContent"), "| qr svg:", b.js("!!document.querySelector('.si-qr svg')"))
    cdp.tap_sel(b, ".screen:not(.under) .bar-back"); b.pump(0.8)
    b.js("PT.nav.push(PT.screens.diagnostics())"); b.pump(0.8)
    cdp.tap_sel(b, ".diag .btn-pill"); b.pump(25); shot(b, "diag")
    print("diag:\n" + b.js("document.querySelector('.diag-out').textContent"))
    print("final errs:", b.js("JSON.stringify(window.__errs)"))
    for m in b.console_messages():
        if "Tracking Prevention" not in m:
            print("  console:", m[:300])
