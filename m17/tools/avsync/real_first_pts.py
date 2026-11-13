#!/usr/bin/env python3
"""Where do the first picture and the first sound of a playback start, relative to the wanted position, on the real streams?

Runs the engine's ffmpeg line (new = app/player/ffargs.lua with spec.probe, or --legacy = the first version) on the device against
the real server's HLS for a few start positions and prints the time stamps that ffmpeg reports for the first pictures / audio
frames (showinfo / ashowinfo, in seconds after the wanted position):

  video before fps   the first picture ffmpeg really decoded for this position  (should be 0 .. one frame)
  video after fps    what goes into the picture pipe                            (new: exactly 0, 1/fps, 2/fps ..)
  audio              the first audio frame                                       (new: exactly 0)

The old line fed the picture pipe with whatever came first and called it frame 0, so a picture that really starts 0.2 s late was
shown 0.2 s too early.  The tunnel must be up.   python tools/avsync/real_first_pts.py [--video ID] [--ss ..] [--both]
"""
import argparse, os, re, shlex, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import avsync_test as T
import real_test as R

DEFAULT = {"nmr8QCcYz98": "12.3,60.5,100.7,233.1,400.4", "ucZl6vQ_8Uo": "7.3,12.3,25.1,40.7"}


def legacy_probe(spec):
    a = T.legacy_argv(spec)
    i = a.index("-pix_fmt")
    a[i + 2:i + 2] = ["-vf", "showinfo"]
    j = a.index("-ac")
    a[j:j] = ["-af", "ashowinfo"]
    return a


def with_limits(argv):
    out = []
    for x in argv:
        if x == "-f":
            out += ["-t", "2"]
        out.append(x)
    out[out.index("-loglevel") + 1] = "info"
    return out


def firsts(log):
    byinst = {}
    for m in re.finditer(r"\[Parsed_(a?showinfo)_(\d+) @ [^\]]+\] n:\s*(\d+) pts:\s*(-?\d+) pts_time:(-?[\d.]+)", log):
        byinst.setdefault((m.group(1), int(m.group(2))), []).append(float(m.group(5)))
    return byinst


def run(spec, legacy, lua, mod):
    sp = dict(spec)
    if legacy:
        argv = legacy_probe(sp)
    else:
        sp["probe"] = True
        argv = T.lua_list(mod.build(lua.table_from(sp)))
    rc, vraw, apcm, log = R.run_on_device(with_limits(argv))
    return rc, firsts(log), len(vraw), len(apcm), log


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", action="append")
    ap.add_argument("--ss")
    ap.add_argument("--both", action="store_true")
    ap.add_argument("--legacy", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    T.adb("shell", "mkdir -p /tmp/avs/out")
    lua, mod = T.lua_module("player.ffargs")
    vids = a.video or list(DEFAULT)
    for vid in vids:
        s = R.streams(lua, vid)
        fps = R.out_fps(s["fps"])
        print("== %s  %s  %.0fs  %dx%d @%g" % (vid, s["title"][:40], s["duration"] or 0, s["w"], s["h"], s["fps"]))
        for ss in [float(x) for x in (a.ss or DEFAULT.get(vid, "12.3,60.5")).split(",")]:
            spec = {"vurl": s["vurl"], "aurl": s["aurl"], "start": ss, "fps": fps, "fps_arg": str(fps), "speed": 1.0, "rate": 44100,
                    "threads": 3, "w": s["w"], "h": s["h"]}
            for legacy in ([True, False] if a.both else [a.legacy]):
                rc, f, nv, na, log = run(spec, legacy, lua, mod)
                v = sorted(k for k in f if k[0] == "showinfo")
                au = sorted(k for k in f if k[0] == "ashowinfo")
                fmt = lambda k: ("%.3f %.3f %.3f" % tuple(f[k][:3])) if k in f and len(f[k]) >= 3 else "-"
                parts = ["video(pre fps) " + fmt(v[0]) if v else "video -", ("video(post) " + fmt(v[1])) if len(v) > 1 else "",
                         "audio " + fmt(au[0]) if au else "audio -"]
                print("  ss=%-6s %-6s %s   frames=%d" % (ss, "legacy" if legacy else "new", "   ".join(p for p in parts if p), nv // (s["w"] * s["h"] * 3 // 2)))
                if rc != "rc=0":
                    print("     ", rc, log.strip().replace("\n", " | ")[-200:])


if __name__ == "__main__":
    main()
