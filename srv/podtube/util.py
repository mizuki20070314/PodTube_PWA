"""Small helpers: a lenient JSON wrapper (InnerTube responses are deeply nested and change shape often),
outbound HTTP, and the pieces of formatting the parsers need."""
import gzip
import io
import json
import re
import ssl
import urllib.error
import urllib.request
import zlib


class J(object):
    """Lenient JSON node: a missing key yields an empty node instead of an error (same idea as the app's `JSON`)."""
    __slots__ = ("raw",)

    def __init__(self, raw=None):
        self.raw = raw

    def __getitem__(self, key):
        r = self.raw
        if isinstance(key, int):
            if isinstance(r, list) and 0 <= key < len(r):
                return J(r[key])
            return J(None)
        if isinstance(r, dict):
            return J(r.get(key))
        return J(None)

    @property
    def exists(self):
        return self.raw is not None

    @property
    def dict(self):
        return self.raw if isinstance(self.raw, dict) else None

    @property
    def is_array(self):
        return isinstance(self.raw, list)

    @property
    def array(self):
        return [J(x) for x in self.raw] if isinstance(self.raw, list) else []

    @property
    def keys(self):
        return sorted(self.raw.keys()) if isinstance(self.raw, dict) else []

    @property
    def string(self):
        return self.raw if isinstance(self.raw, str) else None

    @property
    def str(self):
        return self.raw if isinstance(self.raw, str) else ""

    @property
    def int(self):
        r = self.raw
        if isinstance(r, bool):
            return None
        if isinstance(r, int):
            return r
        if isinstance(r, float):
            if r != r or abs(r) >= 9.0e18 or r in (float("inf"), float("-inf")):
                return None
            return int(r)
        if isinstance(r, str):
            try:
                return int(r)
            except ValueError:
                return None
        return None

    @property
    def float(self):
        r = self.raw
        if isinstance(r, bool):
            return None
        if isinstance(r, (int, float)):
            return float(r)
        if isinstance(r, str):
            try:
                return float(r)
            except ValueError:
                return None
        return None

    @property
    def bool(self):
        r = self.raw
        if isinstance(r, bool):
            return r
        if isinstance(r, str):
            return True if r == "true" else (False if r == "false" else None)
        return None

    @property
    def text(self):
        """YouTube text objects: {"simpleText": "..."} or {"runs": [{"text": "..."}, ...]}."""
        r = self.raw
        if isinstance(r, str):
            return r
        if not isinstance(r, dict):
            return None
        s = r.get("simpleText")
        if isinstance(s, str):
            return s
        runs = r.get("runs")
        if isinstance(runs, list) and runs:
            return "".join(x.get("text", "") if isinstance(x, dict) and isinstance(x.get("text"), str) else "" for x in runs)
        c = r.get("content")
        if isinstance(c, str):
            return c
        return None

    @property
    def text_value(self):
        t = self.text
        return t if t is not None else ""

    def find_all(self, key, limit=100000):
        """Depth-first search for every value stored under `key` (keys visited in sorted order, arrays in order)."""
        out = []

        def walk(o):
            if len(out) >= limit:
                return
            if isinstance(o, dict):
                if key in o:
                    out.append(J(o[key]))
                for k in sorted(o.keys()):
                    walk(o[k])
            elif isinstance(o, list):
                for v in o:
                    walk(v)
        walk(self.raw)
        return out

    def find_first(self, key):
        result = []

        def walk(o):
            if isinstance(o, dict):
                if key in o:
                    result.append(J(o[key]))
                    return True
                for k in sorted(o.keys()):
                    if walk(o[k]):
                        return True
            elif isinstance(o, list):
                for v in o:
                    if walk(v):
                        return True
            return False
        walk(self.raw)
        return result[0] if result else None


class HttpError(Exception):
    def __init__(self, status, body=b""):
        Exception.__init__(self, "HTTP %s" % status)
        self.status = status
        self.body = body


_ctx = None


def ssl_context():
    global _ctx
    if _ctx is None:
        _ctx = ssl.create_default_context()
    return _ctx


def _decode(data, enc):
    enc = (enc or "").lower()
    if enc == "gzip" or data[:2] == b"\x1f\x8b":
        try:
            return gzip.GzipFile(fileobj=io.BytesIO(data)).read()
        except Exception:
            return data
    if enc == "deflate":
        try:
            return zlib.decompress(data)
        except zlib.error:
            try:
                return zlib.decompress(data, -15)
            except zlib.error:
                return data
    return data


def request(url, data=None, headers=None, method=None, timeout=30):
    """One request; returns (status, headers dict with lower-case names, body bytes). HTTP errors raise HttpError."""
    h = {"Accept-Encoding": "gzip"}
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        r = urllib.request.urlopen(req, timeout=timeout, context=ssl_context())
        body = r.read()
        hd = dict((k.lower(), v) for k, v in r.headers.items())
        return r.status, hd, _decode(body, hd.get("content-encoding"))
    except urllib.error.HTTPError as e:
        try:
            body = _decode(e.read(), e.headers.get("Content-Encoding"))
        except Exception:
            body = b""
        raise HttpError(e.code, body)


def open_stream(url, headers=None, timeout=30):
    """An open response for streaming (no decoding: the media is sent as it is). Raises HttpError on HTTP errors."""
    h = {"Accept-Encoding": "identity"}
    h.update(headers or {})
    req = urllib.request.Request(url, headers=h)
    try:
        return urllib.request.urlopen(req, timeout=timeout, context=ssl_context())
    except urllib.error.HTTPError as e:
        try:
            body = e.read()[:300]
        except Exception:
            body = b""
        raise HttpError(e.code, body)


def parse_json(data):
    """JSON bytes -> J (an empty J when the data is not JSON)."""
    try:
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        return J(json.loads(data))
    except (ValueError, UnicodeDecodeError):
        return J(None)


def parse_duration(s):
    """'1:02:03' / '3:51' -> seconds, None when it is not a duration."""
    if not s:
        return None
    parts = s.split(":")
    total = 0
    for p in parts:
        p = p.strip()
        if not p.isdigit():
            return None
        total = total * 60 + int(p)
    return total


def format_duration(seconds):
    try:
        seconds = float(seconds)
    except (TypeError, ValueError):
        return "0:00"
    if seconds != seconds or seconds < 0 or seconds == float("inf"):
        return "0:00"
    total = int(seconds)
    h, m, s = total // 3600, (total % 3600) // 60, total % 60
    if h > 0:
        return "%d:%02d:%02d" % (h, m, s)
    return "%d:%02d" % (m, s)


_VIDEO_ID = re.compile(r"^[0-9A-Za-z_-]{11}$")


def is_video_id(s):
    return bool(s) and bool(_VIDEO_ID.match(s))
