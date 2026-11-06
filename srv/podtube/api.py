"""CGI entry: routes `api.cgi/<route>` to the typed endpoints, the account calls and the media relay.

Every answer is JSON (errors: {"error": {"code", "message", "status"}}) except the media: playlists, segments.
The access key (config.json) is required for everything except /health, /unlock and the media of a live session.
"""
import gzip
import json
import os
import re
import sys
import time
import traceback
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

from . import VERSION, account, config, hls, parsers, yt
from .innertube import InnerTube, InnerTubeError
from .util import HttpError, format_duration, is_video_id, parse_json, request

REASONS = {200: "OK", 204: "No Content", 206: "Partial Content", 400: "Bad Request", 401: "Unauthorized", 404: "Not Found",
           405: "Method Not Allowed", 410: "Gone", 422: "Unprocessable Entity", 429: "Too Many Requests",
           500: "Internal Server Error", 502: "Bad Gateway", 503: "Service Unavailable"}
ERROR_STATUS = {"auth": 401, "locked": 401, "botcheck": 429, "unplayable": 422, "empty": 404, "http": 502, "api": 502,
                "parse": 502, "bad": 400, "notfound": 404}


class Req(object):
    def __init__(self, env, stdin):
        self.env = env
        self.method = env.get("REQUEST_METHOD", "GET").upper()
        self.path = env.get("PATH_INFO", "") or ""
        self.script = env.get("SCRIPT_NAME", "") or ""
        q = urllib.parse.parse_qs(env.get("QUERY_STRING", ""), keep_blank_values=True)
        self.query = dict((k, v[0]) for k, v in q.items())
        self.accept_gzip = "gzip" in env.get("HTTP_ACCEPT_ENCODING", "").lower()
        n = 0
        try:
            n = int(env.get("CONTENT_LENGTH") or 0)
        except ValueError:
            pass
        self.raw = stdin.read(min(n, 4 * 1024 * 1024)) if n > 0 else b""
        self._json = None

    def header(self, name):
        return self.env.get("HTTP_" + name.upper().replace("-", "_"), "")

    @property
    def body(self):
        if self._json is None:
            js = parse_json(self.raw) if self.raw else None
            self._json = js.raw if js is not None and isinstance(js.raw, dict) else {}
        return self._json

    def cookie(self, name):
        for part in self.env.get("HTTP_COOKIE", "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == name:
                return urllib.parse.unquote(v)
        return ""

    @property
    def key(self):
        return self.header("X-PT-Key") or self.cookie("ptk")

    @property
    def token(self):
        return self.header("X-PT-Token")

    def lang(self):
        hl, gl = self.header("X-PT-Hl"), self.header("X-PT-Gl")
        if not re.match(r"^[a-z]{2,3}(-[A-Za-z]{2,4})?$", hl or ""):
            hl = "ja"
        if not re.match(r"^[A-Z]{2}$", gl or ""):
            gl = config.get("default_region") or "JP"
        return hl, gl

    def innertube(self):
        hl, gl = self.lang()
        v = self.header("X-PT-Visitor")
        return InnerTube(hl, gl, v if re.match(r"^[A-Za-z0-9_%=-]{10,1500}$", v or "") else None)


class Err(Exception):
    def __init__(self, code, message="", status=None):
        Exception.__init__(self, message or code)
        self.code = code
        self.message = message or code
        self.status = status or ERROR_STATUS.get(code, 500)


# ---------------------------------------------------------------------------------------------------------------------
# output
# ---------------------------------------------------------------------------------------------------------------------

def _write_head(out, status, headers):
    lines = ["Status: %d %s" % (status, REASONS.get(status, "OK"))]
    for k, v in headers:
        lines.append("%s: %s" % (k, v))
    out.write(("\r\n".join(lines) + "\r\n\r\n").encode("utf-8"))


def respond(out, req, status, ctype, body, extra=None, cache="no-store"):
    if isinstance(body, str):
        body = body.encode("utf-8")
    headers = [("Content-Type", ctype), ("Cache-Control", cache), ("X-Content-Type-Options", "nosniff")]
    headers += extra or []
    if req.accept_gzip and len(body) >= 1024:
        body = gzip.compress(body, 5)
        headers += [("Content-Encoding", "gzip"), ("Vary", "Accept-Encoding")]
    headers.append(("Content-Length", str(len(body))))
    _write_head(out, status, headers)
    if req.method != "HEAD":
        out.write(body)


def respond_json(out, req, obj, status=200, extra=None, it=None):
    if it is not None and it.visitor_changed and isinstance(obj, dict):
        obj["_visitor"] = it.visitor
    respond(out, req, status, "application/json; charset=utf-8", json.dumps(obj, ensure_ascii=False, separators=(",", ":")), extra)


def respond_error(out, req, code, message="", status=None):
    status = status or ERROR_STATUS.get(code, 500)
    respond_json(out, req, {"error": {"code": code, "message": message or code, "status": status}}, status)


# ---------------------------------------------------------------------------------------------------------------------
# route helpers
# ---------------------------------------------------------------------------------------------------------------------

def need(q, name):
    v = q.get(name, "")
    if not v:
        raise Err("bad", "missing " + name)
    return v


def need_video(q, name="v"):
    v = need(q, name)
    if not is_video_id(v):
        raise Err("bad", "bad video id")
    return v


def need_channel(v):
    if not re.match(r"^[A-Za-z0-9_-]{2,64}$", v or ""):
        raise Err("bad", "bad id")
    return v


def need_token(req):
    if not req.token:
        raise InnerTubeError("auth", "Sign in required", 401)
    return req.token


def items_page(page):
    return page


def int_param(req, name, default=0):
    try:
        return int(req.query.get(name, default))
    except ValueError:
        return default


# ---------------------------------------------------------------------------------------------------------------------
# JSON routes: each returns a dict (or raises Err / InnerTubeError)
# ---------------------------------------------------------------------------------------------------------------------

def r_init(req, it):
    it.ensure_visitor()
    return {"version": VERSION, "visitor": it.visitor, "hl": it.hl, "gl": it.gl, "time": int(time.time())}


def r_home(req, it):
    b = req.body
    seen = set(x for x in (b.get("seen") or []) if isinstance(x, str))
    token = req.token or None
    return yt.fresh_home(it, seen, token=token, new_visitor=bool(b.get("fresh")),
                         account_home=lambda t: account.home(it, t),
                         account_continuation=lambda t, c: account.continuation(it, t, c))


def r_search(req, it):
    q = need(req.query, "q")
    params = yt.search_params(
        sort=int_param(req, "sort"), date=int_param(req, "date"), kind=int_param(req, "kind"),
        duration=int_param(req, "dur"), live=req.query.get("live") == "1", hd=req.query.get("hd") == "1",
        subtitles=req.query.get("cc") == "1", four_k=req.query.get("4k") == "1")
    return yt.search(it, q, params)


def r_continuation(req, it):
    b = req.body
    token, endpoint = b.get("token"), b.get("endpoint") or "browse"
    if not isinstance(token, str) or not token:
        raise Err("bad", "missing token")
    if endpoint == "tv":
        return account.continuation(it, need_token(req), token)
    return yt.continuation(it, token, endpoint)


def r_suggest(req, it):
    return {"suggestions": yt.suggestions(it.hl, need(req.query, "q"))}


def r_watch(req, it):
    lst = req.query.get("list") or None
    if lst is not None and not re.match(r"^[A-Za-z0-9_-]{2,64}$", lst):
        lst = None
    return yt.watch(it, need_video(req.query), lst)


def r_owner(req, it):
    return {"channel": yt.video_owner(it, need_video(req.query))}


def r_comments(req, it):
    token = req.body.get("token")
    if not isinstance(token, str) or not token:
        raise Err("bad", "missing token")
    return yt.comments(it, token)


def r_channel(req, it):
    return yt.channel(it, need_channel(need(req.query, "id")))


def r_channeltab(req, it):
    return yt.channel_tab(it, need_channel(need(req.query, "id")), need(req.query, "params"))


def r_channelbasics(req, it):
    return yt.channel_basics(it, need_channel(need(req.query, "id")))


def r_resolve(req, it):
    url = need(req.query, "url")
    if not re.match(r"^https://www\.youtube\.com/[^\s]*$", url):
        raise Err("bad", "bad url")
    return {"id": yt.resolve_channel(it, url)}


def r_playlist(req, it):
    pid = need(req.query, "id")
    if not re.match(r"^[A-Za-z0-9_-]{2,64}$", pid):
        raise Err("bad", "bad id")
    return yt.playlist(it, pid)


def r_reel_seq(req, it):
    return {"ids": yt.reel_sequence(it, need_video(req.query, "seed"))}


def r_reel_item(req, it):
    return yt.reel_item(it, need_video(req.query))


def r_subsfeed(req, it):
    """The latest videos of up to 40 channels (the PWA asks in chunks), newest first, each with its age in seconds."""
    chans = req.body.get("channels") or []
    chans = [c for c in chans if isinstance(c, dict) and re.match(r"^UC[A-Za-z0-9_-]{22}$", str(c.get("id", "")))][:40]
    it.ensure_visitor()
    deadline = time.time() + 40

    def one(idx_ch):
        idx, ch = idx_ch
        if time.time() > deadline:
            return []
        try:
            page = yt.channel_tab(it, ch["id"], yt.VIDEOS_TAB)
        except InnerTubeError:
            return []
        out, n = [], 0
        for v in parsers.page_videos(page):
            if v["isShort"]:
                continue
            if n >= 12:
                break
            v["channelId"] = ch["id"]
            v["channelName"] = str(ch.get("name") or "")
            v["channelAvatar"] = str(ch.get("avatar") or "")
            v["_age"] = parsers.approximate_age(v["published"])
            v["_order"] = idx * 100 + n
            out.append(v)
            n += 1
        return out

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(one, list(enumerate(chans))))
    videos = [v for r in results for v in r]
    videos.sort(key=lambda v: (v["_age"], v["_order"]))
    return {"videos": videos}


