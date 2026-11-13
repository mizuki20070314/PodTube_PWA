#!/usr/bin/env python3
"""A/V sync of the real pipeline on the real server's streams, with a public "beep + flash" test video.

Gets the video's HLS streams from the PodTube server (the same master the app reads, the same variant choice), runs the engine's
ffmpeg command line (new = app/player/ffargs.lua, or --legacy = the first version) on the device for 25 s from several start
positions, and measures when the flashes appear in the picture pipe and when the beeps appear in the audio pipe:

    error = flash time in the pipe - beep time in the pipe          (positive: the picture comes later than the sound)

The test video has its flash and beep at the same instant, so a correct pipeline gives |error| < one frame at every position.
The access key is read from secrets/pt_key and never printed.  The tunnel must be up (the device fetches the streams itself).

  python tools/avsync/real_test.py [--video ID] [--ss 0,7.3,...] [--legacy] [--both]
"""
import argparse, json, os, shlex, subprocess, sys, tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import api
import avsync_test as T

ENV = dict(os.environ, MSYS_NO_PATHCONV="1")
PROXY = "http://127.0.0.1:8899"
ORIGIN = "https://my-dev.sakura.ne.jp"
RATE = 44100
SW, SH = 16, 9          # size of the pictures written to the analysis pipe (set per test video)
DEFAULT_VIDEOS = ["l-u0f9SWvV0"]


def out_fps(src, cap=30):
    f = int(src + 0.5)
    if f < 1:
        f = 30
    while f > cap:
        f = int(f / 2 + 0.5)
    return f


def streams(lua, vid):
    st, raw = api.call("GET", "play", {"v": vid})
    info = json.loads(raw)
    sid = info["sid"]
    st, raw = api.call("GET", "hls/%s/master.m3u8" % sid, {"maxh": "360"})
    hls = lua.eval('(require("player.hls"))')
    variants, audio = hls.parse_master(raw.decode())
    v = hls.choose_variant(variants, 360)
    a = audio[v["audio"] or ""]
    if a is None:                                                   # the app takes any rendition when the group does not match
        a = next(iter(audio.values()))
    return {"title": info.get("title", ""), "duration": info.get("duration"), "vurl": ORIGIN + v["uri"], "aurl": ORIGIN + a["uri"],
            "w": int(v["w"]), "h": int(v["h"]), "fps": float(v["fps"])}


def shrink(argv):
    """the pipeline of the engine, but the picture pipe gets 16x9 frames and only 25 s are written"""
    out, i = [], 0
    argv = list(argv)
    j = argv.index("-vf") if "-vf" in argv else -1
    if j >= 0:
        argv[j + 1] += ",scale=%d:%d:flags=area" % (SW, SH)
    else:
        k = argv.index("-pix_fmt")
        argv[k + 2:k + 2] = ["-vf", "scale=%d:%d:flags=area" % (SW, SH)]
    res = []
    for x in argv:
        if x == "-f":
            res += ["-t", "25"]
        res.append(x)
    return res


def run_on_device(argv):
    cmd = ("cd /tmp/avs/out && rm -f v.raw a.pcm ff.log; export https_proxy=%s http_proxy=%s LD_LIBRARY_PATH=/usr/lib:/lib; "
           "%s 3>v.raw 4>a.pcm 2>ff.log; echo rc=$?") % (PROXY, PROXY, " ".join(shlex.quote(x) for x in argv))
    rc = T.adb("shell", cmd).strip()
    d = tempfile.mkdtemp(prefix="avr_")
    T.adb("pull", "/tmp/avs/out/v.raw", os.path.join(d, "v.raw"), check=False)
    T.adb("pull", "/tmp/avs/out/a.pcm", os.path.join(d, "a.pcm"), check=False)
    log = T.adb("shell", "cat /tmp/avs/out/ff.log")
    rd = lambda n: open(os.path.join(d, n), "rb").read() if os.path.exists(os.path.join(d, n)) else b""
    return rc, rd("v.raw"), rd("a.pcm"), log


