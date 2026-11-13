#!/usr/bin/env python3
"""Noto Sans JP(可変フォント、SIL OFL)から、固定ウェイトの静的フォントを作る。
LÖVE(FreeType)は可変フォントの軸を選べないため、400/500/700 を別ファイルにして app/fonts/ に置く。
入力: C:/Windows/Fonts/NotoSansJP-VF.ttf (または app/fonts/NotoSansJP-VF.ttf)
"""
import os
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "app", "fonts", "NotoSansJP-VF.ttf")  # (app/fonts に無ければ Windows のものを使う)
if not os.path.exists(SRC):
    SRC = r"C:\Windows\Fonts\NotoSansJP-VF.ttf"

for name, w in (("Regular", 400), ("Medium", 500), ("Bold", 700)):
    f = TTFont(SRC)
    axes = {a.axisTag: a for a in f["fvar"].axes}
    print(name, "axes:", {k: (v.minValue, v.defaultValue, v.maxValue) for k, v in axes.items()})
    inst = instancer.instantiateVariableFont(f, {"wght": w}, inplace=False)
    out = os.path.join(ROOT, "app", "fonts", "NotoSansJP-%s.ttf" % name)
    inst.save(out)
    print("  ->", out, os.path.getsize(out))