def r_play(req, it):
    """Resolves a video and opens a media-relay session for it."""
    vid = need_video(req.query)
    info = yt.playback(it, vid)
    sid = hls.new_session(info)
    heights = sorted(set(f["height"] for f in info["videoFormats"] if 0 < f["height"] <= 1080), reverse=True)
    best_audio = max([f["contentLength"] for f in info["audioFormats"]] or [0])
    return {
        "videoId": vid, "title": info["title"], "author": info["author"], "channelId": info["channelId"],
        "thumbnail": info["thumbnail"], "duration": info["duration"], "isLive": info["isLive"], "sid": sid,
        "hls": bool(info["hlsURL"]), "progressive": bool(info["progressiveURL"]),
        "captions": [{"i": i, "languageCode": c["languageCode"], "name": c["name"], "isAuto": c["isAuto"]}
                     for i, c in enumerate(info["captions"])],
        "audioTracks": info["audioTracks"], "maxHeight": info["maxHeight"], "heights": heights,
        "storyboardSpec": info["storyboardSpec"], "client": info.get("client", ""),
        "sizes": [{"height": h, "bytes": max([f["contentLength"] for f in info["videoFormats"] if f["height"] == h] or [0]) + best_audio}
                  for h in heights],
    }


def parse_json3(data):
    """Caption cues [[start, end, text], ...] from a timedtext json3 document."""
    root = parse_json(data)
    cues = []
    for e in root["events"].array:
        segs = e["segs"].array
        if not segs:
            continue
        text = "".join(s["utf8"].str for s in segs).replace("\n", " ").strip(" \t")
        if not text:
            continue
        start = (e["tStartMs"].float or 0.0) / 1000.0
        dur = (e["dDurationMs"].float if e["dDurationMs"].float is not None else 2000.0) / 1000.0
        cues.append([start, start + dur, text])
    cues.sort(key=lambda c: c[0])
    # Rolling (auto-generated) captions: trim an end that overlaps the next cue's start.
    for i in range(len(cues) - 1):
        if cues[i][1] > cues[i + 1][0]:
            cues[i][1] = cues[i + 1][0]
    return cues