def flashes(vraw, fps):
    """The red circle in the upper left corner of this test video is complete only on the frame of the beep (timecode 00:0x:00,
    every 2 s) and has a black wedge on every other frame: the frames where its brightness peaks are the markers."""
    fs = SW * SH * 3 // 2
    n = len(vraw) // fs
    if n < 10:
        return [], n
    y = np.frombuffer(vraw[: n * fs], dtype=np.uint8).reshape(n, fs)[:, : SW * SH].reshape(n, SH, SW).astype(np.float32)
    roi = y[:, 0: int(SH * 0.5), int(SW * 0.02): int(SW * 0.26)].sum(axis=(1, 2))
    k = int(fps * 1.0)
    out = []
    for i in range(k, n - k):
        win = roi[i - k: i + k + 1]
        if roi[i] >= win.max() - 1e-6 and roi[i] > np.median(roi) * 1.01 and (not out or (i - out[-1]) > fps):
            if roi[i] > roi[i - 1] and roi[i] > roi[i + 1] or roi[i] == win.max():
                out.append(i)
    return [i / fps for i in out], n


def beeps(apcm):
    x = np.frombuffer(apcm[: len(apcm) // 4 * 4], dtype="<i2").reshape(-1, 2).astype(np.float32).mean(axis=1)
    w = int(RATE * 0.004)
    m = len(x) // w
    if m < 10:
        return [], 0.0
    e = np.sqrt((x[: m * w].reshape(m, w) ** 2).mean(axis=1))
    thr = max(300.0, 0.35 * np.percentile(e, 99.5))
    on = e > thr
    out, last = [], -1e9
    for i in range(1, m):
        t = i * w / RATE
        if on[i] and not on[i - 1] and t - last > 0.3:
            out.append(t)
            last = t
    return out, len(x) / RATE


def measure(spec, legacy, lua, mod):
    argv = T.legacy_argv(spec) if legacy else T.lua_list(mod.build(lua.table_from(spec)))
    rc, vraw, apcm, log = run_on_device(shrink(argv))
    fl, nf = flashes(vraw, spec["fps"])
    bp, adur = beeps(apcm)
    errs = []
    for b in bp:
        near = min(fl, key=lambda f: abs(f - b)) if fl else None
        if near is not None and abs(near - b) < 0.5:
            errs.append((near - b) * 1000)
    return rc, nf, adur, len(fl), len(bp), errs, log


def main():
    global SW, SH
    SW, SH = 160, 90
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", action="append")
    ap.add_argument("--ss", default="0,7.3,13.1,21.7,34.9")
    ap.add_argument("--legacy", action="store_true")
    ap.add_argument("--both", action="store_true")
    ap.add_argument("--mod", default="player.ffargs")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    T.adb("shell", "mkdir -p /tmp/avs/out")
    lua, mod = T.lua_module(a.mod)
    for vid in a.video or DEFAULT_VIDEOS:
        s = streams(lua, vid)
        fps = out_fps(s["fps"])
        print("== %s  %s  %.0fs  %dx%d @%g -> %d fps" % (vid, s["title"][:50], s["duration"] or 0, s["w"], s["h"], s["fps"], fps))
        for legacy in ([False, True] if a.both else [a.legacy]):
            for ss in [float(x) for x in a.ss.split(",")]:
                spec = {"vurl": s["vurl"], "aurl": s["aurl"], "start": ss, "fps": fps, "fps_arg": str(fps), "speed": 1.0, "rate": RATE,
                        "threads": 3, "w": s["w"], "h": s["h"]}
                rc, nf, adur, nfl, nbp, errs, log = measure(spec, legacy, lua, mod)
                if errs:
                    m = sum(errs) / len(errs)
                    print("  %-6s ss=%-5s flashes=%2d beeps=%2d paired=%2d  error mean %+7.1f ms  [min %+6.1f max %+6.1f]  frames=%d audio=%.1fs rc=%s" % (
                        "legacy" if legacy else "new", ss, nfl, nbp, len(errs), m, min(errs), max(errs), nf, adur, rc.replace("rc=", "")))
                else:
                    print("  %-6s ss=%-5s flashes=%2d beeps=%2d  no pairs  frames=%d audio=%.1fs rc=%s  %s" % (
                        "legacy" if legacy else "new", ss, nfl, nbp, nf, adur, rc.replace("rc=", ""), log.strip().replace("\n", " | ")[:200]))
                if a.verbose and log.strip():
                    print("     log:", log.strip().replace("\n", " | ")[:300])


if __name__ == "__main__":
    main()
