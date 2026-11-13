#!/usr/bin/env python3
"""端末の PodTube の制御ソケット(127.0.0.1:7777、debug.flag があるときだけ)を PC から操作する。

  python tools/ctl.py key down a            ボタンを押す(複数可: key の後に並べる)
  python tools/ctl.py hold right 600        押しっぱなし(ミリ秒)
  python tools/ctl.py text 猫               OSK/検索欄に文字を入れる
  python tools/ctl.py eval "App.top().name" Lua を実行して結果を表示
  python tools/ctl.py state                 画面名・FPS・メモリ
  python tools/ctl.py reload                アプリを再起動(Lua を読み直す)
  python tools/ctl.py shot [name]           (少し待って)画面を撮る → shots/name.png
  python tools/ctl.py seq "down down a" [--shot name] [--wait 0.4]
"""
import os, socket, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PORT = 7777


def forward():
    env = dict(os.environ, MSYS_NO_PATHCONV="1", MSYS2_ARG_CONV_EXCL="*")
    subprocess.run(["adb", "forward", f"tcp:{PORT}", f"tcp:{PORT}"], capture_output=True, env=env)


def send(line, timeout=8.0):
    for attempt in range(2):
        try:
            with socket.create_connection(("127.0.0.1", PORT), timeout=timeout) as s:
                s.settimeout(timeout)
                s.sendall(line.encode("utf-8") + b"\n")
                buf = b""
                while not buf.endswith(b"\n"):
                    d = s.recv(65536)
                    if not d:
                        break
                    buf += d
                return buf.decode("utf-8", "replace").rstrip("\n").replace("\\n", "\n")
        except OSError:
            if attempt == 0:
                forward()
                time.sleep(0.2)
            else:
                raise
    return ""


def shot(name):
    time.sleep(0.15)
    out = os.path.join(ROOT, "shots", name + ".png")
    subprocess.run([sys.executable, os.path.join(HERE, "fbshot.py"), out])
    return out


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return
    forward()
    c = a[0]
    if c == "key":
        for k in a[1:]:
            print(send("key " + k))
            time.sleep(0.12)
    elif c == "hold":
        k, ms = a[1], int(a[2]) / 1000.0
        send("key %s press" % k)
        time.sleep(ms)
        send("key %s release" % k)
    elif c == "text":
        print(send("text " + " ".join(a[1:])))
    elif c == "eval":
        print(send("eval " + " ".join(a[1:])))
    elif c in ("state", "reload", "quit", "ping"):
        print(send(c))
    elif c == "shot":
        print(shot(a[1] if len(a) > 1 else "latest"))
    elif c == "seq":
        keys = a[1].split()
        wait = 0.35
        name = None
        if "--wait" in a:
            wait = float(a[a.index("--wait") + 1])
        if "--shot" in a:
            name = a[a.index("--shot") + 1]
        for k in keys:
            if k.startswith("w") and k[1:].replace(".", "").isdigit():
                time.sleep(float(k[1:]))
                continue
            send("key " + k)
            time.sleep(wait)
        if name:
            print(shot(name))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
