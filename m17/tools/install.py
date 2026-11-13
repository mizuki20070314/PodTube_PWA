#!/usr/bin/env python3
"""M17 に PodTube を入れる(初回・更新どちらでも)。

  python tools/install.py [--debug] [--no-key] [--no-fonts]

  1. 端末に /mnt/sdcard/Ports/PodTube を作り、LÖVE の実行ファイル(bin/)と共有ライブラリ(libs/)を
     既存の Balatro ポートから複製する(無ければ vendor/ にあるものを送る)
  2. app/(フォント込み)とランチャー(Roms/Ports (SH)/PodTube.sh)を送る
  3. secrets/pt_key があればサーバー設定(アドレスとアクセスキー)を端末に書く(画面にも出力しない)
  4. --debug のときだけ、PC から画面操作できる制御ソケット用の debug.flag を作る(既定では作らない)

MinUI の Ports に「PodTube」が出ます。ネットワークが無い端末なので、PC で m17-net.sh(トンネル)を動かして使います。
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import dev  # noqa: E402

APP = dev.DEV_APP


def main():
    args = sys.argv[1:]
    if dev.sh("echo ok").strip() != "ok":
        raise SystemExit("端末に adb でつながりません")
    have_bin = dev.sh(f"[ -x {APP}/bin/love.armhf ] && [ -d {APP}/libs ] && echo yes").strip() == "yes"
    if not have_bin:
        src = "/mnt/sdcard/Ports/Balatro"
        if dev.sh(f"[ -x {src}/bin/love.armhf ] && echo yes").strip() == "yes":
            print("LÖVE を Balatro ポートから複製します ...")
            dev.sh(f"mkdir -p {APP} && cp -a {src}/bin {APP}/ && cp -a {src}/libs {APP}/", timeout=300)
        else:
            vendor = os.path.join(ROOT, "vendor")
            if os.path.isdir(os.path.join(vendor, "bin")):
                print("vendor/ から LÖVE を送ります ...")
                dev.sh(f"mkdir -p {APP}")
                dev.adb("push", os.path.join(vendor, "bin"), f"{APP}/", timeout=600)
                dev.adb("push", os.path.join(vendor, "libs"), f"{APP}/", timeout=600)
            else:
                raise SystemExit("LÖVE の実行ファイルがありません(端末の Ports/Balatro か、PC の vendor/bin, vendor/libs が必要)")
    dev.push(with_fonts="--no-fonts" not in args)
    if "--no-key" not in args and os.path.exists(os.path.join(ROOT, "secrets", "pt_key")):
        dev.provision()
    if "--debug" in args:
        dev.sh(f"touch {APP}/debug.flag")
        print("debug.flag を作りました(制御ソケット 127.0.0.1:7777 が有効)")
    elif "--debug" not in args:
        dev.sh(f"rm -f {APP}/debug.flag")
    print("インストール完了: MinUI の Ports > PodTube から起動できます")


if __name__ == "__main__":
    main()
