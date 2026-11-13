#!/usr/bin/env python3
"""A/V sync of the whole app on the device (control socket): plays a public test video, samples what the engine measures
(how far the shown picture is from the audio clock), seeks around, runs into the end of the video, and - with --stress - starves
the decoder of CPU to see the sync monitor repair a playback that falls behind.

  python tools/avsync/app_test.py [--video ID] [--stress]
needs: the tunnel up, the app running with debug.flag (python tools/dev.py debug on; python tools/dev.py run)
"""
import argparse, json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import ctl

ENV = dict(os.environ, MSYS_NO_PATHCONV="1")
fails = []


def ev(code):
    return ctl.send("eval " + code)


def adb(cmd):
    return subprocess.run(["adb", "shell", cmd], capture_output=True, env=ENV).stdout.decode("utf-8", "replace")


def check(name, ok, detail=""):
    print("%-58s %s %s" % (name, "ok" if ok else "FAIL", detail))
    if not ok:
        fails.append(name)


def state():
    return ev("return require('player.player').state")


def stats():
    r = ev("local E=require('player.engine'); local s=E.stats(); if not s then return 'none' end; "
           "return string.format('%d %d %d %d %.1f %.1f %.2f %d', s.frames, s.displayed, s.dropped, s.xruns, s.skew_ms, s.late_ms, s.clock, s.latency_ms)")
    if r == "none":
        return None
    f = r.split()
    return {"frames": int(f[0]), "shown": int(f[1]), "dropped": int(f[2]), "xruns": int(f[3]), "skew": float(f[4]), "late": float(f[5]),
            "clock": float(f[6]), "latency": int(f[7])}


def wait_state(want, timeout):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if state() == want:
            return True
        time.sleep(0.4)
    return False


def sample(seconds, label):
    rows = []
    t0 = time.time()
    while time.time() - t0 < seconds:
        s = stats()
        if s:
            rows.append(s)
        time.sleep(0.5)
    if not rows:
        check(label + ": engine reports stats", False)
        return rows
    sk = [r["skew"] for r in rows]
    lt = max(r["late"] for r in rows)
    print("   %s: skew mean %+.0f ms (min %+.0f max %+.0f), worst lateness %.0f ms, dropped %d of %d, xruns %d, clock %.1f s" % (
        label, sum(sk) / len(sk), min(sk), max(sk), lt, rows[-1]["dropped"], rows[-1]["frames"], rows[-1]["xruns"], rows[-1]["clock"]))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", default="l-u0f9SWvV0")
    ap.add_argument("--stress", action="store_true")
    ap.add_argument("--hogs", type=int, default=8, help="number of CPU hogs in the stress phase")
    ap.add_argument("--nice", type=int, default=0, help="niceness of the hogs; a negative value takes CPU from the app (--nice -10 with 8 hogs made the audio under-run on the M17)")
    ap.add_argument("--stress-seconds", type=int, default=30)
    a = ap.parse_args()
    ctl.forward()
    if ctl.send("ping") != "pong":
        raise SystemExit("control socket not reachable")
    adb("rm -f /mnt/sdcard/Ports/PodTube/logs/podtube.log.bak")
    ev("local P=require('player.player'); P.play({id='%s', title='sync test'}); return 1" % a.video)
    check("playback starts", wait_state("playing", 40), state())
    time.sleep(4)
    rows = sample(8, "from the start")
    if rows:
        check("picture within 60 ms of the sound after the start", abs(sum(r["skew"] for r in rows) / len(rows)) < 60)
        check("no lateness at the start", max(r["late"] for r in rows) < 150)
        check("no device under-runs", rows[-1]["xruns"] == 0)

    for pos in (13.0, 5.5):
        ev("require('player.player').seek(%s); return 1" % pos)
        time.sleep(1)
        check("seek to %.1f s plays again" % pos, wait_state("playing", 30), state())
        time.sleep(4)
        p = float(ev("return require('player.player').position()"))
        check("   position after the seek is where it should be", abs(p - pos - 4) < 3.0, "position %.1f" % p)
        rows = sample(6, "after seek to %.1f" % pos)
        if rows:
            check("   picture within 60 ms of the sound", abs(sum(r["skew"] for r in rows) / len(rows)) < 60)
            check("   not late", max(r["late"] for r in rows) < 150)

    # the end of the video: the engine must report "ended" even with pictures left over
    ev("require('player.player').seek(26.0); return 1")
    time.sleep(1)
    wait_state("playing", 30)
    ev("local P=require('player.player'); P.loops=false; require('core.store').set('autoplay', false); return 1")
    ended = wait_state("ended", 20)
    check("the end of the video is noticed", ended, state())

    if a.stress:
        print("\n-- stress: %d CPU hogs (nice %d) on all cores while the video plays (looping) --" % (a.hogs, a.nice))
        ev("require('core.store').set('autoplay', false); local P=require('player.player'); P.play({id='%s', title='sync test'}); P.loops=true; return 1" % a.video)
        check("playback starts", wait_state("playing", 40), state())
        time.sleep(3)
        # The hogs have to be detached from the adb shell the way net-up.sh detaches dropbear: a background job of the adb shell dies
        # with it (a plain `nohup sh -c '...' &` started nothing at all), so setsid in the foreground and the forking inside.
        # They stop by themselves a little after the stress phase, whatever happens to this script.
        adb("setsid sh -c 'i=0; while [ $i -lt %d ]; do nice -n %d dd if=/dev/zero of=/dev/null bs=1M </dev/null >/dev/null 2>&1 & i=$((i+1)); done; "
            "(sleep %d; killall dd) </dev/null >/dev/null 2>&1 &' </dev/null >/dev/null 2>&1" % (a.hogs, a.nice, a.stress_seconds + 40))
        time.sleep(1)
        running = adb("pidof dd | wc -w").strip()
        check("the CPU hogs are running", running == str(a.hogs), "%s of %d" % (running, a.hogs))
        t0 = time.time()
        lates, repairs, nextshow = [], 0, 0
        while time.time() - t0 < a.stress_seconds:
            s = stats()
            if s:
                lates.append(s["late"])
            fixes = ev("return require('player.player').sync_fixes")
            repairs = int(fixes) if fixes.isdigit() else repairs
            if s and time.time() - t0 >= nextshow:
                nextshow += 5
                print("   +%2.0f s: late %5.0f ms, skew %+5.0f ms, dropped %d, xruns %d, repairs %d" % (time.time() - t0, s["late"], s["skew"], s["dropped"], s["xruns"], repairs))
            time.sleep(1)
        print("   worst lateness %.0f ms, repairs %d" % (max(lates) if lates else -1, repairs))
        adb("killall dd 2>/dev/null; true")
        # the load is over: playback has to be back in step by itself (a repair may still be restarting the engine)
        time.sleep(4)
        check("playing again after the load", wait_state("playing", 40), state())
        time.sleep(4)
        rows = sample(6, "after the load")
        if rows:
            check("   in step again after the load", abs(sum(r["skew"] for r in rows) / len(rows)) < 60 and max(r["late"] for r in rows) < 150)
        ev("require('player.player').loops=false; return 1")
        log = subprocess.run(["adb", "shell", "grep -E 'sync:|first picture' /mnt/sdcard/Ports/PodTube/logs/podtube.log | tail -10"],
                             capture_output=True, env=ENV).stdout.decode("utf-8", "replace")
        print(log)
    print("\n%s" % ("ALL OK" if not fails else "FAILED: %s" % fails))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
