"""Typed endpoints on top of InnerTube.post (Core/API.swift, Core/FreshFeed.swift, Core/SearchFilter.swift)."""
import base64
import json
import time
import urllib.parse

from . import parsers
from .innertube import InnerTube, InnerTubeError, profile
from .util import HttpError, request, parse_json

VIDEOS_TAB = "EgZ2aWRlb3PyBgQKAjoA"


# ---------------------------------------------------------------------------------------------------------------------
# search filter -> protobuf `params`
# ---------------------------------------------------------------------------------------------------------------------

def _varint(value):
    out = bytearray()
    v = value
    while v >= 0x80:
        out.append((v & 0x7F) | 0x80)
        v >>= 7
    out.append(v)
    return bytes(out)


def _varint_field(field, value):
    return _varint(field << 3) + _varint(value)


def search_params(sort=0, date=0, kind=0, duration=0, live=False, hd=False, subtitles=False, four_k=False):
    """sort 0 relevance/1 rating/2 upload date/3 views; date 0 any/1 hour/2 today/3 week/4 month/5 year;
    kind 0 any/1 video/2 channel/3 playlist/4 movie; duration 0 any/1 short/2 long/3 medium. None when all default."""
    out = b""
    if sort:
        out += _varint_field(1, sort)
    f = b""
    if date:
        f += _varint_field(1, date)
    if kind:
        f += _varint_field(2, kind)
    if duration:
        f += _varint_field(3, duration)
    if hd:
        f += _varint_field(4, 1)
    if subtitles:
        f += _varint_field(5, 1)
    if live:
        f += _varint_field(8, 1)
    if four_k:
        f += _varint_field(14, 1)
    if f:
        out += _varint((2 << 3) | 2) + _varint(len(f)) + f
    if not out:
        return None
    return base64.b64encode(out).decode("ascii").replace("=", "%3D")


# ---------------------------------------------------------------------------------------------------------------------
# feeds
# ---------------------------------------------------------------------------------------------------------------------

def home(it):
    return parsers.feed(it.post("browse", {"browseId": "FEwhat_to_watch"}))


def search(it, query, params=None):
    body = {"query": query}
    if params:
        body["params"] = params
    return parsers.feed(it.post("search", body))


def continuation(it, token, endpoint):
    """Next page of any list. `endpoint` is the endpoint that produced the token ("browse", "search", "next")."""
    if endpoint not in ("browse", "search", "next"):
        endpoint = "browse"
    return parsers.feed(it.post(endpoint, {"continuation": token}))


def suggestions(hl, query):
    url = "https://suggestqueries.google.com/complete/search?" + urllib.parse.urlencode(
        {"client": "firefox", "ds": "yt", "hl": hl, "q": query})
    try:
        _, _, body = request(url, timeout=8)
        arr = json.loads(body.decode("utf-8"))
        if isinstance(arr, list) and len(arr) > 1 and isinstance(arr[1], list):
            return [s for s in arr[1] if isinstance(s, str)]
    except (HttpError, OSError, ValueError):
        pass
    return []


# ---------------------------------------------------------------------------------------------------------------------
# watch page / channel / playlist
# ---------------------------------------------------------------------------------------------------------------------

def watch(it, video_id, playlist_id=None):
    body = {"videoId": video_id}
    if playlist_id:
        body["playlistId"] = playlist_id
    return parsers.watch(it.post("next", body), video_id)


def video_owner(it, video_id):
    """Who owns a video (channel id, name, icon): one ~90 KB request per channel, remembered by the client."""
    return parsers.video_owner(it.post("next", {"videoId": video_id}))


def comments(it, token):
    return parsers.comments(it.post("next", {"continuation": token}))


def channel(it, cid):
    return parsers.channel_info(it.post("browse", {"browseId": cid}), cid)


def channel_tab(it, cid, params):
    js = it.post("browse", {"browseId": cid, "params": params})
    page = parsers.feed(js["contents"])
    if not page["items"]:
        about = parsers.about_text(js)
        if about:
            page["items"] = [{"type": "text", "text": about}]
    return page


def resolve_channel(it, url):
    """Resolves vanity URLs (@handle, /user/...) to a channel id."""
    js = it.post("navigation/resolve_url", {"url": url})
    cid = js["endpoint"]["browseEndpoint"]["browseId"].str
    if not cid:
        raise InnerTubeError("empty", "No results")
    return cid


def channel_basics(it, cid):
    """Name / avatar / subscriber text of a channel, fetched cheaply through its Videos tab."""
    return parsers.channel_info(it.post("browse", {"browseId": cid, "params": VIDEOS_TAB}), cid)


def playlist(it, pid):
    return parsers.playlist_info(it.post("browse", {"browseId": "VL" + pid}), pid)


