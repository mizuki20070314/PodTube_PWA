"""The identity the app presents to YouTube's InnerTube API, and the transport.

Port of Core/InnerTube.swift + Core/ClientConfig.swift.  VISIONOS is used for everything that does not need the
signed-in account: as of late 2026 it is the only client that returns a complete logged-out home feed, classic
(mobile app) renderers, and HLS / adaptive stream URLs without a PO token or the JS player.
"""
import copy
import json
import os
import time

from . import config
from .util import HttpError, J, parse_json, request

TV_USER_AGENT = ("Mozilla/5.0 (ChromiumStylePlatform) Cobalt/25.lts.30.1034943-gold (unlike Gecko), "
                 "Unknown_TV_Unknown_0/Unknown (Unknown, Unknown)")

# (id used by config/clients.json, name, version, numeric id, user agent, extra context fields)
_BASE = {
    "tv": dict(name="TVHTML5", version="7.20260707.07.00", num=7, ua=TV_USER_AGENT, extra={}),
    "tv_samsung": dict(
        name="TVHTML5", version="5.20260707", num=7,
        ua="Mozilla/5.0 (SMART-TV; Linux; Tizen 2.4.0) AppleWebKit/538.1 (KHTML, like Gecko) Version/2.4.0 TV Safari/538.1",
        extra={"deviceMake": "Samsung", "deviceModel": "UKS9800", "osName": "Tizen", "osVersion": "2.4.0"}),
    "visionos": dict(
        name="VISIONOS", version="1.02", num=101,
        ua="Mozilla/5.0 (Macintosh; Intel Mac OS X 15_7_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0 Safari/605.1.15",
        extra={"deviceMake": "Apple", "deviceModel": "RealityDevice17,1", "osName": "visionOS", "osVersion": "26.5.23O471"}),
    "android_vr": dict(
        name="ANDROID_VR", version="1.65.10", num=28,
        ua="com.google.android.apps.youtube.vr.oculus/1.65.10 (Linux; U; Android 12L; eureka-user Build/SQ3A.220605.009.A1) gzip",
        extra={"deviceMake": "Oculus", "deviceModel": "Quest 3", "androidSdkVersion": 32, "osName": "Android", "osVersion": "12L"}),
    "ios": dict(
        name="IOS", version="21.26.4", num=5,
        ua="com.google.ios.youtube/21.26.4 (iPhone16,2; U; CPU iOS 18_3_2 like Mac OS X;)",
        extra={"deviceMake": "Apple", "deviceModel": "iPhone16,2", "osName": "iPhone", "osVersion": "18.3.2.22D82"}),
}

_overrides = None


def client_overrides():
    """config/clients.json of the project repository: version / user agent of each client without a new build.
    Fetched at most once an hour and kept in the cache directory; the built-in values always work as a fallback."""
    global _overrides
    if _overrides is not None:
        return _overrides
    path = os.path.join(config.CACHE, "clients.json")
    ttl = config.get("clients_ttl") or 3600
    data = None
    try:
        age = time.time() - os.path.getmtime(path)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if age < ttl:
            _overrides = _clean_overrides(data)
            return _overrides
    except (OSError, ValueError):
        pass
    url = config.get("clients_url")
    if url:
        try:
            status, _, body = request(url, headers={"User-Agent": "podtube-pwa"}, timeout=6)
            fresh = json.loads(body.decode("utf-8"))
            if isinstance(fresh, dict):
                data = fresh
                try:
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(fresh, f)
                except OSError:
                    pass
        except Exception:
            try:
                os.utime(path, None) if os.path.exists(path) else None   # do not ask again for a while
            except OSError:
                pass
    _overrides = _clean_overrides(data)
    return _overrides


def _clean_overrides(data):
    out = {}
    if isinstance(data, dict):
        for client, entry in data.items():
            if not isinstance(entry, dict):
                continue
            clean = {}
            for field in ("clientVersion", "userAgent", "osVersion", "signatureTimestamp"):
                v = entry.get(field)
                if isinstance(v, str) and v:
                    clean[field] = v
            if clean:
                out[client] = clean
    return out