def r_captions(req, it):
    sess = hls.load(req.query.get("sid", ""))
    if sess is None:
        raise Err("notfound", "session expired", 410)
    try:
        track = sess["captions"][int(req.query.get("i", "0"))]
    except (ValueError, IndexError):
        raise Err("bad", "no such track")
    url = track["url"]
    if "fmt=" not in url:
        url += "&fmt=json3"
    tlang = req.query.get("tlang", "")
    if tlang and re.match(r"^[A-Za-z-]{2,12}$", tlang):
        url += "&tlang=" + tlang
    try:
        _, _, data = request(url, headers={"User-Agent": sess["ua"]}, timeout=20)
    except (HttpError, OSError):
        raise Err("http", "captions unavailable", 502)
    return {"cues": parse_json3(data)}


def r_diag(req, it):
    """Runs the whole chain once and reports what worked (the PWA's connection diagnostics)."""
    lines = []

    def step(label, fn):
        t = time.time()
        try:
            detail = fn()
            lines.append({"label": label, "ok": True, "ms": int((time.time() - t) * 1000), "detail": detail or ""})
            return True
        except Exception as e:  # noqa
            lines.append({"label": label, "ok": False, "ms": int((time.time() - t) * 1000), "detail": getattr(e, "message", None) or str(e)})
            return False

    it.refresh_visitor()
    step("visitor id", lambda: (it.visitor or "")[:12] if it.visitor else (_ for _ in ()).throw(InnerTubeError("http", "no visitor id")))
    step("home feed", lambda: "%d videos" % len(parsers.page_videos(yt.home(it))))
    holder = {}

    def player():
        info = yt.playback(it, "dQw4w9WgXcQ")
        holder["info"] = info
        return "hls=%s adaptive=%d+%d client=%s" % (bool(info["hlsURL"]), len(info["videoFormats"]), len(info["audioFormats"]), info.get("client"))

    if step("player", player):
        info = holder["info"]
        if info["hlsURL"]:
            def manifest():
                sess = {"ua": hls.profile(info.get("client", "visionos"))["ua"]}
                text = hls._upstream(sess, info["hlsURL"])
                n = text.count("#EXT-X-STREAM-INF")
                if n == 0:
                    raise InnerTubeError("parse", "no variants in the manifest")
                return "%d variants" % n
            step("HLS manifest (relay)", manifest)
            sid = hls.new_session(info)

            def segment():
                sess = hls.load(sid)
                up = hls.upstream_master(sess, sid)
                k = min(range(len(up["variants"])), key=lambda i: int(hls.attr(up["variants"][i][0], "BANDWIDTH") or 0))
                text = hls.upstream_media(sess, sid, "v%d" % k)
                url = [l for l in text.splitlines() if l and not l.startswith("#")][0]
                s, h, body = request(url, headers={"User-Agent": sess["ua"], "Range": "bytes=0-65535"}, timeout=20)
                return "%d bytes" % len(body)
            step("HLS segment (relay)", segment)
    if req.token:
        step("account history tracking", lambda: "uga=%s" % ("uga=" in account.playback_tracking(it, req.token, "dQw4w9WgXcQ")["playbackURL"]))
    return {"lines": lines, "visitor": it.visitor, "hl": it.hl, "gl": it.gl, "version": VERSION}


