#!/usr/bin/env python3
"""app/ の全 Lua ファイルを LuaJIT 2.1(lupa)で構文検査する。配備の前に流す。
  python tools/luacheck.py          → エラーがあれば表示して終了コード 1
"""
import os, sys
import lupa.luajit21 as lj

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app")
rt = lj.LuaRuntime(unpack_returned_tuples=True)
loadstring = rt.eval("loadstring")

bad = 0
n = 0
for dp, dn, fn in os.walk(APP):
    for f in sorted(fn):
        if not f.endswith(".lua"):
            continue
        p = os.path.join(dp, f)
        src = open(p, "rb").read()
        n += 1
        res = loadstring(src, "@" + os.path.relpath(p, APP))
        if isinstance(res, tuple):
            bad += 1
            print("SYNTAX ERROR:", res[1])
print("checked %d files, %d with errors" % (n, bad))
sys.exit(1 if bad else 0)