def profile(cid):
    """The profile `cid` ("visionos", "ios", "android_vr", "tv", "tv_samsung") with config/clients.json applied."""
    base = copy.deepcopy(_BASE[cid])
    o = client_overrides().get(cid) or {}
    if o.get("osVersion"):
        base["extra"]["osVersion"] = o["osVersion"]
    if o.get("clientVersion"):
        base["version"] = o["clientVersion"]
    if o.get("userAgent"):
        base["ua"] = o["userAgent"]
    base["id"] = cid
    return base


def signature_timestamp():
    """The signatureTimestamp a signed-in `player` request has to carry (the values of the last few months work)."""
    built_in = 20760
    configured = 0
    try:
        configured = int((client_overrides().get("tv_samsung") or {}).get("signatureTimestamp") or 0)
    except ValueError:
        pass
    stored = 0
    try:
        with open(os.path.join(config.CACHE, "sts.txt"), "r") as f:
            stored = int(f.read().strip())
    except (OSError, ValueError):
        pass
    return max(built_in, configured, stored)


class InnerTubeError(Exception):
    """kind: parse | unplayable | botcheck | http | api | auth | empty"""

    def __init__(self, kind, message="", code=0):
        Exception.__init__(self, message or kind)
        self.kind = kind
        self.message = message or kind
        self.code = code


class InnerTube(object):
    """One request's view of the API: language / region and the visitor id of the calling browser."""

    def __init__(self, hl="ja", gl="JP", visitor=None):
        self.hl = hl or "ja"
        self.gl = gl or "JP"
        self.visitor = visitor or None
        self.visitor_changed = False

    # -- visitor data -----------------------------------------------------------------------------------------------
    # Requests that carry no `visitorData` are frequently answered with LOGIN_REQUIRED ("confirm you're not a bot").
    # A visitor id is cheap to get, so every request has one.

    def ensure_visitor(self):
        if self.visitor:
            return self.visitor
        return self.fetch_visitor()

    def refresh_visitor(self):
        self.visitor = None
        return self.fetch_visitor()

    def fetch_visitor(self):
        try:
            js = self._send("visitor_id", {}, profile("visionos"), use_visitor=False)
            vd = js["responseContext"]["visitorData"].string
        except Exception:
            vd = None
        if vd:
            self.visitor = vd
            self.visitor_changed = True
        return self.visitor

    # -- requests ---------------------------------------------------------------------------------------------------

    def _send(self, endpoint, body, prof, use_visitor=True, extra_headers=None):
        url = "https://www.youtube.com/youtubei/v1/%s?prettyPrint=false" % endpoint
        client = {"clientName": prof["name"], "clientVersion": prof["version"], "userAgent": prof["ua"],
                  "hl": self.hl, "gl": self.gl}
        client.update(prof["extra"])
        visitor = self.visitor if use_visitor else None
        if visitor:
            client["visitorData"] = visitor
        payload = {"context": {"client": client}}
        payload.update(body)
        headers = {
            "Content-Type": "application/json",
            "User-Agent": prof["ua"],
            "X-YouTube-Client-Name": str(prof["num"]),
            "X-YouTube-Client-Version": prof["version"],
            "Origin": "https://www.youtube.com",
            "Accept-Language": self.hl,
        }
        if visitor:
            headers["X-Goog-Visitor-Id"] = visitor
        headers.update(extra_headers or {})
        try:
            status, _, data = request(url, data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
                                      headers=headers, method="POST", timeout=30)
        except HttpError as e:
            msg = parse_json(e.body)["error"]["message"].string
            if msg:
                raise InnerTubeError("api", msg, e.status)
            raise InnerTubeError("http", "HTTP %d" % e.status, e.status)
        except OSError as e:
            raise InnerTubeError("http", str(e) or "network error", 0)
        js = parse_json(data)
        if not js.exists:
            raise InnerTubeError("parse", "invalid JSON")
        msg = js["error"]["message"].string
        if msg:
            raise InnerTubeError("parse", msg)
        return js

    def post(self, endpoint, body=None, prof=None, extra_headers=None):
        """POST to an InnerTube endpoint (VISIONOS by default); returns a J."""
        self.ensure_visitor()
        return self._send(endpoint, body or {}, prof or profile("visionos"), True, extra_headers)
