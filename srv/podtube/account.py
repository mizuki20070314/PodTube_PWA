"""Google sign-in (the "limited input device" flow YouTube on TV uses) and everything that needs the signed-in account.

Port of Core/Auth.swift, Core/AccountAPI.swift and Core/PlayHistory.swift.  Google only accepts OAuth bearer tokens for
the TVHTML5 InnerTube client, so these calls use it instead of the anonymous VISIONOS client.

The server keeps no tokens: the browser holds them (localStorage) and sends the access token with each call.
"""
import json
import os
import re
import time
import urllib.parse
import uuid

from . import config, parsers
from .innertube import InnerTubeError, TV_USER_AGENT, profile, signature_timestamp
from .util import HttpError, J, parse_json, request

# YouTube's own TV client credentials. They are public (every smart TV carries them) and the same ones used by
# YouTube.js / SmartTube; Google only honours OAuth for the TVHTML5 InnerTube client.
CLIENT_ID = "861556708454-d6dlm3lh05idd8npek18k6be8ba3oc68.apps.googleusercontent.com"
CLIENT_SECRET = "SboVhoG9s0rNafixCSGGKXAT"
SCOPE = "http://gdata.youtube.com https://www.googleapis.com/auth/youtube-paid-content"
DEVICE_URL = "https://www.youtube.com/o/oauth2/device/code"
TOKEN_URL = "https://www.youtube.com/o/oauth2/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"


# ---------------------------------------------------------------------------------------------------------------------
# OAuth
# ---------------------------------------------------------------------------------------------------------------------

def _post_json(url, body):
    """(http status, parsed J) - OAuth answers its errors (authorization_pending, ...) with 4xx and a JSON body."""
    try:
        status, _, data = request(url, data=json.dumps(body).encode("utf-8"),
                                  headers={"Content-Type": "application/json", "User-Agent": TV_USER_AGENT},
                                  method="POST", timeout=30)
        return status, parse_json(data)
    except HttpError as e:
        return e.status, parse_json(e.body)
    except OSError as e:
        raise InnerTubeError("http", str(e) or "network error")


def request_device_code():
    body = {"client_id": CLIENT_ID, "scope": SCOPE, "device_id": uuid.uuid4().hex, "model_name": "ytlr::"}
    status, js = _post_json(DEVICE_URL, body)
    user, dev = js["user_code"].string, js["device_code"].string
    if status != 200 or not user or not dev:
        raise InnerTubeError("api", js["error_description"].string or js["error"].string or "HTTP %d" % status, status)
    return {"userCode": user, "deviceCode": dev,
            "verificationURL": js["verification_url"].string or "https://www.google.com/device",
            "interval": js["interval"].int or 5, "expiresIn": js["expires_in"].int or 1800}


def poll_token(device_code):
    """One poll of the token endpoint: tokens when approved, otherwise {"status": pending|slow_down|denied|expired|error}."""
    body = {"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "code": device_code,
            "grant_type": "http://oauth.net/grant_type/device/1.0"}
    status, js = _post_json(TOKEN_URL, body)
    access, refresh = js["access_token"].string, js["refresh_token"].string
    if access and refresh:
        return {"status": "ok", "accessToken": access, "refreshToken": refresh, "expiresIn": js["expires_in"].int or 3600}
    err = js["error"].str
    mapping = {"authorization_pending": "pending", "slow_down": "slow_down", "access_denied": "denied", "expired_token": "expired"}
    if err in mapping:
        return {"status": mapping[err]}
    return {"status": "error", "message": js["error_description"].string or err or "HTTP %d" % status}