# ---------------------------------------------------------------------------------------------------------------------
# account routes
# ---------------------------------------------------------------------------------------------------------------------

def a_device(req, it):
    return account.request_device_code()


def a_poll(req, it):
    code = req.body.get("deviceCode")
    if not isinstance(code, str) or not code:
        raise Err("bad", "missing deviceCode")
    return account.poll_token(code)


def a_refresh(req, it):
    t = req.body.get("refreshToken")
    if not isinstance(t, str) or not t:
        raise Err("bad", "missing refreshToken")
    return account.refresh_access_token(t)


def a_revoke(req, it):
    t = req.body.get("token")
    if isinstance(t, str) and t:
        return account.revoke(t)
    return {"ok": True}


def c_browse(req, it):
    bid = req.body.get("browseId")
    if not isinstance(bid, str) or not re.match(r"^[A-Za-z0-9_-]{2,64}$", bid):
        raise Err("bad", "bad browseId")
    return account.browse(it, need_token(req), bid)


def c_subscriptions(req, it):
    return account.subscriptions(it, need_token(req))


def c_channels(req, it):
    return {"channels": account.channels(it, need_token(req))}


def c_playlist(req, it):
    return account.playlist(it, need_token(req), need(req.query, "id"))


def c_subscribed(req, it):
    return {"subscribed": account.channel_subscribed(it, need_token(req), need_channel(need(req.query, "id")))}


