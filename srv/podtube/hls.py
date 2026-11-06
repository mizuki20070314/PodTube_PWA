"""The media relay.

YouTube hands out stream URLs that only work from the IP address that asked for them, and the media servers send no
CORS headers.  So the browser cannot fetch them itself: this module relays the HLS manifests and segments.

A *session* is created when a video is resolved (`play`).  Its random id is the only credential the media requests carry
(a browser's <video> element cannot send headers), it names a few files in the cache directory and expires with the
stream URLs.  Nothing under a session id can reach anything but what the server itself put there: the PWA never names an
upstream URL.

  <sid>.json              the session (video, user agent of the client that resolved it, upstream manifest URL, captions)
  <sid>.master            upstream master playlist (fetched lazily, kept for a few minutes)
  <sid>.<stream>.m3u8     the last upstream media playlist of a stream  (v<k> = k-th video variant, a<j> = j-th audio rendition)

Served (PATH_INFO under api.cgi):
  /hls/<sid>/master.m3u8?maxh=720&audio=original   master playlist, H.264+AAC only, capped and with one audio track
  /hls/<sid>/v/<k>.m3u8   /hls/<sid>/a/<j>.m3u8     media playlists, segment URIs rewritten
  /hls/<sid>/s/<stream>/<seq>.ts|.aac                 one segment (streamed)
  /hls/<sid>/prog                                     progressive MP4 (fallback when there is no HLS)
"""
import json
import os
import re
import secrets
import time

from . import config
from .innertube import profile
from .util import HttpError, open_stream, request

SID_RE = re.compile(r"^[A-Za-z0-9_-]{16,48}$")
MASTER_TTL = 600


# ---------------------------------------------------------------------------------------------------------------------
# sessions
# ---------------------------------------------------------------------------------------------------------------------

def _path(sid, suffix):
    return os.path.join(config.SESS, sid + suffix)


def _write(path, data):
    tmp = path + ".%d.tmp" % os.getpid()
    with open(tmp, "wb") as f:
        f.write(data if isinstance(data, bytes) else data.encode("utf-8"))
    os.replace(tmp, path)


def new_session(info):
    """`info` is the server-side result of yt.playback (with the stream URLs). Returns the session id."""
    purge()
    sid = secrets.token_urlsafe(16)
    data = {
        "v": info["videoId"],
        "created": int(time.time()),
        "client": info.get("client", "visionos"),
        "ua": profile(info.get("client", "visionos"))["ua"],
        "hls": info.get("hlsURL"),
        "prog": info.get("progressiveURL"),
        "captions": [{"url": c["url"], "languageCode": c["languageCode"], "name": c["name"], "isAuto": c["isAuto"]}
                     for c in info.get("captions", [])],
        "audioTracks": info.get("audioTracks", []),
        "duration": info.get("duration", 0),
        "live": bool(info.get("isLive")),
    }
    _write(_path(sid, ".json"), json.dumps(data))
    return sid


