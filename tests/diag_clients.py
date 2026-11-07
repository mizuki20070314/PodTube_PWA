"""Scratch: what each InnerTube client is told for a video, with one persistent visitor id (run on the server or on a PC).
usage: python probe_clients.py <PT_HOME for the code: the folder that holds code/podtube> [video ids...]"""
import os
import sys
import time

home = sys.argv[1]
sys.path.insert(0, os.path.join(home, "code"))
os.environ["PT_HOME"] = home
from podtube import yt  # noqa: E402
from podtube.innertube import InnerTube, profile  # noqa: E402

vids = sys.argv[2:] or ["T5EZXMH9W3M", "dQw4w9WgXcQ"]
it = InnerTube("ja", "JP")
v = it.ensure_visitor() or ""
print("visitor id: %d characters" % len(v))
for vid in vids:
    for cid in ("visionos", "ios", "android_vr"):
        t = time.time()
        try:
            js = it.post("player", yt.player_body(vid), profile(cid))
            ps, sd = js["playabilityStatus"], js["streamingData"]
            print("%-12s %-10s status=%-14s streaming=%-5s hls=%-5s %.1fs  %s" % (
                vid, cid, ps["status"].str, sd.exists, bool(sd["hlsManifestUrl"].string), time.time() - t, ps["reason"].text_value[:70]))
        except Exception as e:
            print("%-12s %-10s EXC %s %s" % (vid, cid, type(e).__name__, str(e)[:100]))
        time.sleep(1)
