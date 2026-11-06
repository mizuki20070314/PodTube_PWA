"""Download a short video, cut the network, play it from the cache."""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cdp  # noqa: E402

VID = "jNQXAC9IVRw"
with cdp.Browser(size=(430, 900), scale=2.0) as b:
    cdp.emulate(b, 390, 800, mobile=True, scale=2.0)
    b.open("http://localhost:8080/podtube/", wait=4)
    b.js("localStorage.clear()")
    b.open("http://localhost:8080/podtube/", wait=3)
    for i in range(10):
        if b.js("!!(navigator.serviceWorker && navigator.serviceWorker.controller)"):
            break
        b.pump(1)
    print("sw controlled:", b.js("!!(navigator.serviceWorker && navigator.serviceWorker.controller)"), "| supported:", b.js("PT.downloads.supported"))
    video = {"id": VID, "title": "Me at the zoo", "channelName": "jawed", "channelId": "", "channelAvatar": "", "thumbnail": "", "duration": "0:19",
             "views": "", "published": "", "isLive": False, "isUpcoming": False, "isShort": False}
    b.js("window.__dl = null; PT.api.play('%s').then(function(info){ window.__info = info; PT.downloads.start(%s, info, 240); return 1; })" % (VID, json.dumps(video)))
    for i in range(30):
        b.pump(1)
        pend = b.js("JSON.stringify(Object.keys(PT.downloads.pending).map(function(k){var p=PT.downloads.pending[k]; return [k, p.done, p.total, p.bytes]}))")
        recs = b.js("JSON.stringify(PT.downloads.records.map(function(r){return [r.video.id, r.height, r.bytes]}))")
        if i % 3 == 0:
            print("t+%2ds pending=%s records=%s" % (i + 1, pend, recs))
        if recs != "[]":
            break
    keys = b.js("caches.open('pt-offline').then(c=>c.keys()).then(ks=>ks.map(k=>new URL(k.url).pathname))")
    print("cache entries:", len(keys), keys[:4], "...")
    # library -> downloads screen
    b.js("PT.nav.selectTab(3); PT.nav.push(PT.screens.downloads())"); b.pump(1.0)
    b.shot("shots/off_list.png")
    # network off, play from the cache
    b.call("Network.enable")
    b.call("Network.emulateNetworkConditions", offline=True, latency=0, downloadThroughput=-1, uploadThroughput=-1)
    b.js("PT.router.play(%s)" % json.dumps(video)); b.pump(6)
    print("offline play:", b.js("JSON.stringify({state: PT.player.state, t: PT.player.currentTime, src: PT.player.sourceName, w: PT.player.video.videoWidth, err: PT.player.errorMessage})"))
    res = b.js("performance.getEntriesByType('resource').filter(function(e){return e.name.indexOf('/offline/')>=0}).length")
    print("resources served from /offline/:", res)
    b.shot("shots/off_play.png")
    b.call("Network.emulateNetworkConditions", offline=False, latency=0, downloadThroughput=-1, uploadThroughput=-1)
    # delete the download
    b.js("PT.downloads.remove('%s')" % VID); b.pump(1.0)
    print("after remove: records=%s, cache entries=%s" % (b.js("PT.downloads.records.length"), len(b.js("caches.open('pt-offline').then(c=>c.keys())"))))
    for m in b.console_messages():
        if "Tracking Prevention" not in m and "Manifest" not in m:
            print("  console:", m[:300])
