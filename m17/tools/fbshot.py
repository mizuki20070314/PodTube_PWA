#!/usr/bin/env python3
"""M17 の画面を撮って PNG にする(アシスタントが自分で画面を確認するための道具)。

  python tools/fbshot.py [出力.png] [--fb] [--scale N]

既定は KMS の走査面(/userdata/bin/kmsshot)。MinUI も LÖVE(SDL2 kmsdrm)も DRM で描くので /dev/fb0 は
真っ黒のまま。fbdev で描くアプリ(PC Mirror の ffmpeg -f fbdev など)を見るときは --fb で /dev/fb0 を読む。

この adbd は `adb exec-out` も `adb reverse` も使えず、`adb shell cat` は改行変換でバイナリが壊れるので、
端末の tmpfs に書いてから `adb pull` する。
"""
import os, re, subprocess, sys, tempfile

W, H = 480, 272
ADB = os.environ.get("ADB", "adb")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(os.path.dirname(HERE), "shots")


def adb(*args, timeout=30):
    env = dict(os.environ, MSYS_NO_PATHCONV="1", MSYS2_ARG_CONV_EXCL="*")
    return subprocess.run([ADB, *args], capture_output=True, env=env, timeout=timeout)


def grab_kms():
    r = adb("shell", "/userdata/bin/kmsshot /tmp/kms 2>&1; echo rc=$?")
    txt = r.stdout.decode(errors="replace")
    planes = []
    for line in txt.splitlines():
        m = re.match(r"plane=(\d+) crtc=(\d+) fb=(\d+) w=(\d+) h=(\d+) pitch=(\d+) bpp=(\d+) depth=(\d+) how=(\w+) file=(\S+)", line.strip())
        if m:
            planes.append(dict(plane=int(m[1]), w=int(m[4]), h=int(m[5]), pitch=int(m[6]), bpp=int(m[7]), path=m[10]))
    if not planes:
        raise SystemExit("kmsshot: 取得できず\n" + txt)
    p = planes[0]
    with tempfile.TemporaryDirectory() as td:
        dst = os.path.join(td, "p.raw")
        adb("pull", p["path"], dst)
        data = open(dst, "rb").read()
    return p, data


def grab_fb():
    r = adb("shell", f"dd if=/dev/fb0 of=/tmp/fb.raw bs={W*H*4} count=1 2>/dev/null")
    with tempfile.TemporaryDirectory() as td:
        dst = os.path.join(td, "fb.raw")
        adb("pull", "/tmp/fb.raw", dst)
        data = open(dst, "rb").read()
    return dict(w=W, h=H, pitch=W * 4, bpp=32), data


def to_png(p, data, path, scale=1):
    from PIL import Image
    import numpy as np
    w, h, pitch = p["w"], p["h"], p["pitch"]
    a = np.frombuffer(data[: pitch * h], dtype=np.uint8).reshape(h, pitch)[:, : w * 4].reshape(h, w, 4)
    rgb = a[:, :, [2, 1, 0]]  # XRGB8888(リトルエンディアン) = メモリ上 B,G,R,X
    im = Image.fromarray(np.ascontiguousarray(rgb), "RGB")
    if scale != 1:
        im = im.resize((w * scale, h * scale), Image.NEAREST)
    im.save(path)


def main():
    args = [a for a in sys.argv[1:]]
    use_fb = "--fb" in args
    scale = 1
    if "--scale" in args:
        i = args.index("--scale")
        scale = int(args[i + 1])
        del args[i:i + 2]
    args = [a for a in args if a != "--fb"]
    out = args[0] if args else os.path.join(OUT_DIR, "latest.png")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    p, data = grab_fb() if use_fb else grab_kms()
    to_png(p, data, out, scale)
    print(out, "%dx%d pitch=%d" % (p["w"], p["h"], p["pitch"]))


if __name__ == "__main__":
    main()
