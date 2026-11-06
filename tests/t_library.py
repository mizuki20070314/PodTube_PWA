"""History, likes, playlists, subscriptions, watch later: the local data and the screens built on it."""
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
    return b.shot("shots/lib_" + name + ".png")


def store(b):
    return json.loads(b.js("JSON.stringify({history: PT.store.history.map(e=>[e.video.id, Math.round(e.position)]), liked: PT.store.liked.map(v=>v.id), wl: PT.store.watchLater.map(v=>v.id), pls: PT.store.playlists.map(p=>[p.name, p.videos.length]), subs: PT.store.subscriptions.map(c=>c.name)})"))


with cdp.Browser(size=(430, 900), scale=2.0) as b:
    cdp.emulate(b, 390, 800, mobile=True, scale=2.0)
    b.open(URL, wait=5)
    b.js("localStorage.clear()")
    b.js("window.__errs = []; window.addEventListener('error', e => __errs.push(e.message)); window.addEventListener('unhandledrejection', e => __errs.push('rej: ' + (e.reason && e.reason.message || e.reason)))")
    b.open(URL, wait=5)
    b.js("window.__errs = []; window.addEventListener('error', e => __errs.push(e.message)); window.addEventListener('unhandledrejection', e => __errs.push('rej: ' + (e.reason && e.reason.message || e.reason)))")

    # play the first video for a few seconds -> history entry with a position
    cdp.tap(b, 195, 200); b.pump(9)
    print("after play:", store(b))
    # like (header pill), save to a new playlist
    print("like tap:", cdp.tap_sel(b, ".lk-btn.like")); b.pump(0.8)
    print("liked:", store(b)["liked"])
    b.js("document.querySelector('.wh-actions').scrollLeft = 999"); b.pump(0.3)
    print("save tap:", cdp.tap_sel(b, ".p-save")); b.pump(1.0)
    print("sheet rows:", b.js("Array.from(document.querySelectorAll('.sheet-row .t')).map(e=>e.textContent)"))
    shot(b, "save_sheet")
    idx = b.js("Array.from(document.querySelectorAll('.sheet-row .t')).findIndex(e=>e.textContent==='新しい再生リスト')")
    cdp.tap_sel(b, ".sheet-row", idx); b.pump(1.0)
    print("dialog:", b.js("!!document.querySelector('.dlg-input')"))
    b.js("document.querySelector('.dlg-input').focus()")
    b.type_text("mylist", delay=0.04)
    shot(b, "new_playlist_dialog")
    cdp.tap_sel(b, ".dlg-btn", 1); b.pump(1.0)
    print("playlists:", store(b)["pls"], "| toast:", b.js("document.querySelector('.toast').textContent"))
    # subscribe from the channel row
    print("subscribe tap:", cdp.tap_sel(b, ".wh-channel .subbtn")); b.pump(0.6)
    print("subs:", store(b)["subs"])
    # description expand + chapters/timestamps
    cdp.tap_sel(b, ".wh-title"); b.pump(0.6)
    print("desc links:", b.js("document.querySelectorAll('.wh-desc .lnk').length"), "ts:", b.js("document.querySelectorAll('.wh-desc .lnk.ts').length"), "tags:", b.js("document.querySelectorAll('.wh-desc .lnk.tag').length"))
    b.js("document.querySelector('.w-body').scrollTop = 0")
    shot(b, "desc_open")
    # minimise, then the library
    cdp.tap_sel(b, ".ctl-collapse") or cdp.tap(b, 195, 110)
    cdp.tap(b, 195, 110); b.pump(0.6); cdp.tap_sel(b, ".ctl-collapse"); b.pump(1.2)
    cdp.tap_sel(b, ".tabitem", 3); b.pump(1.5)
    shot(b, "library_filled")
    print("library rows:", b.js("Array.from(document.querySelectorAll('.library .librow')).map(e=>e.textContent.trim().replace(/\\s+/g,' '))"))
    print("shelf cards:", b.js("document.querySelectorAll('.library .hcard').length"))
    # history list, liked list, playlists list
    cdp.tap_sel(b, ".library .librow", 0); b.pump(1.2); shot(b, "history_list")
    print("history cards:", b.js("document.querySelectorAll('.screen:not(.under) .vcard').length"))
    cdp.tap_sel(b, ".screen:not(.under) .bar-back"); b.pump(0.8)
    cdp.tap_sel(b, ".library .librow", 2); b.pump(1.0); shot(b, "playlists_list")
    cdp.tap_sel(b, ".ul-row"); b.pump(1.0)
    print("playlist screen title:", b.js("document.querySelector('.screen:not(.under) .bar-title').textContent"), "cards:", b.js("document.querySelectorAll('.screen:not(.under) .vcard').length"))
    cdp.tap_sel(b, ".screen:not(.under) .bar-back"); b.pump(0.8)
    cdp.tap_sel(b, ".screen:not(.under) .bar-back"); b.pump(0.8)
    # subscriptions tab: strip + feed
    cdp.tap_sel(b, ".tabitem", 2); b.pump(7)
    print("strip items:", b.js("document.querySelectorAll('.strip-item').length"), "feed cards:", b.js("document.querySelectorAll('.subs .vcard').length"))
    shot(b, "subs_filled")
    # a card menu: add to watch later
    cdp.tap_sel(b, ".subs .vcard .more"); b.pump(0.8)
    print("menu rows:", b.js("Array.from(document.querySelectorAll('.sheet-row .t')).map(e=>e.textContent)"))
    cdp.tap_sel(b, ".sheet-row", 0); b.pump(1.0)
    print("watch later:", store(b)["wl"])
    print("errs:", b.js("JSON.stringify(__errs)"))
    for m in b.console_messages():
        if "Tracking Prevention" not in m and "Manifest" not in m:
            print("  console:", m[:300])