def refresh_access_token(refresh_token):
    body = {"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "refresh_token": refresh_token, "grant_type": "refresh_token"}
    status, js = _post_json(TOKEN_URL, body)
    access = js["access_token"].string
    if access:
        return {"status": "ok", "accessToken": access, "expiresIn": js["expires_in"].int or 3600}
    if js["error"].str == "invalid_grant":
        return {"status": "revoked"}                       # revoked (e.g. from the Google account page): sign out locally
    return {"status": "error", "message": js["error_description"].string or "HTTP %d" % status}


def revoke(token):
    try:
        request(REVOKE_URL + "?" + urllib.parse.urlencode({"token": token}), data=b"", method="POST", timeout=15,
                headers={"User-Agent": TV_USER_AGENT})
    except Exception:
        pass
    return {"ok": True}


# ---------------------------------------------------------------------------------------------------------------------
# authenticated InnerTube calls (TV client + bearer token)
# ---------------------------------------------------------------------------------------------------------------------

def post_authed(it, endpoint, body, token, prof=None):
    """POST as the signed-in account. A 401 becomes InnerTubeError("auth"): the PWA refreshes the token and retries."""
    if not token:
        raise InnerTubeError("auth", "Sign in required", 401)
    try:
        return it.post(endpoint, body, prof or profile("tv"), {"Authorization": "Bearer " + token})
    except InnerTubeError as e:
        if e.kind in ("http", "api") and e.code == 401:
            raise InnerTubeError("auth", "Sign in required", 401)
        raise


def home(it, token):
    return browse(it, token, "FEwhat_to_watch")


def browse(it, token, browse_id):
    """Any TV browse page (history, library, playlists, ...) read as a feed."""
    return parsers.feed(post_authed(it, "browse", {"browseId": browse_id}, token))


def continuation(it, token, tok):
    return parsers.feed(post_authed(it, "browse", {"continuation": tok}, token))


def subscriptions(it, token):
    """The subscriptions page of the account: the video feed plus the channel strip on the left of the TV page."""
    js = post_authed(it, "browse", {"browseId": "FEsubscriptions"}, token)
    return {"feed": parsers.feed(js), "channels": parsers.subscription_tabs(js)}


def channels(it, token):
    """The channels of the account's "Channels" page (only the most recently active ones - the TV API gives no more)."""
    js = post_authed(it, "browse", {"browseId": "FEchannels"}, token)
    return [x["channel"] for x in parsers.feed(js)["items"] if x["type"] == "channel"]


def playlist(it, token, pid):
    """Any playlist, including the private ones ("WL", "LL", the account's own lists)."""
    return parsers.account_playlist_info(post_authed(it, "browse", {"browseId": "VL" + pid}, token), pid)


def channel_subscribed(it, token, cid):
    """Whether the account subscribes to a channel (the TV channel page carries the exact state; the response is large)."""
    s = parsers.account_watch_state(post_authed(it, "browse", {"browseId": cid}, token))
    if s["subscribed"] is None:
        raise InnerTubeError("empty", "No results")
    return s["subscribed"]


def profile_of(it, token):
    p = parsers.account_profile(post_authed(it, "account/accounts_list", {}, token))
    if p is None:
        raise InnerTubeError("empty", "No results")
    return p


def watch_state(it, token, video_id):
    """Like / subscribe state of a video for this account (the anonymous watch page cannot know it)."""
    return parsers.account_watch_state(post_authed(it, "next", {"videoId": video_id}, token))


def set_like(it, token, video_id, status):
    endpoint = {"like": "like/like", "dislike": "like/dislike"}.get(status, "like/removelike")
    post_authed(it, endpoint, {"target": {"videoId": video_id}}, token)
    return {"ok": True}


def set_subscribed(it, token, channel_id, on):
    body = {"channelIds": [channel_id], "params": "EgIIAxgA" if on else "CgIIAxgA"}
    post_authed(it, "subscription/subscribe" if on else "subscription/unsubscribe", body, token)
    return {"ok": True}


def edit_playlist(it, token, playlist_id, video_id, add):
    """Adds / removes one video of a playlist ("WL" = Watch later). Adding an already present video is skipped."""
    if add:
        action = {"action": "ACTION_ADD_VIDEO", "addedVideoId": video_id, "dedupeOption": "DEDUPE_OPTION_SKIP"}
    else:
        action = {"action": "ACTION_REMOVE_VIDEO_BY_VIDEO_ID", "removedVideoId": video_id}
    js = post_authed(it, "browse/edit_playlist", {"playlistId": playlist_id, "actions": [action]}, token)
    status = js["status"].str
    if status and status != "STATUS_SUCCEEDED":
        raise InnerTubeError("parse", status)
    return {"ok": True}


# ---------------------------------------------------------------------------------------------------------------------
# recording what is played in the account's watch history
# ---------------------------------------------------------------------------------------------------------------------
# The `player` request of the generic TV identity is refused; a Samsung (Tizen) TV identity is answered, and its response
# carries statistics URLs bound to the account (they have a `uga` parameter; the anonymous ones of the VISIONOS client do
# not, and pinging those never reached the history).

def _sts_file():
    return os.path.join(config.CACHE, "sts.txt")


def refresh_signature_timestamp():
    """Reads the current signatureTimestamp from the watch page (about 1.3 MB, so only after a refusal, at most every 6 h)."""
    stamp = os.path.join(config.CACHE, "sts.tried")
    try:
        if time.time() - os.path.getmtime(stamp) < 6 * 3600:
            return None
    except OSError:
        pass
    try:
        with open(stamp, "w") as f:
            f.write(str(int(time.time())))
    except OSError:
        pass
    try:
        _, _, body = request("https://www.youtube.com/watch?v=jNQXAC9IVRw",
                             headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"},
                             timeout=30)
    except Exception:
        return None
    m = re.search(rb'"STS":(\d+)', body)
    if not m or len(m.group(1)) != 5:
        return None
    value = int(m.group(1))
    try:
        with open(_sts_file(), "w") as f:
            f.write(str(value))
    except OSError:
        pass
    return value


def playback_tracking(it, token, video_id, retry=True):
    body = {"videoId": video_id, "contentCheckOk": True, "racyCheckOk": True,
            "playbackContext": {"contentPlaybackContext": {"html5Preference": "HTML5_PREF_WANTS",
                                                           "signatureTimestamp": signature_timestamp()}}}
    js = post_authed(it, "player", body, token, profile("tv_samsung"))
    tracking = parsers.playback_tracking(js)
    if tracking:
        return tracking
    # refused, typically because the signatureTimestamp is stale: read the current one once and ask again
    if retry and refresh_signature_timestamp() is not None:
        return playback_tracking(it, token, video_id, False)
    raise InnerTubeError("parse", js["playabilityStatus"]["status"].string or "no playback tracking")


def _stats_url(url, cpn, extra):
    """The query is edited as text: the values of `ei` / `vm` contain characters (`+`, `/`, `=`) that must stay as they were."""
    parts = urllib.parse.urlsplit(url)
    replaced = set(["ver", "cpn", "cmt", "el", "st", "et"])
    keep = []
    for part in parts.query.split("&"):
        if not part:
            continue
        if part.split("=", 1)[0] in replaced:
            continue
        keep.append(part)
    keep += ["ver=2", "cpn=" + cpn, "el=leanback"] + extra
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, "&".join(keep), ""))


