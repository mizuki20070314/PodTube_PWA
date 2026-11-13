#!/usr/bin/env python3
"""A picture the device cannot decode in real time: plays the test video, then asks for a much higher quality than the 360p it was
tuned for.  The decoder falls behind the sound, and the sync monitor has to notice it (late picture), restart from the current position
and - when it happens again soon - lower the quality by itself until the picture keeps up.

  python tools/avsync/hq_test.py [--video ID] [--height 1080] [--seconds 90]
needs: the tunnel up, the app running with debug.flag (python tools/dev.py debug on; python tools/dev.py run)
"""
import argparse, subprocess, sys, time

import app_test as T
from app_test import ev, check, state, stats, wait_state, sample, ctl, ENV


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", default="l-u0f9SWvV0")
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--seconds", type=int, default=90)
    a = ap.parse_args()
    ctl.forward()
    if ctl.send("ping") != "pong":
        raise SystemExit("control socket not reachable")
    ev("local S=require('core.store'); S.set('autoplay', false); local P=require('player.player'); P.loops=true; "
       "P.play({id='%s', title='hq test'}); return 1" % a.video)
    check("playback starts (at the usual quality)", wait_state("playing", 40), state())
    time.sleep(4)
    rows = sample(4, "at the usual quality")
    ev("require('player.player').set_max_height(%d); return 1" % a.height)
    print("-- asked for up to %dp --" % a.height)
    t0, nextshow, worst, last_fixes = time.time(), 0, 0, 0
    while time.time() - t0 < a.seconds:
        s = stats()
        fixes = ev("return require('player.player').sync_fixes")
        fixes = int(fixes) if fixes.isdigit() else last_fixes
        last_fixes = fixes
        if s:
            worst = max(worst, s["late"])
        if time.time() - t0 >= nextshow:
            nextshow += 5
            print("   +%3.0f s: %s repairs %d" % (time.time() - t0, ("late %5.0f ms, skew %+5.0f ms, dropped %d of %d, xruns %d" % (
                s["late"], s["skew"], s["dropped"], s["frames"], s["xruns"])) if s else "(no engine running)", fixes))
        time.sleep(1)
    print("   worst lateness %.0f ms, repairs %d" % (worst, last_fixes))
    cap = ev("local P=require('player.player'); return tostring(P.max_height)")
    print("   max_height setting now %s" % cap)
    check("the monitor repaired it by itself at least once", last_fixes >= 1, "repairs %d" % last_fixes)
    check("still playing at the end", wait_state("playing", 30), state())
    time.sleep(5)
    rows = sample(8, "at the end")
    if rows:
        check("   in step at the end", abs(sum(r["skew"] for r in rows) / len(rows)) < 60 and max(r["late"] for r in rows) < 250,
              "worst lateness %.0f ms" % max(r["late"] for r in rows))
    ev("require('player.player').loops=false; return 1")
    log = subprocess.run(["adb", "shell", "grep -E 'sync:|engine: ffmpeg' /mnt/sdcard/Ports/PodTube/logs/podtube.log | tail -12"],
                         capture_output=True, env=ENV).stdout.decode("utf-8", "replace")
    print(log)
    print("\n%s" % ("ALL OK" if not T.fails else "FAILED: %s" % T.fails))
    sys.exit(1 if T.fails else 0)


if __name__ == "__main__":
    main()
