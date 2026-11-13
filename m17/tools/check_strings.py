#!/usr/bin/env python3
"""app/ の Lua が I.t("...") で使う文言キーが app/data/strings.lua(PWA 由来)か app/data/strings_m17.lua にあるかを確認する。"""
import os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app")


def keys_of(path):
    if not os.path.exists(path):
        return set()
    s = open(path, encoding="utf-8").read()
    return set(re.findall(r'^\s*\["([^"]+)"\]\s*=', s, re.M))


have = keys_of(os.path.join(APP, "data", "strings.lua")) | keys_of(os.path.join(APP, "data", "strings_m17.lua"))
used = {}
for dp, dn, fn in os.walk(APP):
    for f in fn:
        if f.endswith(".lua") and not f.startswith("strings"):
            p = os.path.join(dp, f)
            for m in re.finditer(r'\bI\.t\(\s*"([^"]+)"', open(p, encoding="utf-8").read()):
                used.setdefault(m.group(1), set()).add(os.path.relpath(p, APP))
missing = sorted(k for k in used if k not in have)
print("used keys:", len(used), "missing:", len(missing))
for k in missing:
    print("  ", k, "<-", ", ".join(sorted(used[k])))
sys.exit(1 if missing else 0)