def c_profile(req, it):
    return account.profile_of(it, need_token(req))


def c_watchstate(req, it):
    return account.watch_state(it, need_token(req), need_video(req.query))


def c_like(req, it):
    b = req.body
    vid = b.get("v")
    if not isinstance(vid, str) or not is_video_id(vid):
        raise Err("bad", "bad video id")
    return account.set_like(it, need_token(req), vid, b.get("status") or "none")


def c_subscribe(req, it):
    b = req.body
    return account.set_subscribed(it, need_token(req), need_channel(b.get("id")), bool(b.get("on")))


def c_editplaylist(req, it):
    b = req.body
    pid, vid = b.get("id"), b.get("v")
    if not isinstance(pid, str) or not re.match(r"^[A-Za-z0-9_-]{2,64}$", pid) or not isinstance(vid, str) or not is_video_id(vid):
        raise Err("bad", "bad id")
    return account.edit_playlist(it, need_token(req), pid, vid, bool(b.get("add")))


def c_track_start(req, it):
    b = req.body
    vid, cpn = b.get("v"), b.get("cpn")
    if not isinstance(vid, str) or not is_video_id(vid) or not isinstance(cpn, str) or not re.match(r"^[A-Za-z0-9_-]{16}$", cpn):
        raise Err("bad", "bad request")
    return account.track_start(it, need_token(req), vid, cpn, b.get("position") or 0)


def c_track_end(req, it):
    b = req.body
    cpn = b.get("cpn")
    if not isinstance(cpn, str) or not re.match(r"^[A-Za-z0-9_-]{16}$", cpn):
        raise Err("bad", "bad request")
    return account.track_end(need_token(req), b.get("wt"), cpn, b.get("from") or 0, b.get("to") or 0)


GET_ROUTES = {
    "init": r_init, "suggest": r_suggest, "watch": r_watch, "owner": r_owner, "channel": r_channel,
    "channeltab": r_channeltab, "channelbasics": r_channelbasics, "resolve": r_resolve, "playlist": r_playlist,
    "play": r_play, "captions": r_captions, "search": r_search, "reel/seq": r_reel_seq, "reel/item": r_reel_item,
    "diag": r_diag,
    "acct/playlist": c_playlist, "acct/subscribed": c_subscribed, "acct/profile": c_profile,
    "acct/watchstate": c_watchstate, "acct/subscriptions": c_subscriptions, "acct/channels": c_channels,
}
POST_ROUTES = {
    "home": r_home, "continuation": r_continuation, "comments": r_comments, "subsfeed": r_subsfeed,
    "auth/device": a_device, "auth/poll": a_poll, "auth/refresh": a_refresh, "auth/revoke": a_revoke,
    "acct/browse": c_browse, "acct/like": c_like, "acct/subscribe": c_subscribe, "acct/editplaylist": c_editplaylist,
    "acct/track/start": c_track_start, "acct/track/end": c_track_end,
}


# ---------------------------------------------------------------------------------------------------------------------
# media
# ---------------------------------------------------------------------------------------------------------------------

_HLS_PATH = re.compile(r"^/hls/([A-Za-z0-9_-]{16,48})/(.*)$")


