#!/usr/bin/env python3
"""deploy.py - install the PodTube PWA on the Sakura rental server.

  ~/www/podtube/            the PWA (static files) + api.cgi + .htaccess      -> https://my-dev.sakura.ne.jp/podtube/
  ~/.podtube/code/podtube/  the CGI's Python code (outside the web root)
  ~/.podtube/config.json    created once (a random access key), never overwritten
  ~/.podtube/{cache,log}/   runtime files of the CGI (never touched by a deploy)

Nothing is started on the server and no cron job is needed: Apache runs api.cgi per request.
Other apps in ~/www are not touched.

usage: python deploy.py [--stage-only] [--base /podtube] [--skip-checks]
"""
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRV = os.path.join(ROOT, "srv")
sys.path.insert(0, HERE)
import build_web  # noqa: E402

RSH = [sys.executable, os.path.join(HERE, "rsh.py")]
HOST_URL = "https://my-dev.sakura.ne.jp"


def srv_file(name):
    with open(os.path.join(SRV, name), "rb") as f:
        return f.read()

INSTALL = r"""
set -e
umask 022
mkdir -p ~/tmp ~/.podtube/code ~/.podtube/cache/sess ~/.podtube/log
chmod 700 ~/.podtube

# ---- code (replaced as a whole)
rm -rf ~/.podtube/code/podtube.new && mkdir ~/.podtube/code/podtube.new
tar -xzf ~/tmp/podtube-code.tgz -C ~/.podtube/code/podtube.new
chmod 644 ~/.podtube/code/podtube.new/*.py
[ -d ~/.podtube/code/podtube ] && mv ~/.podtube/code/podtube ~/.podtube/code/podtube.old
mv ~/.podtube/code/podtube.new ~/.podtube/code/podtube
rm -rf ~/.podtube/code/podtube.old

# ---- config: created once (a random access key), never overwritten
if [ ! -f ~/.podtube/config.json ]; then
  /usr/local/bin/python3 - <<'PYEOF'
import json, os, secrets
alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
key = "".join(secrets.choice(alphabet) for _ in range(20))
path = os.path.expanduser("~/.podtube/config.json")
with open(path, "w") as f:
    json.dump({"require_key": True, "access_key": key}, f, indent=2)
os.chmod(path, 0o600)
print("config.json created")
PYEOF
fi
chmod 600 ~/.podtube/config.json

# ---- web (replaced as a whole)
cd ~/www
if [ -e podtube ] && ! grep -q 'PodTube PWA' podtube/api.cgi 2>/dev/null; then
  echo "REFUSING: ~/www/podtube exists and is not an install of this app - nothing was changed there"
  exit 3
fi
rm -rf podtube.new && mkdir podtube.new
tar -xzf ~/tmp/podtube-web.tgz -C podtube.new
find podtube.new -type d -exec chmod 755 {} +
find podtube.new -type f -exec chmod 644 {} +
chmod 755 podtube.new/api.cgi
if [ -d podtube ]; then
  echo "replacing existing podtube (had: $(ls podtube | tr '\n' ' ' | cut -c1-120))"
  rm -rf podtube.old && mv podtube podtube.old
fi
mv podtube.new podtube
rm -rf podtube.old ~/tmp/podtube-web.tgz ~/tmp/podtube-code.tgz

echo "--- installed"
du -sh ~/www/podtube ~/.podtube/code 2>/dev/null
echo "--- CGI smoke test (clean environment, run by its shebang)"
head -1 ~/www/podtube/api.cgi
env -i REQUEST_METHOD=GET QUERY_STRING= PATH_INFO=/health SCRIPT_NAME=/podtube/api.cgi ~/www/podtube/api.cgi | tr -d '\r'
"""


def tar_bytes(files, modes=None):
    buf = io.BytesIO()
    now = int(time.time())
    with tarfile.open(fileobj=buf, mode="w:gz", compresslevel=9) as tf:
        for rel in sorted(files):
            data = files[rel]
            if rel.endswith((".cgi", ".py")):
                data = data.replace(b"\r\n", b"\n")                # a shebang must not end in CR
            ti = tarfile.TarInfo(rel)
            ti.size = len(data)
            ti.mode = (modes or {}).get(rel, 0o644)
            ti.uid = ti.gid = 0
            ti.uname = ti.gname = ""
            ti.mtime = now                                          # real mtime: nginx sends Last-Modified, browsers guess freshness from it
            tf.addfile(ti, io.BytesIO(data))
    return buf.getvalue()


def rsh(script, timeout=180):
    env = dict(os.environ, MSYS_NO_PATHCONV="1", PYTHONIOENCODING="utf-8")
    return subprocess.run(RSH + ["-t", str(timeout), "-"], input=script.encode("utf-8"), env=env)


