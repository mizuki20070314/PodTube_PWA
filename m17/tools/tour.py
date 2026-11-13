#!/usr/bin/env python3
"""主要な画面を順に巡る回帰試験(制御ソケット経由)。各ステップで画面名を確かめ、最後にログの E 行を数える。

  python tools/tour.py [--shots]      --shots で各ステップの画面を shots/tour_*.png に残す
事前: python tools/dev.py debug on → 端末でアプリを起動(ネットワークのトンネルが動いていること)
"""
import json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ctl

SHOTS = "--shots" in sys.argv
fails = []


def screen():
    try:
        return json.loads(ctl.send("state"))["screen"]
    except Exception as e:
        return "?" + str(e)


def key(*ks, wait=0.35):
    for k in ks:
        ctl.send("key " + k)
        time.sleep(wait)


def expect(label, want, wait=0.0, shot=None):
    time.sleep(wait)
    got = screen()
    ok = got == want
    print("%-34s -> %-12s %s" % (label, got, "OK" if ok else "NG (want %s)" % want))
    if not ok:
        fails.append(label)
    if SHOTS and shot:
        ctl.shot("tour_" + shot)


def state_eval(code):
    return ctl.send("eval " + code)


def wait_for(code, want, timeout=30):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if state_eval(code) == want:
            return True
        time.sleep(0.5)
    return False


def main():
    ctl.forward()
    if ctl.send("ping") != "pong":
        raise SystemExit("制御ソケットに届きません(debug.flag と起動を確認)")
    state_eval("App.pop_to_root(); App.goto_tab(1); return 1")
    time.sleep(1)
    expect("home", "home", shot="home")
    wait_for("App.top().feed.state", "ready", 40)
    key("a")
    expect("open first video", "watch", 1.0)
    wait_for("require('player.player').state", "playing", 40)
    print("   player state:", state_eval("require('player.player').state"))
    key("up")
    expect("hud (still watch)", "watch", 0.5, shot="watch_full")
    key("start")
    expect("details (still watch)", "watch", 0.5, shot="watch_details")
    key("b")
    expect("back to home (mini player)", "home", 0.8, shot="home_mini")
    key("select")
    expect("select opens now playing", "watch", 0.8)
    key("b", "b")
    expect("back to home again", "home", 0.8)
    key("y")
    expect("search", "search", 0.8, shot="search")
    ctl.send("text ねこ")
    time.sleep(2.5)
    key("start")
    expect("results", "results", 4.0, shot="results")
    key("b")
    expect("back", "home", 0.8)
    for name, steps in (("shorts", ["left", "down", "a"]), ("subs", ["left", "down", "a"]), ("you", ["left", "down", "a"])):
        key(*steps)
        expect("tab " + name, name, 1.5 if name == "shorts" else 0.8, shot="tab_" + name)
    key("down", "down", "down", "down", "down", "down", "a")
    expect("settings", "settings", 0.8, shot="settings")
    key("b")
    expect("back to you", "you", 0.6)
    key("left", "up", "up", "up", "up", "a")
    expect("search from rail", "search", 0.8)
    key("b")
    expect("back", "you", 0.6)
    log = subprocess.run(["adb", "shell", "grep -c ' E ' /mnt/sdcard/Ports/PodTube/logs/podtube.log"], capture_output=True,
                         env=dict(os.environ, MSYS_NO_PATHCONV="1")).stdout.decode().strip()
    print("log error lines:", log)
    print("\nRESULT:", "ALL OK" if not fails and log in ("0", "") else "FAILED %s (errors in log: %s)" % (fails, log))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
