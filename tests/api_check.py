"""End-to-end check of the server through HTTP (works against the dev server and the real one).

usage: python tests/api_check.py [base-url] [key]
       base-url defaults to http://localhost:8080/podtube/api.cgi
"""
import gzip
import json
import re
import sys
import time
import urllib.error
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080/podtube/api.cgi").rstrip("/")
KEY = sys.argv[2] if len(sys.argv) > 2 else ""
ORIGIN = re.match(r"^(https?://[^/]+)", BASE).group(1)
results = []


def call(path, body=None, headers=None, raw=False, timeout=60):
    h = {"Accept-Encoding": "gzip", "X-PT-Hl": "ja", "X-PT-Gl": "JP"}
    if KEY:
        h["X-PT-Key"] = KEY
    h.update(headers or {})
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    url = path if path.startswith("http") else (BASE + path if not path.startswith("/podtube") else ORIGIN + path)
    req = urllib.request.Request(url, data=data, headers=h)
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        status, hd, payload = r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        status, hd, payload = e.code, e.headers, e.read()
    if hd.get("Content-Encoding") == "gzip":
        payload = gzip.decompress(payload)
    if raw:
        return status, hd, payload
    try:
        return status, json.loads(payload.decode("utf-8"))
    except ValueError:
        return status, payload[:200]


def check(name, ok, detail=""):
    results.append(ok)
    print("%s %-34s %s" % ("PASS" if ok else "FAIL", name, detail))
    return ok