def put(data, remote):
    tmp = os.path.join(HERE, "deploy-upload.tgz")
    with open(tmp, "wb") as f:
        f.write(data)
    try:
        subprocess.check_call(RSH + ["--put", tmp, remote], env=dict(os.environ, MSYS_NO_PATHCONV="1"))
    finally:
        os.unlink(tmp)


def remote_value(cmd, timeout=60):
    p = subprocess.run(RSH + ["-t", str(timeout), "-"], input=(cmd + "\n").encode(), env=dict(os.environ, MSYS_NO_PATHCONV="1", PYTHONIOENCODING="utf-8"), capture_output=True)
    return p.stdout.decode("utf-8", "replace").strip()


def http_get(url, headers=None, timeout=60):
    req = urllib.request.Request(url, headers=dict({"User-Agent": "podtube-deploy-check", "Accept-Encoding": "identity"}, **(headers or {})))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def main():
    argv = sys.argv[1:]
    base = argv[argv.index("--base") + 1] if "--base" in argv else "/podtube"
    base_url = HOST_URL + base + "/"

    files, version = build_web.build()
    files["api.cgi"] = srv_file("api.cgi")
    files[".htaccess"] = srv_file("htaccess-minimal")            # the full one is tried after the first checks (see below)
    files["assets/.htaccess"] = srv_file("htaccess-assets")
    code = {}
    pkg = os.path.join(SRV, "podtube")
    for name in sorted(os.listdir(pkg)):
        if name.endswith(".py"):
            code[name] = open(os.path.join(pkg, name), "rb").read()
    web_tgz = tar_bytes(files, {"api.cgi": 0o755})
    code_tgz = tar_bytes(code)
    print("web %s: %d files, %.1f MB;  code: %d files, %.0f KB" % (version, len(files), len(web_tgz) / 1e6, len(code), len(code_tgz) / 1e3))
    if "--stage-only" in argv:
        out = os.path.join(HERE, "out", "stage")
        for rel, data in files.items():
            p = os.path.join(out, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "wb").write(data)
        print("staged in", out)
        return 0

    put(code_tgz, "/home/my-dev/tmp/podtube-code.tgz")
    put(web_tgz, "/home/my-dev/tmp/podtube-web.tgz")
    p = rsh(INSTALL)
    if p.returncode != 0:
        print("install failed, exit", p.returncode)
        return p.returncode

    if "--skip-checks" in argv:
        return 0
    print("\n--- public checks (%s)" % base_url)
    ok = True
    for path, want in (("", b"assets/app."), ("sw.js", b"PRECACHE"), ("manifest.webmanifest", b"start_url"), ("icons/icon-192.png", b"\x89PNG")):
        st, hd, body = http_get(base_url + path)
        good = st == 200 and want in body
        print("%-24s %s %-34s %8d bytes  %s" % (path or "(index)", st, hd.get("Content-Type", ""), len(body), "" if good else "  <-- PROBLEM"))
        ok &= good
    st, hd, body = http_get(base_url + "api.cgi/health")
    print("api.cgi/health           %s %s" % (st, body[:90]))
    ok &= st == 200

    # ---- the full .htaccess (headers, compression); the minimal one is restored if the server refuses it
    full = srv_file("htaccess").decode("utf-8")
    mini = srv_file("htaccess-minimal").decode("utf-8")
    print("\n--- trying the full .htaccess; the minimal one is restored if the server refuses it")
    rsh("cat > ~/www/podtube/.htaccess <<'PTEOF'\n%sPTEOF\nchmod 644 ~/www/podtube/.htaccess\necho written\n" % full, 60)
    js = [k for k in files if k.startswith("assets/app.") and k.endswith(".js")][0]
    st1, hd1, b1 = http_get(base_url)
    st2, hd2, b2 = http_get(base_url + js, {"Accept-Encoding": "gzip"})
    st3, hd3, b3 = http_get(base_url + "api.cgi/health")
    st4, hd4, b4 = http_get(base_url + "sw.js")
    print("index %s (Cache-Control: %s) | %s %s (Content-Encoding: %s, Cache-Control: %s, %d bytes) | api.cgi/health %s | sw.js %s (Cache-Control: %s)" % (
        st1, hd1.get("Cache-Control"), js, st2, hd2.get("Content-Encoding"), hd2.get("Cache-Control"), len(b2), st3, st4, hd4.get("Cache-Control")))
    if not (st1 == 200 and st2 == 200 and st3 == 200 and st4 == 200):
        print("full .htaccess refused -> restoring the minimal one")
        rsh("cat > ~/www/podtube/.htaccess <<'PTEOF'\n%sPTEOF\nchmod 644 ~/www/podtube/.htaccess\n" % mini, 60)
        return 1
    print("\nOK" if ok else "\nPROBLEMS - see above")
    print("deployed web %s" % version)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
