#!/usr/bin/env python3
"""M17 開発用の道具。PC から端末のアプリを入れ替え・起動・停止・撮影する。

  python tools/dev.py push            app/ を端末へ送る(差分ではなく全部。フォントは重いので --fonts のときだけ)
  python tools/dev.py launch          MinUI を終了させて PodTube を起動(MinUI の ports と同じ手順)
  python tools/dev.py stop            PodTube を終了(MinUI に戻る)
  python tools/dev.py log [N]         端末側のログの末尾
  python tools/dev.py shot [out.png]  画面を撮る(tools/fbshot.py)
  python tools/dev.py run             push → launch(再起動)
  python tools/dev.py provision       サーバー設定(secrets/pt_key)を端末へ
  python tools/dev.py debug on|off    制御ソケット用の debug.flag(ctl.py はこれが on のときだけ使える)
"""
import os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ADB = os.environ.get("ADB", "adb")
DEV_APP = "/mnt/sdcard/Ports/PodTube"
LAUNCHER = "/mnt/sdcard/Roms/Ports (SH)/PodTube.sh"


def adb(*args, timeout=120, check=False):
    env = dict(os.environ, MSYS_NO_PATHCONV="1", MSYS2_ARG_CONV_EXCL="*")
    r = subprocess.run([ADB, *args], capture_output=True, env=env, timeout=timeout)
    out = (r.stdout + r.stderr).decode("utf-8", "replace").replace("\r", "")
    if check and r.returncode:
        raise SystemExit(out)
    return out


def sh(cmd, timeout=120):
    return adb("shell", cmd, timeout=timeout)


def push(with_fonts=False):
    app = os.path.join(ROOT, "app")
    sh(f"mkdir -p {DEV_APP}/app")
    # フォント以外を送る(重いので既定では送らない)
    for name in sorted(os.listdir(app)):
        p = os.path.join(app, name)
        if name == "fonts" and not with_fonts:
            continue
        out = adb("push", p, f"{DEV_APP}/app/", timeout=600)
    out = adb("push", os.path.join(ROOT, "device", "PodTube.sh"), LAUNCHER)
    sh(f'chmod 755 "{LAUNCHER}"')
    print("pushed")


def provision():
    """サーバー設定(アドレスとアクセスキー)を端末のデータ置き場に書く。キーは secrets/pt_key から(画面には出さない)。"""
    key = open(os.path.join(ROOT, "secrets", "pt_key")).read().strip()
    cfg = '{"base":"https://my-dev.sakura.ne.jp/podtube","key":"%s"}' % key
    save = f"{DEV_APP}/love/podtube"
    sh(f"mkdir -p {save}")
    tmp = os.path.join(ROOT, "secrets", "server.json")
    open(tmp, "w", newline="").write(cfg)
    adb("push", tmp, f"{save}/server.json")
    os.remove(tmp)
    print("provisioned (server.json)")


def running():
    return sh("pidof love.armhf").strip()


def stop():
    sh("killall love.armhf 2>/dev/null; sleep 1; killall -9 love.armhf 2>/dev/null; killall ffmpeg 2>/dev/null; true")
    for _ in range(20):
        if sh("pidof minui.elf").strip():
            break
        time.sleep(0.5)
    print("stopped; minui:", sh("pidof minui.elf").strip() or "(not yet)")


def launch():
    if running():
        stop()
        time.sleep(1)
    sh(f"echo 'sh \"{LAUNCHER}\"' > /tmp/next; killall -9 minui.elf")
    for _ in range(20):
        time.sleep(0.5)
        if running():
            break
    print("launched; love pid:", running() or "(none)")


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return
    c = a[0]
    if c == "push":
        push("--fonts" in a)
    elif c == "provision":
        provision()
    elif c == "debug":
        on = len(a) < 2 or a[1] != "off"
        sh(f"touch {DEV_APP}/debug.flag" if on else f"rm -f {DEV_APP}/debug.flag")
        print("debug.flag", "on (制御ソケット 127.0.0.1:7777 は次の起動から)" if on else "off")
    elif c == "launch":
        launch()
    elif c == "stop":
        stop()
    elif c == "run":
        push("--fonts" in a)
        launch()
    elif c == "log":
        n = a[1] if len(a) > 1 else "40"
        print(sh(f"tail -n {n} {DEV_APP}/logs/podtube.log"))
    elif c == "shot":
        subprocess.run([sys.executable, os.path.join(HERE, "fbshot.py")] + a[1:])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
