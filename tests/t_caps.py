import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cdp  # noqa: E402
with cdp.Browser(size=(430, 900), scale=1.0) as b:
    cdp.emulate(b, 390, 800, mobile=True, scale=1.0)
    b.open("http://localhost:8080/podtube/", wait=4)
    b.js("localStorage.clear()")
    b.js("PT.router.play({id:'dQw4w9WgXcQ', title:'x'})"); b.pump(7)
    b.js("PT.subtitles.select(PT.subtitles.tracks.filter(function(t){return t.languageCode==='en' && !t.isAuto})[0])"); b.pump(3)
    print("enabled:", b.js("PT.subtitles.isEnabled"), "cues:", b.js("PT.subtitles.cues.length"), "current:", b.js("JSON.stringify(PT.subtitles.current)"))
    print("first cues:", b.js("JSON.stringify(PT.subtitles.cues.slice(0,6))"))
    for t in (19, 21, 24, 27, 30):
        print("textAt(%s):" % t, b.js("PT.subtitles.textAt(%s)" % t))
    b.js("PT.player.seek(21)"); b.pump(1.5)
    print("t=%.1f overlay hidden=%s text=%r fingerDown=%s" % (b.js("PT.player.currentTime"), b.js("document.querySelector('.ctl-sub').hidden"), b.js("document.querySelector('.ctl-sub').textContent"), b.js("PT.watch.controls().fingerDown")))
    b.shot("shots/caps.png")
