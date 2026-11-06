#!/usr/bin/env python3
"""build_web.py - turns web/ into the files that go to ~/www/podtube/ (no network, no external tools).

  index.html            the <script>/<link> lists between the BUNDLE markers become one hashed file each
  assets/app.<h>.js     all scripts of index.html concatenated, in order
  assets/app.<h>.css    app.css after cssfix.py (flexbox gap, sticky: Safari 12)
  sw.js                 version = hash of everything, PRECACHE = the files of the shell
  vendor/ icons/ manifest.webmanifest   copied as they are

usage: python build/build_web.py [out-dir]       prints a one-line summary
"""
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, "web")
sys.path.insert(0, HERE)
import cssfix  # noqa: E402


def read(path, mode="rb"):
    with open(path, mode) as f:
        return f.read()


def digest(*chunks):
    h = hashlib.sha1()
    for c in chunks:
        h.update(c if isinstance(c, bytes) else c.encode("utf-8"))
    return h.hexdigest()[:10]


def build():
    """Returns ({relative path: bytes}, version)."""
    files = {}
    index = open(os.path.join(WEB, "index.html"), encoding="utf-8").read().replace("\r\n", "\n")

    # ---- javascript bundle (the order of the <script> tags)
    m = re.search(r"<!-- BUNDLE-JS -->(.*?)<!-- /BUNDLE-JS -->", index, re.S)
    scripts = re.findall(r'<script src="(js/[^"]+)"></script>', m.group(1))
    parts = []
    for rel in scripts:
        src = open(os.path.join(WEB, rel), encoding="utf-8").read().replace("\r\n", "\n")
        parts.append("/* ==== %s ==== */\n%s" % (rel, src.rstrip("\n")))
    js = ";\n".join(parts) + "\n"
    jsname = "assets/app.%s.js" % digest(js)
    files[jsname] = js.encode("utf-8")

    # ---- stylesheet
    m2 = re.search(r"<!-- BUNDLE-CSS -->(.*?)<!-- /BUNDLE-CSS -->", index, re.S)
    css_rels = re.findall(r'<link rel="stylesheet" href="(css/[^"]+)">', m2.group(1))
    css = "\n".join(cssfix.fix(open(os.path.join(WEB, r), encoding="utf-8").read().replace("\r\n", "\n")) for r in css_rels)
    cssname = "assets/app.%s.css" % digest(css)
    files[cssname] = css.encode("utf-8")

    # ---- vendor libraries, icons, manifest
    hls_ver = "1.5.20"                    # hls.js in vendor/ (see vendor/hls.LICENSE.txt); the query string busts the cache on an upgrade
    for rel in ("vendor/hls.min.js", "vendor/hls.LICENSE.txt", "vendor/qrcode.js"):
        files[rel] = read(os.path.join(WEB, rel))
    for name in sorted(os.listdir(os.path.join(WEB, "icons"))):
        files["icons/" + name] = read(os.path.join(WEB, "icons", name))
    files["manifest.webmanifest"] = read(os.path.join(WEB, "manifest.webmanifest"))

    # ---- index.html
    html = index.replace(m.group(0), '<script src="%s"></script>' % jsname)
    html = html.replace(m2.group(0), '<link rel="stylesheet" href="%s">' % cssname)
    html = html.replace('vendor/hls.min.js"', 'vendor/hls.min.js?v=%s"' % hls_ver)
    files["index.html"] = html.encode("utf-8")

    # ---- service worker
    version = digest(*[files[k] for k in sorted(files)])
    precache = ["./", "index.html", jsname, cssname, "manifest.webmanifest", "icons/icon-192.png", "icons/icon-512.png",
                "icons/apple-touch-icon.png", "icons/favicon-32.png", "vendor/hls.min.js?v=%s" % hls_ver, "vendor/qrcode.js"]
    sw = open(os.path.join(WEB, "sw.js"), encoding="utf-8").read().replace("\r\n", "\n")
    sw = sw.replace("__VERSION__", version).replace("__PRECACHE__", json.dumps(precache))
    files["sw.js"] = sw.encode("utf-8")
    return files, version


def write(out):
    files, version = build()
    for rel, data in files.items():
        p = os.path.join(out, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(data)
    return files, version


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "out", "web")
    files, version = write(out)
    total = sum(len(v) for v in files.values())
    print("built %d files, %.0f KB, version %s -> %s" % (len(files), total / 1024, version, out))