def _allowed_stats_host(url):
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    return urllib.parse.urlsplit(url).scheme == "https" and (host == "youtube.com" or host.endswith(".youtube.com"))


def _seconds(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "0.000"
    if v != v or v in (float("inf"), float("-inf")):
        return "0.000"
    return "%.3f" % max(0.0, v)


def _ping(url, token):
    try:
        request(url, headers={"User-Agent": TV_USER_AGENT, "Authorization": "Bearer " + token}, timeout=15)
        return True
    except Exception:
        return False


def track_start(it, token, video_id, cpn, position):
    """Tells YouTube that the video is being played (`position` in seconds): this puts it into the watch history."""
    t = playback_tracking(it, token, video_id)
    ok = _ping(_stats_url(t["playbackURL"], cpn, ["cmt=" + _seconds(position)]), token)
    return {"ok": ok, "watchtimeURL": t.get("watchtimeURL")}


def track_end(token, watchtime_url, cpn, frm, to):
    """Reports the part of the video that was watched, `frm` to `to` in seconds."""
    if not watchtime_url or not _allowed_stats_host(watchtime_url):
        return {"ok": False}
    url = _stats_url(watchtime_url, cpn, ["cmt=" + _seconds(to), "st=" + _seconds(frm), "et=" + _seconds(to)])
    return {"ok": _ping(url, token)}
