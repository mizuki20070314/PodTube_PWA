"""Paths and operator settings.

Everything the CGI writes lives in one directory outside the web root:

  ~/.podtube/config.json   operator switches (created once by the installer, never overwritten)
  ~/.podtube/cache/        sessions of the media relay, the client-override cache (safe to delete)
  ~/.podtube/log/          a few lines per problem (no URLs with tokens)
"""
import hmac
import json
import os
import time

HOME = os.environ.get("PT_HOME") or os.path.join(os.path.expanduser("~"), ".podtube")
CACHE = os.path.join(HOME, "cache")
SESS = os.path.join(CACHE, "sess")
LOG = os.path.join(HOME, "log")

DEFAULTS = {
    # The PWA is a relay for YouTube: without a key anybody on the internet could use this server as one.
    # Set "require_key" to false in config.json to open it up on purpose.
    "require_key": True,
    "access_key": "",
    # config/clients.json of the original project overrides client versions without a new build (see README).
    "clients_url": "https://raw.githubusercontent.com/mizuki20070314/podtube-ios12/main/config/clients.json",
    "clients_ttl": 3600,
    # a session of the media relay lives this long (YouTube's stream URLs expire after about 6 hours)
    "session_ttl": 8 * 3600,
    "default_region": "JP",
}

_cfg = None


def ensure_dirs():
    for d in (HOME, CACHE, SESS, LOG):
        try:
            os.makedirs(d, mode=0o700, exist_ok=True)
        except OSError:
            pass


def load():
    """config.json merged over the defaults (read once per request)."""
    global _cfg
    if _cfg is None:
        cfg = dict(DEFAULTS)
        try:
            with open(os.path.join(HOME, "config.json"), "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                cfg.update(data)
        except (OSError, ValueError):
            pass
        _cfg = cfg
    return _cfg


def get(name):
    return load().get(name)


def key_ok(candidate):
    """True when no key is required or `candidate` is the key (constant-time comparison)."""
    cfg = load()
    if not cfg.get("require_key"):
        return True
    key = str(cfg.get("access_key") or "")
    if not key:
        return False                         # required but never set: closed, not open
    return hmac.compare_digest(str(candidate or "").encode("utf-8"), key.encode("utf-8"))


def log(line):
    """Appends one line to log/podtube.log (best effort; the file is trimmed when it grows past 256 KB)."""
    try:
        path = os.path.join(LOG, "podtube.log")
        try:
            if os.path.getsize(path) > 256 * 1024:
                with open(path, "rb") as f:
                    f.seek(-64 * 1024, os.SEEK_END)
                    tail = f.read()
                with open(path, "wb") as f:
                    f.write(tail)
        except OSError:
            pass
        with open(path, "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), line))
    except Exception:
        pass
