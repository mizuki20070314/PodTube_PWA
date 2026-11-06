"""Audio track switching, caption overlay, live streams."""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cdp  # noqa: E402

ST = "JSON.stringify({state: PT.player.state, t: +PT.player.currentTime.toFixed(1), live: PT.player.isLive, h: PT.player.video.videoHeight, src: PT.player.sourceName, err: PT.player.errorMessage})"
with cdp.Browser(size=(430, 900), scale=2.0) as b:
    cdp.emulate(b, 390, 800, mobile=True, scale=2.0)
    b.open("http://localhost:8080/podtube/", wait=4)
    b.js("localStorage.clear(); PT.settings.preferredAudio = ''")

    # ---- A. several audio tracks (MrBeast, 20+ dubs)
    b.js("PT.router.play({id:'0e3GPea1Tyg', title:'x'})"); b.pump(9)
    opts = b.js("JSON.stringify(PT.player.audioOptions().slice(0,4).map(function(o){return [o.id,o.title,o.isOriginal,o.isSelected]}))")
    n = b.js("PT.player.audioOptions().length")
    print("A tracks:", n, opts)
    print("A state:", b.js(ST))
    masters = b.js("performance.getEntriesByType('resource').map(e=>e.name).filter(n=>n.indexOf('master.m3u8')>=0).map(n=>n.slice(n.indexOf('master')))")
    print("A master urls:", masters)
    t_before = b.js("PT.player.currentTime")
    b.js("var o = PT.player.audioOptions().filter(function(o){return o.lang==='en-US'||o.isOriginal})[0]; PT.player.selectAudio(o)"); b.pump(6)
    masters = b.js("performance.getEntriesByType('resource').map(e=>e.name).filter(n=>n.indexOf('master.m3u8')>=0).map(n=>n.slice(n.indexOf('master')))")
    print("A after selecting the original:", masters[-1], "| pref:", b.js("PT.settings.preferredAudio"))
    print("A state:", b.js(ST), "(was %.1f)" % t_before)
    b.js("PT.player.selectAutomaticAudio()"); b.pump(1)

    # ---- B. captions overlay
    b.js("PT.router.play({id:'dQw4w9WgXcQ', title:'x'})"); b.pump(8)
    print("B tracks:", b.js("JSON.stringify(PT.subtitles.tracks.map(function(t){return [t.i,t.languageCode,t.name,t.isAuto]}))"))
    b.js("PT.subtitles.select(PT.subtitles.tracks.filter(function(t){return t.languageCode.indexOf('en')===0})[0])"); b.pump(3)
    print("B cues loaded:", b.js("PT.subtitles.cues.length"))
    b.js("PT.player.seek(24); PT.watch.controls().setVisible(false)"); b.pump(3)
    print("B overlay text at %.1fs: %r" % (b.js("PT.player.currentTime"), b.js("document.querySelector('.ctl-sub').hidden ? null : document.querySelector('.ctl-sub').textContent")))
    b.shot("shots/media_caption.png")
    b.js("PT.subtitles.disable()"); b.pump(1)
    print("B overlay after disable hidden:", b.js("document.querySelector('.ctl-sub').hidden"))

    # ---- C. live stream
    live = b.js("PT.api.search('live', {kind:1, live:true}).then(function(r){var v=null; (r.items||[]).forEach(function(it){ if(!v && it.type==='video' && it.video.isLive) v=it.video; }); return v ? JSON.stringify({id:v.id,title:v.title}) : null;})")
    print("C live candidate:", live)
    if live:
        v = json.loads(live)
        b.js("PT.router.play({id:%s, title:%s})" % (json.dumps(v["id"]), json.dumps(v["title"]))); b.pump(12)
        print("C state:", b.js(ST))
        print("C seekbar hidden:", b.js("document.querySelector('.seekbar').style.visibility"), "| time label:", b.js("document.querySelector('.ctl-time').textContent"))
        b.js("PT.watch.controls().setVisible(true)"); b.pump(0.8)
        b.shot("shots/media_live.png")
    for m in b.console_messages():
        if "Tracking Prevention" not in m and "Manifest" not in m:
            print("  console:", m[:300])