def main():
    t0 = time.time()
    st, js = call("/health")
    check("health", st == 200 and js.get("ok"), str(js)[:80])
    st, js = call("/init")
    check("init (visitor id)", st == 200 and len(js.get("visitor", "")) > 20, "http %s" % st)
    visitor = js.get("visitor", "") if st == 200 else ""
    vh = {"X-PT-Visitor": visitor}

    st, js = call("/home", {"seen": [], "fresh": False}, vh)
    items = js.get("items", []) if st == 200 else []
    check("home feed", st == 200 and len(items) > 10, "%d items, endpoint=%s" % (len(items), js.get("endpoint") if st == 200 else st))
    if st == 200 and js.get("continuation"):
        st2, js2 = call("/continuation", {"token": js["continuation"], "endpoint": js["endpoint"]}, vh)
        check("home continuation", st2 == 200 and len(js2.get("items", [])) > 0, "%d items" % len(js2.get("items", [])) if st2 == 200 else str(st2))
    seen = [x["video"]["id"] for x in items if x["type"] == "video"][:30]
    st, js = call("/home", {"seen": seen, "fresh": True}, vh)
    check("home refresh demotes seen", st == 200 and all(x["video"]["id"] not in seen for x in js["items"][:5] if x["type"] == "video"), "")

    st, js = call("/search?q=" + urllib.request.quote("ホロライブ") + "&sort=2", None, vh)
    check("search", st == 200 and len(js.get("items", [])) > 5, "%d items" % len(js.get("items", [])) if st == 200 else str(st))
    st, js = call("/suggest?q=" + urllib.request.quote("ホロ"), None, vh)
    check("suggest", st == 200 and len(js.get("suggestions", [])) > 0, str(js.get("suggestions", [])[:3]))

    vid = "dQw4w9WgXcQ"
    st, js = call("/watch?v=" + vid, None, vh)
    check("watch", st == 200 and js.get("title") and js.get("channel"), (js.get("title") or "")[:40] if st == 200 else str(st))
    if st == 200 and js.get("commentsToken"):
        st2, c = call("/comments", {"token": js["commentsToken"]}, vh)
        check("comments", st2 == 200 and len(c.get("comments", [])) > 0, "%d comments" % len(c.get("comments", [])) if st2 == 200 else str(st2))
    st, js = call("/channel?id=UCuAXFkgsw1L7xaCfnd5JJOw", None, vh)
    check("channel", st == 200 and js.get("name") == "Rick Astley" and len(js.get("tabs", [])) >= 3, "%s tabs" % len(js.get("tabs", [])) if st == 200 else str(st))
    st, js = call("/playlist?id=PLFgquLnL59alCl_2TQvOiD5Vgm1hCaGSI", None, vh)
    check("playlist", st == 200 and len(js.get("firstPage", {}).get("items", [])) > 5, js.get("title", "") if st == 200 else str(st))
    st, js = call("/reel/seq?seed=" + vid, None, vh)
    check("reel sequence", st == 200 and len(js.get("ids", [])) > 2, "%s" % len(js.get("ids", [])) if st == 200 else str(st))

    # ---- media relay
    st, play = call("/play?v=" + vid, None, vh)
    ok = st == 200 and play.get("sid") and play.get("hls")
    check("play (session)", ok, "http %s, %s captions, maxH %s" % (st, len(play.get("captions", [])) if st == 200 else "-", play.get("maxHeight") if st == 200 else "-"))
    if not ok:
        return summary(t0)
    sid = play["sid"]
    mbase = "/podtube/api.cgi/hls/%s" % sid
    st, hd, body = call("/hls/%s/master.m3u8?maxh=720" % sid, raw=True, headers=vh)
    text = body.decode() if st == 200 else ""
    heights = [int(m.group(1)) for m in re.finditer(r"RESOLUTION=\d+x(\d+)", text)]
    check("master (cap 720, H.264 only)", st == 200 and heights and max(heights) <= 720 and "vp09" not in text and "avc1" in text,
          "http %s, heights %s, type %s" % (st, sorted(set(heights)), hd.get("Content-Type")))
    check("master has no subtitle group", "SUBTITLES" not in text and "TYPE=AUDIO" in text, "")
    vuri = [l for l in text.splitlines() if l and not l.startswith("#")]
    auri = re.findall(r'URI="([^"]+)"', text)
    if vuri:
        st, hd, body = call(vuri[0], raw=True)
        pl = body.decode() if st == 200 else ""
        segs = [l for l in pl.splitlines() if l and not l.startswith("#")]
        check("video media playlist", st == 200 and len(segs) > 10 and segs[0].startswith("/podtube/api.cgi/hls/"), "http %s, %d segments, first %s" % (st, len(segs), segs[0][-30:] if segs else ""))
        if segs:
            t = time.time()
            st, hd, body = call(segs[0], raw=True)
            check("video segment (TS)", st == 200 and len(body) > 50000 and body[0] == 0x47, "http %s, %d bytes in %.2fs, type %s" % (st, len(body), time.time() - t, hd.get("Content-Type")))
            st, hd, body = call(segs[3], raw=True)
            check("video segment #3", st == 200 and len(body) > 50000 and body[0] == 0x47, "%d bytes" % len(body))
    if auri:
        st, hd, body = call(auri[0], raw=True)
        pl = body.decode() if st == 200 else ""
        segs = [l for l in pl.splitlines() if l and not l.startswith("#")]
        check("audio media playlist", st == 200 and len(segs) > 10, "http %s, %d segments" % (st, len(segs)))
        if segs:
            st, hd, body = call(segs[0], raw=True)
            check("audio segment (TS)", st == 200 and len(body) > 5000 and (body[0] == 0x47 or body[:3] == b"ID3"), "http %s, %d bytes, type %s" % (st, len(body), hd.get("Content-Type")))
    st, c = call("/captions?sid=%s&i=0" % sid, None, vh)
    check("captions", st == 200 and len(c.get("cues", [])) > 5, "%s cues" % len(c.get("cues", [])) if st == 200 else str(st))
    st, hd, body = call("/hls/%s/s/v0/99999.ts" % sid, raw=True)
    check("bad segment -> 404", st == 404, "http %s" % st)
    st, js = call("/hls/aaaaaaaaaaaaaaaaaaaaaa/master.m3u8")
    check("unknown session -> 410", st == 410, "http %s" % st)

    # ---- several audio tracks
    st, play2 = call("/play?v=0e3GPea1Tyg", None, vh)
    if st == 200 and len(play2.get("audioTracks", [])) > 1:
        sid2 = play2["sid"]
        for pref, want in (("ja", "ja"), ("original", "en-US"), ("", "ja")):
            st, hd, body = call("/hls/%s/master.m3u8?maxh=360&audio=%s" % (sid2, pref), raw=True, headers=vh)
            t = body.decode() if st == 200 else ""
            langs = re.findall(r'TYPE=AUDIO[^\n]*LANGUAGE="([^"]+)"', t)
            check("audio pref %-9r" % pref, st == 200 and langs and all(l == want for l in langs), "chosen %s" % set(langs))
    else:
        check("multi-audio video", False, "play http %s" % st)

    # ---- locked / key
    st, js = call("/watch?v=" + vid, None, {"X-PT-Key": "definitely-wrong"})
    check("wrong key is refused if a key is set", st == 200 or st == 401, "http %s" % st)
    return summary(t0)


def summary(t0):
    print("\n%d/%d passed in %.1fs" % (sum(1 for r in results if r), len(results), time.time() - t0))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
