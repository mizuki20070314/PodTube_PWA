#!/usr/bin/env python3
"""Measure the A/V sync of the engine's ffmpeg pipeline on the device with synthetic sources (see make_sources.py).

For every (source, seek position) it runs the engine's own command line (app/player/ffargs.lua, built here through lupa) on the
device with the video pipe (fd 3) and the audio pipe (fd 4) redirected to files, then finds the flashes in the frames and the beeps
in the samples.  The engine shows frame i at  start + i/fps + av_offset  and plays sample n at  start + n/rate, so for a flash and
the beep that belongs to it

    error = (i_flash / fps + av_offset) - n_beep / rate          (positive: the picture comes later than the sound)

and a correct pipeline gives |error| < one frame for every pulse, whatever the seek position and the start times of the two tracks.
Besides the relative error it checks the absolute one: start + pipe time must equal the container time stamp of the pulse.

  python tools/avsync/avsync_test.py [--build] [--kind ts|fmp4|single-ts|single-fmp4] [--legacy] [--variants a,b] [--ss 0,1.3]
  --build    regenerate the sources (needs ffmpeg with libx264 on the PC: pip install imageio-ffmpeg) and push them to /tmp/avs
  --legacy   use the command line of the first version (per-input time stamp normalisation), to see the problem this fixes
  single-*   first mux the two HLS tracks into one mp4 the way a download does (new or --legacy flags), then play that file
"""
import argparse, json, os, shlex, subprocess, sys, tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.normpath(os.path.join(HERE, "..", "..", "app"))
OUT_LOCAL = os.path.join(HERE, "out")
W, H = 64, 36
RATE = 44100
ENV = dict(os.environ, MSYS_NO_PATHCONV="1")

VARIANTS = ["base", "vlate", "alate", "vlate1f", "ntsc"]
SS = [0, 0.8, 1.3, 2.2, 3.7, 6.1, 8.4]


def adb(*args, check=True):
    r = subprocess.run(["adb"] + list(args), capture_output=True, env=ENV)
    if check and r.returncode != 0:
        raise SystemExit("adb %s failed: %s" % (" ".join(args[:3]), r.stderr.decode("utf-8", "replace")))
    return r.stdout.decode("utf-8", "replace")


def lua_module(name):
    from lupa.luajit21 import LuaRuntime
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute('package.path = "%s/?.lua;" .. package.path' % APP.replace("\\", "/"))
    return lua, lua.eval('(require("%s"))' % name)


def lua_list(t):
    return [t[i] for i in range(1, len(t) + 1)]


def legacy_argv(spec):
    """the command line of the first version of the engine (kept to show what changed)"""
    a = ["/usr/bin/ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostdin", "-nostats"]
    ss = "%.3f" % spec["start"] if spec["start"] > 0.5 else None
    if spec.get("single"):
        if ss: a += ["-ss", ss]
        a += ["-c:v", "h264", "-threads", "3", "-i", spec["single"]]
        amap = "0:a:0"
    else:
        if ss: a += ["-ss", ss]
        a += ["-c:v", "h264", "-threads", "3", "-i", spec["vurl"]]
        if ss: a += ["-ss", ss]
        a += ["-i", spec["aurl"]]
        amap = "1:a:0"
    a += ["-map", "0:v:0", "-an", "-sn", "-pix_fmt", "yuv420p", "-r", spec["fps_arg"], "-f", "rawvideo", "pipe:3"]
    a += ["-map", amap, "-vn", "-sn", "-ac", "2", "-ar", str(RATE), "-f", "s16le", "pipe:4"]
    return a


def legacy_download(v, a, out):
    return ["/usr/bin/ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostdin", "-nostats", "-i", v, "-i", a,
            "-map", "0:v:0", "-map", "1:a:0", "-c", "copy", "-bsf:a", "aac_adtstoasc", "-movflags", "+faststart", "-f", "mp4", "-y", out]


def run_case(argv):
    cmd = "cd /tmp/avs/out && rm -f v.raw a.pcm ff.log; LD_LIBRARY_PATH=/usr/lib:/lib %s 3>v.raw 4>a.pcm 2>ff.log; echo rc=$?" % (
        " ".join(shlex.quote(x) for x in argv))
    rc = adb("shell", cmd).strip()
    d = tempfile.mkdtemp(prefix="avs_")
    adb("pull", "/tmp/avs/out/v.raw", os.path.join(d, "v.raw"), check=False)
    adb("pull", "/tmp/avs/out/a.pcm", os.path.join(d, "a.pcm"), check=False)
    log = adb("shell", "cat /tmp/avs/out/ff.log")
    rd = lambda n: open(os.path.join(d, n), "rb").read() if os.path.exists(os.path.join(d, n)) else b""
    return rc, rd("v.raw"), rd("a.pcm"), log


def video_onsets(vraw, fps):
    fs = W * H * 3 // 2
    n = len(vraw) // fs
    if n == 0:
        return [], 0
    y = np.frombuffer(vraw[: n * fs], dtype=np.uint8).reshape(n, fs)[:, : W * H].mean(axis=1)
    on = y > 128
    return [i / fps for i in range(1, n) if on[i] and not on[i - 1]], n