# ---------------------------------------------------------------------------------------------------------------------
# playback
# ---------------------------------------------------------------------------------------------------------------------

def player_body(video_id):
    return {"videoId": video_id, "contentCheckOk": True, "racyCheckOk": True,
            "playbackContext": {"contentPlaybackContext": {"html5Preference": "HTML5_PREF_WANTS"}}}


def playback(it, video_id):
    """Resolves streams for a video. HLS is preferred, so when the first client has no HLS manifest the iOS client is asked
    too. A bot check is retried (up to twice) with a fresh visitor id after a short pause. The result carries the id of
    the client that answered (`client`): its user agent has to be used for the stream URLs as well."""
    chain = ["visionos", "ios", "android_vr"]
    attempt = 0
    while True:
        first_error = None
        fallback = None
        for index, cid in enumerate(chain):
            try:
                js = it.post("player", player_body(video_id), profile(cid))
                info = parsers.playback(js, video_id)
            except InnerTubeError as e:
                if first_error is None:
                    first_error = e
                continue
            info["client"] = cid
            if info["hlsURL"]:
                return info
            if fallback is None:
                fallback = info
            if index + 1 < len(chain) - 1:
                continue
            return fallback
        if fallback is not None:
            return fallback
        if attempt < 2 and first_error is not None and first_error.kind == "botcheck":
            it.refresh_visitor()
            time.sleep(1.2)
            attempt += 1
            continue
        raise first_error or InnerTubeError("unplayable", "No playable stream")


# ---------------------------------------------------------------------------------------------------------------------
# shorts
# ---------------------------------------------------------------------------------------------------------------------

def reel_sequence_params(seed):
    raw = seed.encode("utf-8")
    data = bytes([0x0A, len(raw)]) + raw + bytes([0x2A, 0x02, 0x18, 0x00, 0x30, 0x01, 0x78, 0x01])
    return base64.b64encode(data).decode("ascii")


def reel_sequence(it, seed):
    """Video ids that follow `seed` in the Shorts feed."""
    return parsers.reel_sequence(it.post("reel/reel_watch_sequence", {"sequenceParams": reel_sequence_params(seed)}))


def reel_item(it, video_id):
    body = {"disablePlayerResponse": True, "playerRequest": {"videoId": video_id, "params": "8AEB"}, "params": "CA8%3D"}
    return parsers.reel_item(it.post("reel/reel_item_watch", body), video_id)


# ---------------------------------------------------------------------------------------------------------------------
# home feed that does not repeat itself (Core/FreshFeed.swift)
# ---------------------------------------------------------------------------------------------------------------------

def demote(items, seen):
    """Stable partition: videos whose id is in `seen` go to the end, everything else keeps its place.
    Returns (items, number of videos that are not in `seen`)."""
    front, back, fresh = [], [], 0
    for it in items:
        if it["type"] == "video":
            if it["video"]["id"] in seen:
                back.append(it)
            else:
                front.append(it)
                fresh += 1
        else:
            front.append(it)
    return front + back, fresh


def fresh_home(it, seen, token=None, new_visitor=False, min_fresh=12, max_extra_pages=3, account_home=None,
               account_continuation=None):
    """The Home "All" feed: the account's recommendations when signed in (falling back to the anonymous feed when they
    cannot be read), otherwise the anonymous feed. Videos in `seen` are moved behind the new ones; when fewer than
    `min_fresh` videos are new, up to `max_extra_pages` further pages are read first. `new_visitor` asks for a fresh
    anonymous visitor id (a refresh the user asked for)."""
    signed_in = bool(token)
    if new_visitor and not signed_in:
        it.refresh_visitor()
    first = None
    endpoint = "browse"
    if signed_in and account_home:
        try:
            page = account_home(token)
            if page["items"]:
                first, endpoint = page, "tv"
        except InnerTubeError as e:
            if e.kind == "auth":
                raise
    if first is None:
        first, endpoint = home(it), "browse"

    items = list(first["items"])
    have = set(x["video"]["id"] for x in items if x["type"] == "video")
    tok = first["continuation"]
    remaining = max_extra_pages
    while demote(items, seen)[1] < min_fresh and remaining > 0 and tok:
        try:
            if endpoint == "tv":
                more = account_continuation(token, tok)
            else:
                more = continuation(it, tok, "browse")
        except InnerTubeError:
            break
        for x in more["items"]:
            if x["type"] == "video":
                if x["video"]["id"] in have:
                    continue
                have.add(x["video"]["id"])
            items.append(x)
        tok = more["continuation"]
        remaining -= 1
    return {"items": demote(items, seen)[0], "sections": first["sections"], "continuation": tok, "endpoint": endpoint}
