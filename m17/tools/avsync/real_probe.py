#!/usr/bin/env python3
"""Look at the HLS streams the real server hands out: segment type, segment length, init segments, and what the device's ffmpeg
reports as the start time of the video and audio inputs (the numbers the A/V alignment depends on).  The access key is read from
secrets/pt_key and never printed; URLs are shortened.

  python tools/avsync/real_probe.py [query or video id ...]      (the tunnel must be up for the device's ffmpeg)
"""
import json, os, re, shlex, subprocess, sys, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import api

ENV = dict(os.environ, MSYS_NO_PATHCONV="1")
PROXY = "http://127.0.0.1:8899"


def get(route, params=None):
    st, raw = api.call("GET", route, params)
    return st, raw


def short(u):
    u = re.sub(r"\?.*$", "", u)
    return u if len(u) < 70 else "…" + u[-60:]


def adb(cmd, timeout=120):
    r = subprocess.run(["adb", "shell", cmd], capture_output=True, env=ENV, timeout=timeout)
    return r.stdout.decode("utf-8", "replace")


def probe_video(vid):
    st, raw = get("play", {"v": vid})
    if st != 200:
        print(vid, "play ->", st, raw[:120])
        return
    info = json.loads(raw)
    sid = info.get("sid")
    print("== %s  %s  (%ss) live=%s" % (vid, (info.get("title") or "")[:40], info.get("duration"), info.get("isLive")))
    st, raw = get("hls/%s/master.m3u8" % sid, {"maxh": "360"})
    master = raw.decode()
    base = "https://my-dev.sakura.ne.jp"
    lines = master.splitlines()
    vuri = auri = None
    for i, l in enumerate(lines):
        if l.startswith("#EXT-X-MEDIA") and "TYPE=AUDIO" in l and not auri:
            auri = re.search(r'URI="([^"]+)"', l).group(1)
        if l.startswith("#EXT-X-STREAM-INF"):
            print("  variant:", re.sub(r'CODECS="[^"]*",?', "", l)[:100])
            if not vuri:
                vuri = lines[i + 1]
    for name, uri in (("video", vuri), ("audio", auri)):
        route = uri.split("api.cgi/", 1)[1]
        st, raw = api.call("GET", route, None)
        txt = raw.decode("utf-8", "replace")
        tags = [l for l in txt.splitlines() if l.startswith("#") and not l.startswith("#EXTINF")]
        segs = re.findall(r"#EXTINF:([\d.]+)", txt)
        maps = [l for l in tags if "EXT-X-MAP" in l]
        print("  %s playlist: %d segments, EXTINF first %s  (target %s)  map:%s  ext:%s" % (
            name, len(segs), segs[:3], [t for t in tags if "TARGETDURATION" in t], bool(maps),
            sorted(set(re.findall(r"\.(\w{2,4})(?:\?|$)", "\n".join(l for l in txt.splitlines() if not l.startswith("#")))))[:4]))
        if maps:
            print("   ", re.sub(r'URI="[^"]+"', 'URI="…"', maps[0])[:100])
        print("   tags:", sorted(set(re.sub(r":.*", "", t) for t in tags)))
    return sid, base + vuri, base + auri


def device_starts(vurl, aurl, ss=None):
    """the device's ffmpeg: Input start times for both playlists, plus the first decoded pts through showinfo/ashowinfo"""
    out = []
    for kind, url in (("video", vurl), ("audio", aurl)):
        flt = ("-vf showinfo -an -frames:v 3" if kind == "video" else "-af ashowinfo -vn -frames:a 3")
        pre = "-c:v h264" if kind == "video" else ""
        cmd = ("export https_proxy=%s http_proxy=%s LD_LIBRARY_PATH=/usr/lib:/lib; ffmpeg -hide_banner -loglevel info -nostdin %s %s -i %s %s -f null - 2>&1 | "
               "grep -E 'Input #|start:|pts_time' | head -8") % (PROXY, PROXY, "-seek_timestamp 1" if ss is not None else "", ("-ss %s" % ss) if ss is not None else "", shlex.quote(url), flt)
        txt = adb(cmd)
        out.append((kind, txt))
    return out


def main():
    qs = sys.argv[1:] or ["猫 かわいい", "ニュース 生放送 録画", "ゲーム実況"]
    vids = []
    for q in qs:
        if re.fullmatch(r"[\w-]{11}", q):
            vids.append(q)
            continue
        st, raw = get("search", {"q": q})
        js = json.loads(raw)
        n = 0
        for it in js.get("items") or []:
            v = (it.get("video") or {})
            vid = v.get("id")
            if it.get("type") == "video" and vid and len(vid) == 11 and not v.get("isLive") and not v.get("isShort") and not v.get("isUpcoming"):
                vids.append(vid)
                n += 1
                if n >= 2:
                    break
    print("videos:", vids)
    for v in vids:
        probe_video(v)


if __name__ == "__main__":
    main()
