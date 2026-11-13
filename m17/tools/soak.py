#!/usr/bin/env python3
"""長時間再生の安定性試験: 再生しながら一定間隔で状態を記録し、途中でシーク・一時停止も行う。

  python tools/soak.py [秒数=180] [間隔=15]

事前に端末でアプリを起動しておく(ホームの先頭の動画を A で開く所から始める)。
"""
import json, subprocess, sys, time, os

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ctl


def ev(code):
    return ctl.send("eval " + code)


def adb_sh(cmd):
    env = dict(os.environ, MSYS_NO_PATHCONV="1", MSYS2_ARG_CONV_EXCL="*")
    return subprocess.run(["adb", "shell", cmd], capture_output=True, env=env, timeout=30).stdout.decode(errors="replace")


def sample():
    st = ev("local P=require('player.player'); local E=require('player.engine'); local s=E.stats() or {}; return {state=P.state, pos=P.position(), dur=P.duration(), shown=s.displayed, dropped=s.dropped, xruns=s.xruns, delay=s.delay_ms, mem=collectgarbage('count')}")
    try:
        d = json.loads(st)
    except Exception:
        d = {"raw": st}
    ps = adb_sh("for p in $(pidof love.armhf ffmpeg); do echo $p $(grep -E 'VmRSS' /proc/$p/status | tr -s ' ') $(cat /proc/$p/comm); done; grep -E 'MemAvailable' /proc/meminfo; cat /proc/loadavg")
    d["ps"] = " | ".join(l.strip() for l in ps.strip().splitlines())
    return d


def main():
    total = int(sys.argv[1]) if len(sys.argv) > 1 else 180
    every = int(sys.argv[2]) if len(sys.argv) > 2 else 15
    ctl.forward()
    t0 = time.time()
    n = 0
    actions = {45: ("key", "right"), 60: ("key", "right"), 90: ("key", "a"), 96: ("key", "a")}
    done = set()
    while time.time() - t0 < total:
        el = int(time.time() - t0)
        for at, (kind, k) in actions.items():
            if el >= at and at not in done:
                done.add(at)
                ctl.send("key " + k)
                print("  [action] %s %s at %ds" % (kind, k, el))
        d = sample()
        print("%4ds %s" % (el, json.dumps(d, ensure_ascii=False)))
        time.sleep(every)


if __name__ == "__main__":
    main()