def load(sid):
    """The session, or None when it does not exist (any more)."""
    if not sid or not SID_RE.match(sid):
        return None
    try:
        with open(_path(sid, ".json"), "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if time.time() - data.get("created", 0) > (config.get("session_ttl") or 8 * 3600):
        return None
    return data


def purge():
    """Deletes expired sessions (at most once a minute)."""
    stamp = os.path.join(config.SESS, ".purged")
    now = time.time()
    try:
        if now - os.path.getmtime(stamp) < 60:
            return
    except OSError:
        pass
    try:
        with open(stamp, "w") as f:
            f.write(str(int(now)))
    except OSError:
        return
    ttl = (config.get("session_ttl") or 8 * 3600) + 1800
    try:
        for name in os.listdir(config.SESS):
            p = os.path.join(config.SESS, name)
            try:
                if name != ".purged" and now - os.path.getmtime(p) > ttl:
                    os.remove(p)
            except OSError:
                pass
    except OSError:
        pass


# ---------------------------------------------------------------------------------------------------------------------
# m3u8 helpers
# ---------------------------------------------------------------------------------------------------------------------

_ATTR = re.compile(r'([A-Z0-9-]+)=("[^"]*"|[^,]*)')


def parse_attrs(s):
    return [(m.group(1), m.group(2)) for m in _ATTR.finditer(s)]


def attr(attrs, name):
    for k, v in attrs:
        if k == name:
            return v[1:-1] if v.startswith('"') and v.endswith('"') else v
    return None


def build_attrs(attrs):
    return ",".join("%s=%s" % (k, v) for k, v in attrs)


def _upstream(sess, url):
    status, headers, body = request(url, headers={"User-Agent": sess["ua"]}, timeout=30)
    return body.decode("utf-8", "replace")


def upstream_master(sess, sid):
    """Parsed upstream master: {"audio": [(attrs, uri)...], "variants": [(attrs, uri)...], "head": [lines]}."""
    path = _path(sid, ".master")
    text = None
    try:
        if time.time() - os.path.getmtime(path) < MASTER_TTL:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
    except OSError:
        pass
    if text is None:
        if not sess.get("hls"):
            raise HttpError(404)
        text = _upstream(sess, sess["hls"])
        try:
            _write(path, text)
        except OSError:
            pass
    audio, variants, head = [], [], []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        l = lines[i].strip()
        if l.startswith("#EXT-X-MEDIA:"):
            a = parse_attrs(l[len("#EXT-X-MEDIA:"):])
            if attr(a, "TYPE") == "AUDIO":
                audio.append((a, attr(a, "URI")))
        elif l.startswith("#EXT-X-STREAM-INF:"):
            a = parse_attrs(l[len("#EXT-X-STREAM-INF:"):])
            uri = lines[i + 1].strip() if i + 1 < len(lines) else ""
            variants.append((a, uri))
            i += 1
        elif l.startswith("#EXT") and l not in ("#EXTM3U",) and not l.startswith("#EXT-X-MEDIA") and not l.startswith("#EXT-X-STREAM-INF"):
            head.append(l)
        i += 1
    return {"audio": audio, "variants": variants, "head": head}


def variant_height(attrs):
    res = attr(attrs, "RESOLUTION") or ""
    m = re.match(r"(\d+)x(\d+)", res)
    return min(int(m.group(1)), int(m.group(2))) if m else 0         # a portrait 720x1280 is "720p" too


def _primary(tag):
    return (tag or "").lower().split("-")[0].split(".")[0]


def choose_audio(tracks, pref, hl):
    """Which audio track plays: `pref` is "" (automatic: the viewer's language, else the original), "original" or a
    language tag ("ja", "en-us"). Returns the track id, or None when the video has a single track. The PWA applies the
    same rules to show the check mark (web/js/player.js, chooseAudio)."""
    if len(tracks) < 2:
        return None
    original = None
    for t in tracks:
        if t.get("isDefault"):
            original = t
            break
    if original is None:
        original = tracks[0]
    pref = (pref or "").lower()
    if pref == "original":
        return original["id"]
    if pref:
        exact = [t for t in tracks if t["id"].split(".")[0].lower() == pref]
        if exact:
            return exact[0]["id"]
        same = [t for t in tracks if _primary(t["id"]) == _primary(pref)]
        if len(same) == 1:
            return same[0]["id"]
    mine = [t for t in tracks if _primary(t["id"]) == _primary(hl)]
    if mine:
        for t in mine:
            if t.get("isDefault"):
                return t["id"]
        return mine[0]["id"]
    return original["id"]


def build_master(sess, sid, base, maxh=0, audio_pref="", hl="ja"):
    """The master playlist for the browser: H.264 + AAC only (Safari 12 cannot decode VP9), the variants no taller than
    `maxh`, one audio rendition per group, no subtitle renditions (the PWA draws captions itself), URIs pointing at us."""
    up = upstream_master(sess, sid)
    variants = list(enumerate(up["variants"]))
    avc = [(k, v) for k, v in variants if "avc1" in (attr(v[0], "CODECS") or "")]
    if avc:
        variants = avc
    if maxh and maxh > 0:
        capped = [(k, v) for k, v in variants if 0 < variant_height(v[0]) <= maxh]
        if not capped and variants:
            lowest = min(variants, key=lambda kv: variant_height(kv[1][0]) or 99999)
            capped = [lowest]
        variants = capped
    variants.sort(key=lambda kv: int(attr(kv[1][0], "BANDWIDTH") or 0))

    # audio: the renditions of every group that is still used; the chosen track only
    used_groups = []
    for k, (a, uri) in variants:
        g = attr(a, "AUDIO")
        if g and g not in used_groups:
            used_groups.append(g)
    track_id = choose_audio(sess.get("audioTracks") or [], audio_pref, hl)
    chosen = {}
    for j, (a, uri) in enumerate(up["audio"]):
        g = attr(a, "GROUP-ID")
        if g not in used_groups:
            continue
        content_id = attr(a, "YT-EXT-AUDIO-CONTENT-ID")
        score = 0
        if track_id and content_id == track_id:
            score = 3
        elif not track_id and (attr(a, "DEFAULT") or "").upper() == "YES":
            score = 2
        elif g not in chosen:
            score = 1
        if g not in chosen or score > chosen[g][0]:
            chosen[g] = (score, j, a)

    out = ["#EXTM3U", "#EXT-X-INDEPENDENT-SEGMENTS"]
    for g in used_groups:
        if g not in chosen:
            continue
        _, j, a = chosen[g]
        attrs = [("TYPE", "AUDIO"), ("GROUP-ID", '"%s"' % g), ("NAME", '"%s"' % (attr(a, "NAME") or "Default").replace('"', "'"))]
        lang = attr(a, "LANGUAGE")
        if lang:
            attrs.append(("LANGUAGE", '"%s"' % lang))
        attrs += [("DEFAULT", "YES"), ("AUTOSELECT", "YES"), ("URI", '"%s/a/%d.m3u8"' % (base, j))]
        out.append("#EXT-X-MEDIA:" + build_attrs(attrs))
    for k, (a, uri) in variants:
        keep = [(n, v) for n, v in a if n in ("BANDWIDTH", "AVERAGE-BANDWIDTH", "CODECS", "RESOLUTION", "FRAME-RATE", "AUDIO")]
        if attr(a, "AUDIO") not in chosen and any(n == "AUDIO" for n, _ in keep):
            keep = [(n, v) for n, v in keep if n != "AUDIO"]
        out.append("#EXT-X-STREAM-INF:" + build_attrs(keep))
        out.append("%s/v/%d.m3u8" % (base, k))
    return "\n".join(out) + "\n"


def upstream_media(sess, sid, stream):
    """Fetches (and stores) the upstream media playlist of `stream` ("v3", "a0"); returns its text."""
    up = upstream_master(sess, sid)
    kind, idx = stream[0], stream[1:]
    if kind not in ("v", "a") or not idx.isdigit():
        raise HttpError(404)
    idx = int(idx)
    lst = up["variants"] if kind == "v" else up["audio"]
    if idx >= len(lst) or not lst[idx][1]:
        raise HttpError(404)
    text = _upstream(sess, lst[idx][1])
    try:
        _write(_path(sid, ".%s.m3u8" % stream), text)
    except OSError:
        pass
    return text


def rewrite_media(text, base, stream):
    """Segment URIs -> /hls/<sid>/s/<stream>/<seq>.ts (seq = media sequence + position, stable for live playlists)."""
    lines = text.splitlines()
    seq = 0
    for l in lines:
        if l.startswith("#EXT-X-MEDIA-SEQUENCE:"):
            try:
                seq = int(l.split(":", 1)[1].strip())
            except ValueError:
                pass
            break
    out = []
    n = 0
    for l in lines:
        s = l.strip()
        if not s:
            continue
        if s.startswith("#"):
            if s.startswith("#EXT-X-MAP:"):
                a = parse_attrs(s[len("#EXT-X-MAP:"):])
                rest = [(k, v) for k, v in a if k != "URI"]
                rest.append(("URI", '"%s/s/%s/map"' % (base, stream)))
                s = "#EXT-X-MAP:" + build_attrs(rest)
            out.append(s)
        else:
            out.append("%s/s/%s/%d.%s" % (base, stream, seq + n, "aac" if stream.startswith("a") else "ts"))
            n += 1
    return "\n".join(out) + "\n"


def segment_url(sess, sid, stream, seq):
    """The upstream URL of segment `seq` of `stream` (or "map" for the init segment), from the stored playlist."""
    path = _path(sid, ".%s.m3u8" % stream)
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        text = upstream_media(sess, sid, stream)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if seq == "map":
        for l in lines:
            if l.startswith("#EXT-X-MAP:"):
                return attr(parse_attrs(l[len("#EXT-X-MAP:"):]), "URI")
        raise HttpError(404)
    first = 0
    for l in lines:
        if l.startswith("#EXT-X-MEDIA-SEQUENCE:"):
            try:
                first = int(l.split(":", 1)[1].strip())
            except ValueError:
                pass
            break
    idx = int(seq) - first
    uris = [l for l in lines if not l.startswith("#")]
    if idx < 0 or idx >= len(uris):
        # a live playlist that moved on: look again
        text = upstream_media(sess, sid, stream)
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        first = 0
        for l in lines:
            if l.startswith("#EXT-X-MEDIA-SEQUENCE:"):
                try:
                    first = int(l.split(":", 1)[1].strip())
                except ValueError:
                    pass
                break
        uris = [l for l in lines if not l.startswith("#")]
        idx = int(seq) - first
        if idx < 0 or idx >= len(uris):
            raise HttpError(404)
    return uris[idx]


# ---------------------------------------------------------------------------------------------------------------------
# streaming
# ---------------------------------------------------------------------------------------------------------------------

def stream_to(out, url, ua, range_header=None, ctype="video/mp2t", cache="private, max-age=3600", head_only=False):
    """Copies an upstream response to the CGI output as it arrives. Returns the HTTP status that was sent."""
    headers = {"User-Agent": ua}
    if range_header:
        headers["Range"] = range_header
    try:
        r = open_stream(url, headers)
    except HttpError as e:
        status = 410 if e.status in (403, 410) else 502
        body = b'{"error":{"code":"upstream","message":"upstream HTTP %d","status":%d}}' % (e.status, status)
        out.write(b"Status: %d\r\nContent-Type: application/json\r\nCache-Control: no-store\r\nContent-Length: %d\r\n\r\n" % (status, len(body)))
        out.write(body)
        return status
    except OSError:
        body = b'{"error":{"code":"upstream","message":"upstream unreachable","status":502}}'
        out.write(b"Status: 502\r\nContent-Type: application/json\r\nCache-Control: no-store\r\nContent-Length: %d\r\n\r\n" % len(body))
        out.write(body)
        return 502
    status = r.status
    lines = ["Status: %d" % status, "Content-Type: %s" % ctype, "Cache-Control: %s" % cache,
             "Accept-Ranges: bytes"]
    cl = r.headers.get("Content-Length")
    if cl:
        lines.append("Content-Length: %s" % cl)
    cr = r.headers.get("Content-Range")
    if cr:
        lines.append("Content-Range: %s" % cr)
    out.write(("\r\n".join(lines) + "\r\n\r\n").encode("ascii"))
    if head_only:
        r.close()
        return status
    try:
        while True:
            chunk = r.read(65536)
            if not chunk:
                break
            out.write(chunk)
    except (BrokenPipeError, ConnectionError):
        pass
    except OSError:
        pass
    finally:
        try:
            r.close()
        except Exception:
            pass
    return status