def audio_onsets(apcm):
    x = np.frombuffer(apcm[: len(apcm) // 4 * 4], dtype="<i2").reshape(-1, 2)[:, 0].astype(np.int32)
    loud = np.nonzero(np.abs(x) > 9000)[0]
    out, last = [], -10 ** 9
    for i in loud:
        if i - last > 0.2 * RATE and i > 100:
            out.append(i / RATE)
        last = i
    return out, len(x) / RATE


def frac(x):
    return (x + 0.5) % 1.0 - 0.5


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--src", default=OUT_LOCAL)
    ap.add_argument("--kind", default="ts")
    ap.add_argument("--variants", default=",".join(VARIANTS))
    ap.add_argument("--ss", default=",".join(str(s) for s in SS))
    ap.add_argument("--mod", default="player.ffargs")
    ap.add_argument("--legacy", action="store_true")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--verbose", "-v", action="store_true")
    a = ap.parse_args()

    if a.build:
        subprocess.run([sys.executable, os.path.join(HERE, "make_sources.py"), a.src], check=True)
        adb("shell", "rm -rf /tmp/avs; mkdir -p /tmp/avs/out")
        adb("push", a.src + "/.", "/tmp/avs/")
    adb("shell", "mkdir -p /tmp/avs/out")

    single = a.kind.startswith("single-")
    kind = a.kind.split("-", 1)[1] if single else a.kind
    lua, mod = lua_module(a.mod)
    worst_rel = worst_abs = 0.0
    bad = []
    for v in a.variants.split(","):
        base = "/tmp/avs/%s_%s" % (kind, v)
        tr = json.load(open(os.path.join(a.src, "%s_%s" % (kind, v), "truth.json")))
        fps_src = 30 if v == "ntsc" else 24
        vurl, aurl = base + "/v/index.m3u8", base + "/a/index.m3u8"
        single_path = None
        if single:
            single_path = base + "/single.mp4"
            argv = legacy_download(vurl, aurl, single_path) if a.legacy else lua_list(mod.download_argv(vurl, aurl, single_path))
            rc = adb("shell", "LD_LIBRARY_PATH=/usr/lib:/lib %s 2>&1; echo rc=$?" % " ".join(shlex.quote(x) for x in argv)).strip()
            if not rc.endswith("rc=0"):
                raise SystemExit("mux failed: " + rc)
        for ss in [float(s) for s in a.ss.split(",")]:
            spec = {"start": ss, "fps": fps_src, "fps_arg": str(fps_src), "speed": a.speed, "rate": RATE, "threads": 3, "w": W, "h": H}
            if single:
                spec["single"] = single_path
            else:
                spec["vurl"], spec["aurl"] = vurl, aurl
            argv = legacy_argv(spec) if a.legacy else lua_list(mod.build(lua.table_from(spec)))
            rc, vraw, apcm, log = run_case(argv)
            vt, nframes = video_onsets(vraw, fps_src)
            at, adur = audio_onsets(apcm)
            beep0 = tr["beep"] - round(tr["beep"] - tr["flash"])      # the beep of the same pulse as the first flash
            vk = {round(t + ss - tr["flash"]): t for t in vt}
            ak = {round(t + ss - beep0): t for t in at}
            ks = sorted(set(vk) & set(ak))
            rel = [(vk[k] - ak[k]) * 1000 for k in ks]
            absv = [frac(vk[k] + ss - tr["flash"]) * 1000 for k in ks]
            absa = [frac(ak[k] + ss - beep0) * 1000 for k in ks]
            tol = 1000.0 / fps_src * 1.15 + 5
            if rel:
                m, spread = sum(rel) / len(rel), max(rel) - min(rel)
                worst_rel = max(worst_rel, max(abs(e) for e in rel))
                worst_abs = max(worst_abs, max(abs(e) for e in absa))
                ok = max(abs(e) for e in rel) <= tol
            else:
                m = spread = float("nan")
                ok = False
            if not ok:
                bad.append((v, ss))
            print("%-8s ss=%-4s pulses=%2d  A/V error %+8.1f ms (spread %4.1f)  abs audio %+6.1f ms video %+6.1f ms  frames=%3d audio=%5.2fs rc=%s %s%s" % (
                v, ss, len(rel), m, spread, sum(absa) / len(absa) if absa else float("nan"), sum(absv) / len(absv) if absv else float("nan"),
                nframes, adur, rc.replace("rc=", ""), "ok" if ok else "FAIL",
                ("  LOG: " + log.strip().replace("\n", " | ")[:160]) if log.strip() and a.verbose else ""))
    print("\n%s: worst A/V error %.1f ms, worst absolute audio error %.1f ms, %d failing case(s) %s" % (
        a.kind + (" (legacy)" if a.legacy else ""), worst_rel, worst_abs, len(bad), bad if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