def serve_hls(req, out):
    m = _HLS_PATH.match(req.path)
    sid, rest = m.group(1), m.group(2)
    sess = hls.load(sid)
    if sess is None:
        respond_error(out, req, "notfound", "session expired", 410)
        return
    base = "%s/hls/%s" % (req.script, sid)
    ua = sess["ua"]
    try:
        if rest == "master.m3u8":
            text = hls.build_master(sess, sid, base, maxh=int_param(req, "maxh"), audio_pref=req.query.get("audio", ""),
                                    hl=req.lang()[0])
            respond(out, req, 200, "application/vnd.apple.mpegurl", text)
            return
        mm = re.match(r"^([va])/(\d+)\.m3u8$", rest)
        if mm:
            stream = mm.group(1) + mm.group(2)
            text = hls.upstream_media(sess, sid, stream)
            respond(out, req, 200, "application/vnd.apple.mpegurl", hls.rewrite_media(text, base, stream))
            return
        mm = re.match(r"^s/([va]\d+)/(\d+|map)(?:\.(?:ts|aac|m4s|mp4))?$", rest)
        if mm:
            url = hls.segment_url(sess, sid, mm.group(1), mm.group(2))
            # the audio renditions of YouTube's HLS are packed audio (AAC with ID3 timestamps), whatever the URL says
            ctype = "audio/aac" if mm.group(1).startswith("a") and mm.group(2) != "map" else "video/mp2t"
            hls.stream_to(out, url, ua, req.env.get("HTTP_RANGE"), ctype=ctype, head_only=req.method == "HEAD")
            return
        if rest == "prog":
            if not sess.get("prog"):
                respond_error(out, req, "notfound", "no progressive stream", 404)
                return
            hls.stream_to(out, sess["prog"], ua, req.env.get("HTTP_RANGE"), ctype="video/mp4",
                          head_only=req.method == "HEAD")
            return
    except HttpError as e:
        respond_error(out, req, "notfound" if e.status == 404 else "http", "upstream HTTP %d" % e.status,
                      404 if e.status == 404 else (410 if e.status in (403, 410) else 502))
        return
    except OSError as e:
        respond_error(out, req, "http", "upstream unreachable", 502)
        return
    respond_error(out, req, "notfound", "no such media", 404)


# ---------------------------------------------------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------------------------------------------------

def cookie_path(req):
    return os.path.dirname(req.script.rstrip("/")) + "/" if req.script else "/"


def handle(env, stdin, stdout):
    config.ensure_dirs()
    req = Req(env, stdin)
    out = stdout
    route = req.path.lstrip("/")
    try:
        if req.method == "OPTIONS":
            _write_head(out, 204, [("Allow", "GET, POST, HEAD, OPTIONS"), ("Content-Length", "0")])
            return
        if route == "health":
            respond_json(out, req, {"ok": True, "version": VERSION, "time": int(time.time())})
            return
        if route.startswith("hls/"):                       # media of a session: the session id is the credential
            if req.method not in ("GET", "HEAD"):
                respond_error(out, req, "bad", "method not allowed", 405)
                return
            serve_hls(req, out)
            return
        if route == "unlock":
            key = req.body.get("key") or ""
            if config.key_ok(key):
                extra = [("Set-Cookie", "ptk=%s; Path=%s; Max-Age=31536000; Secure; HttpOnly; SameSite=Lax"
                          % (urllib.parse.quote(str(key), safe=""), cookie_path(req)))] if key else []
                respond_json(out, req, {"ok": True}, extra=extra)
            else:
                time.sleep(1.0)
                respond_error(out, req, "locked", "wrong key", 401)
            return
        if not config.key_ok(req.key):
            if req.key:
                time.sleep(1.0)
            respond_error(out, req, "locked", "access key required", 401)
            return
        table = POST_ROUTES if req.method == "POST" else GET_ROUTES if req.method in ("GET", "HEAD") else None
        fn = table.get(route) if table else None
        if fn is None:
            other = POST_ROUTES if table is GET_ROUTES else GET_ROUTES
            respond_error(out, req, "notfound" if route not in other else "bad",
                          "no such route" if route not in other else "method not allowed",
                          404 if route not in other else 405)
            return
        it = req.innertube()
        result = fn(req, it)
        respond_json(out, req, result, it=it)
    except Err as e:
        respond_error(out, req, e.code, e.message, e.status)
    except InnerTubeError as e:
        status = ERROR_STATUS.get(e.kind, 502)
        respond_error(out, req, e.kind, e.message, status)
    except Exception:
        config.log("500 %s %s\n%s" % (req.method, route, traceback.format_exc()[-1500:]))
        respond_error(out, req, "internal", "internal error", 500)


def main():
    out = sys.stdout.buffer
    try:
        handle(os.environ, sys.stdin.buffer, out)
    finally:
        try:
            out.flush()
        except Exception:
            pass
