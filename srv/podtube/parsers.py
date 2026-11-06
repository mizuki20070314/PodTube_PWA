"""Raw InnerTube JSON (visionOS client / classic renderers / TV tiles) -> small dicts for the PWA.

A port of Core/Parsers.swift.  Everything is lenient: unknown or missing fields are skipped rather than failing the page.
Feed items are  {"type": "video", "video": {...}}  /  {"type": "channel", "channel": {...}}  /
{"type": "playlist", "playlist": {...}}  /  {"type": "shorts", "videos": [...]}  /  {"type": "text", "text": "..."}.
"""
import base64
import re
import urllib.parse

from .innertube import InnerTubeError
from .util import J


# ---------------------------------------------------------------------------------------------------------------------
# models
# ---------------------------------------------------------------------------------------------------------------------

def new_video(vid):
    return {"id": vid, "title": "", "channelName": "", "channelId": "", "channelAvatar": "", "thumbnail": "",
            "duration": "", "views": "", "published": "", "isLive": False, "isUpcoming": False, "isShort": False}


def new_channel(cid):
    return {"id": cid, "name": "", "handle": "", "avatar": "", "subscribers": "", "videoCount": ""}


def new_playlist(pid):
    return {"id": pid, "title": "", "channelName": "", "thumbnail": "", "videoCount": ""}


def item_video(v):
    return {"type": "video", "video": v}


# ---------------------------------------------------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------------------------------------------------

def absolute(url):
    if url.startswith("//"):
        return "https:" + url
    return url


def thumb(node, min_width):
    """Smallest thumbnail that is at least `min_width` wide, else the largest one."""
    lst = node["thumbnails"].array
    if not lst:
        lst = node["sources"].array                 # view-model style images
    if not lst:
        return ""
    best = None
    best_width = 1 << 62
    largest = ""
    largest_width = -1
    for t in lst:
        url = t["url"].str
        w = t["width"].int or 0
        if w > largest_width:
            largest_width = w
            largest = url
        if w >= min_width and w < best_width:
            best_width = w
            best = url
    return absolute(best if best is not None else largest)


def first_text(*nodes):
    for n in nodes:
        t = n.text
        if t:
            return t
    return ""


# ---------------------------------------------------------------------------------------------------------------------
# single renderers
# ---------------------------------------------------------------------------------------------------------------------

def video(r):
    """compactVideoRenderer / videoWithContextRenderer / playlistVideoRenderer / reelItemRenderer"""
    nav = r["navigationEndpoint"]
    vid = r["videoId"].str
    if not vid:
        vid = nav["watchEndpoint"]["videoId"].str
    if not vid:
        vid = nav["reelWatchEndpoint"]["videoId"].str
    if not vid:
        return None
    v = new_video(vid)
    if nav["reelWatchEndpoint"].exists:
        v["isShort"] = True
    v["title"] = first_text(r["title"], r["headline"])
    byline = r["longBylineText"]
    if not byline.exists:
        byline = r["shortBylineText"]
    if not byline.exists:
        byline = r["ownerText"]
    v["channelName"] = byline["runs"][0]["text"].string or byline.text_value
    v["channelId"] = byline["runs"][0]["navigationEndpoint"]["browseEndpoint"]["browseId"].str
    v["channelAvatar"] = thumb(r["channelThumbnail"], 48)
    v["thumbnail"] = thumb(r["thumbnail"], 480)
    v["views"] = first_text(r["shortViewCountText"], r["viewCountText"])
    v["published"] = r["publishedTimeText"].text_value
    v["duration"] = r["lengthText"].text_value
    for o in r["thumbnailOverlays"].array:
        ts = o["thumbnailOverlayTimeStatusRenderer"]
        if not ts.exists:
            continue
        style = ts["style"].str
        if style == "LIVE":
            v["isLive"] = True
        if style == "UPCOMING":
            v["isUpcoming"] = True
        if style == "SHORTS":
            v["isShort"] = True
        if not v["duration"] and style in ("DEFAULT", "SHORTS"):
            v["duration"] = ts["text"].text_value
    if v["isLive"] or v["isUpcoming"]:
        v["duration"] = ""
    return v


def lockup(r):
    """`lockupViewModel` (the newer web layout): videos and playlists. Returns a feed item or None."""
    cid = r["contentId"].str
    if not cid:
        return None
    ctype = r["contentType"].str
    meta = r["metadata"]["lockupMetadataViewModel"]
    title = meta["title"]["content"].str
    thumb_node = r["contentImage"]["thumbnailViewModel"]

    if ctype in ("LOCKUP_CONTENT_TYPE_PLAYLIST", "LOCKUP_CONTENT_TYPE_PODCAST"):
        p = new_playlist(cid)
        p["title"] = title
        t = thumb(thumb_node["image"], 320)
        if not t:
            t = thumb(r["contentImage"]["collectionThumbnailViewModel"]["primaryThumbnail"]["thumbnailViewModel"]["image"], 320)
        p["thumbnail"] = t
        rows = meta["metadata"]["contentMetadataViewModel"]["metadataRows"].array
        p["channelName"] = rows[0]["metadataParts"][0]["text"]["content"].str if rows else ""
        return {"type": "playlist", "playlist": p}
    if ctype != "LOCKUP_CONTENT_TYPE_VIDEO" and ctype:
        return None

    v = new_video(cid)
    v["title"] = title
    v["thumbnail"] = thumb(thumb_node["image"], 480)
    for o in thumb_node["overlays"].array:
        for b in o["thumbnailBottomOverlayViewModel"]["badges"].array:
            badge = b["thumbnailBadgeViewModel"]
            text = badge["text"].str
            style = badge["badgeStyle"].str
            if "LIVE" in style:
                v["isLive"] = True
            elif ":" in text and not v["duration"]:
                v["duration"] = text
    avatar_node = meta["image"]["decoratedAvatarViewModel"]
    v["channelAvatar"] = thumb(avatar_node["avatar"]["avatarViewModel"]["image"], 48)
    v["channelId"] = avatar_node["rendererContext"]["commandContext"]["onTap"]["innertubeCommand"]["browseEndpoint"]["browseId"].str
    rows = meta["metadata"]["contentMetadataViewModel"]["metadataRows"].array
    if len(rows) >= 2:
        v["channelName"] = rows[0]["metadataParts"][0]["text"]["content"].str
        v["views"] = rows[1]["metadataParts"][0]["text"]["content"].str
        v["published"] = rows[1]["metadataParts"][1]["text"]["content"].str
    elif rows:
        v["views"] = rows[0]["metadataParts"][0]["text"]["content"].str
        v["published"] = rows[0]["metadataParts"][1]["text"]["content"].str
    return item_video(v)


def short_lockup(r):
    """`shortsLockupViewModel`"""
    vid = r["onTap"]["innertubeCommand"]["reelWatchEndpoint"]["videoId"].str
    if not vid:
        vid = r["entityId"].str.replace("shorts-shelf-item-", "")
    if not vid:
        return None
    v = new_video(vid)
    v["isShort"] = True
    v["title"] = r["overlayMetadata"]["primaryText"]["content"].str
    v["views"] = r["overlayMetadata"]["secondaryText"]["content"].str
    v["thumbnail"] = thumb(r["onTap"]["innertubeCommand"]["reelWatchEndpoint"]["thumbnail"], 300)
    if not v["title"]:
        v["title"] = r["accessibilityText"].str
    return v


def channel(r):
    cid = r["channelId"].str
    if not cid:
        cid = r["navigationEndpoint"]["browseEndpoint"]["browseId"].str
    if not cid:
        return None
    c = new_channel(cid)
    c["name"] = first_text(r["displayName"], r["title"])
    c["avatar"] = thumb(r["thumbnail"], 88)
    # The renderer mislabels these: videoCountText holds the subscriber count, subscriberCountText the @handle.
    a = r["videoCountText"].text_value
    b = r["subscriberCountText"].text_value
    if b.startswith("@"):
        c["handle"] = b
        c["subscribers"] = a
    else:
        c["subscribers"] = b
        c["videoCount"] = a
    return c


def playlist(r):
    pid = r["playlistId"].str
    if not pid:
        b = r["navigationEndpoint"]["browseEndpoint"]["browseId"].str
        pid = b[2:] if b.startswith("VL") else b
    if not pid:
        return None
    p = new_playlist(pid)
    p["title"] = r["title"].text_value
    p["channelName"] = first_text(r["shortBylineText"], r["longBylineText"])
    t = thumb(r["thumbnail"], 320)
    if not t:
        t = thumb(r["thumbnailRenderer"]["playlistVideoThumbnailRenderer"]["thumbnail"], 320)
    if not t:
        t = thumb(r["thumbnailRenderer"]["playlistCustomThumbnailRenderer"]["thumbnail"], 320)
    p["thumbnail"] = t
    p["videoCount"] = first_text(r["videoCountText"], r["videoCountShortText"], r["numVideosText"])
    return p


# ---------------------------------------------------------------------------------------------------------------------
# TV client (tileRenderer): everything that needs the signed-in account
# ---------------------------------------------------------------------------------------------------------------------

def line_rows(lines):
    """Text of the `lineRenderer` rows of a tile / playlist header, separators and badges dropped."""
    rows = []
    for line in lines:
        row = []
        for it in line["lineRenderer"]["items"].array:
            li = it["lineItemRenderer"]
            if li["badge"].exists:
                continue
            t = li["text"].text_value.strip(" \t")
            if not t or t == "•" or t == "·":
                continue
            row.append(t)
        rows.append(row)
    return rows


def tile(r):
    ttype = r["contentType"].str
    cid = r["contentId"].str
    if not cid or not ttype:
        return None
    meta = r["metadata"]["tileMetadataRenderer"]
    header = r["header"]["tileHeaderRenderer"]
    title = meta["title"].text_value
    rows = line_rows(meta["lines"].array)

    if ttype in ("TILE_CONTENT_TYPE_VIDEO", "TILE_CONTENT_TYPE_SHORTS"):
        v = new_video(cid)
        v["title"] = title
        v["isShort"] = ttype == "TILE_CONTENT_TYPE_SHORTS"
        v["thumbnail"] = thumb(header["thumbnail"], 480)
        if rows:
            v["channelName"] = " ".join(rows[0])
        if len(rows) > 1:
            v["views"] = rows[1][0] if rows[1] else ""
            if len(rows[1]) > 1:
                v["published"] = rows[1][1]
        for o in header["thumbnailOverlays"].array:
            ts = o["thumbnailOverlayTimeStatusRenderer"]
            if ts.exists:
                style = ts["style"].str
                if style == "LIVE":
                    v["isLive"] = True
                if style == "UPCOMING":
                    v["isUpcoming"] = True
                if style == "SHORTS":
                    v["isShort"] = True
                if not v["duration"] and style in ("DEFAULT", "SHORTS"):
                    v["duration"] = ts["text"].text_value
            pct = o["thumbnailOverlayResumePlaybackRenderer"]["percentDurationWatched"].int
            if pct is not None:
                v["watchedPercent"] = pct
        if v["isLive"] or v["isUpcoming"]:
            v["duration"] = ""
        return item_video(v)
    if ttype == "TILE_CONTENT_TYPE_PLAYLIST":
        p = new_playlist(cid)
        p["title"] = title
        p["thumbnail"] = thumb(header["thumbnail"], 320)
        if rows:
            p["channelName"] = " · ".join(rows[0])
        for o in header["thumbnailOverlays"].array:
            t = o["thumbnailOverlayTimeStatusRenderer"]["text"].text_value
            if t:
                p["videoCount"] = t
        return {"type": "playlist", "playlist": p}
    if ttype == "TILE_CONTENT_TYPE_CHANNEL":
        if not cid.startswith("UC"):             # library shortcuts ("FEhistory", ...) are typed as channels too
            return None
        c = new_channel(cid)
        c["name"] = title
        c["avatar"] = thumb(header["thumbnail"], 88)
        for row in rows:
            for s in row:
                if s.startswith("@"):
                    c["handle"] = s
                elif not c["subscribers"]:
                    c["subscribers"] = s
        return {"type": "channel", "channel": c}
    return None


_UC = re.compile(r"UC[0-9A-Za-z_-]{22}")


def channel_id_from_params(params):
    """Channel id inside the url-encoded base64 `params` of a subscriptions tab."""
    s = urllib.parse.unquote(params)
    s = s.replace("-", "+").replace("_", "/")
    while len(s) % 4 != 0:
        s += "="
    try:
        data = base64.b64decode(s)
    except Exception:
        return None
    text = data.decode("utf-8", "replace")
    m = _UC.search(text)
    return m.group(0) if m else None


def subscription_tabs(root):
    """The left-hand channel list of the TV subscriptions page (most recently active channels first)."""
    out = []
    seen = set()
    for t in root.find_all("tabRenderer"):
        if not t["thumbnail"].exists:
            continue
        params = t["endpoint"]["browseEndpoint"]["params"].str
        cid = channel_id_from_params(params)
        if not cid or cid in seen:
            continue
        seen.add(cid)
        c = new_channel(cid)
        c["name"] = t["title"].text_value
        c["avatar"] = thumb(t["thumbnail"], 88)
        out.append(c)
    return out


def account_profile(root):
    items = root.find_all("accountItem")
    item = None
    for it in items:
        if it["isSelected"].bool is True:
            item = it
            break
    if item is None and items:
        item = items[0]
    if item is None:
        return None
    name = item["accountName"].text_value
    if not name:
        return None
    return {"name": name, "handle": item["channelHandle"].text_value, "avatar": thumb(item["accountPhoto"], 88)}


def account_playlist_info(root, pid):
    """A playlist page of the TV client: title / owner / counts live in `entityMetadataRenderer`."""
    info = {"id": pid, "title": "", "owner": "", "ownerId": "", "stats": [], "thumbnail": "", "firstPage": None}
    e = root.find_first("entityMetadataRenderer")
    if e is not None:
        info["title"] = e["title"].text_value
        texts = [t for row in line_rows(e["bylines"].array) for t in row]
        if texts:
            info["owner"] = texts[0]
        info["stats"] = texts[1:]
    info["firstPage"] = feed(root)
    vids = page_videos(info["firstPage"])
    info["thumbnail"] = vids[0]["thumbnail"] if vids else ""
    return info


def account_watch_state(root):
    s = {"likeStatus": "", "subscribed": None, "channelId": ""}
    like = root.find_first("likeButtonRenderer")
    if like is not None:
        s["likeStatus"] = like["likeStatus"].str
    sub = root.find_first("subscribeButtonRenderer")
    if sub is not None:
        s["subscribed"] = sub["subscribed"].bool
        s["channelId"] = sub["channelId"].str
    return s


# ---------------------------------------------------------------------------------------------------------------------
# feeds
# ---------------------------------------------------------------------------------------------------------------------

_VIDEO_KEYS = ("compactVideoRenderer", "videoWithContextRenderer", "playlistVideoRenderer", "videoRenderer",
               "gridVideoRenderer", "reelItemRenderer", "playlistPanelVideoRenderer")
_CHANNEL_KEYS = ("compactChannelRenderer", "gridChannelRenderer", "channelRenderer")
_PLAYLIST_KEYS = ("compactPlaylistRenderer", "gridPlaylistRenderer", "playlistRenderer")


class _FeedWalker(object):
    def __init__(self):
        self.items = []
        self.sections = []
        self.tokens = []
        self.seen = set()
        self.current_section = None
        self.shelf_depth = 0     # > 0 while inside a shelf: horizontal "more in this shelf" tokens must not page the list

    def add(self, item):
        self.items.append(item)
        if self.current_section is not None:
            self.sections[self.current_section]["items"].append(item)

    def _add_unique(self, item):
        t = item["type"]
        if t == "video":
            key = item["video"]["id"]
        elif t == "channel":
            key = "c:" + item["channel"]["id"]
        else:
            key = "p:" + item["playlist"]["id"]
        if key not in self.seen:
            self.seen.add(key)
            self.add(item)

    def visit(self, node, depth):
        if depth > 60:
            return
        if isinstance(node, list):
            for x in node:
                self.visit(x, depth + 1)
            return
        if not isinstance(node, dict):
            return
        d = node
        if "adSlotRenderer" in d or "adBreakServiceRenderer" in d:
            return
        if "tileRenderer" in d:
            item = tile(J(d["tileRenderer"]))
            if item is not None:
                self._add_unique(item)
            return
        if "lockupViewModel" in d:
            item = lockup(J(d["lockupViewModel"]))
            if item is not None and item["type"] in ("video", "playlist"):
                self._add_unique(item)
            return
        if "shortsLockupViewModel" in d:
            v = short_lockup(J(d["shortsLockupViewModel"]))
            if v is not None and v["id"] not in self.seen:
                self.seen.add(v["id"])
                self.add(item_video(v))
            return
        for key in _VIDEO_KEYS:
            if key in d:
                v = video(J(d[key]))
                if v is not None and v["id"] not in self.seen:
                    self.seen.add(v["id"])
                    self.add(item_video(v))
                return
        for key in _CHANNEL_KEYS:
            if key in d:
                c = channel(J(d[key]))
                if c is not None and "c:" + c["id"] not in self.seen:
                    self.seen.add("c:" + c["id"])
                    self.add({"type": "channel", "channel": c})
                return
        for key in _PLAYLIST_KEYS:
            if key in d:
                p = playlist(J(d[key]))
                if p is not None and "p:" + p["id"] not in self.seen:
                    self.seen.add("p:" + p["id"])
                    self.add({"type": "playlist", "playlist": p})
                return
        if "shelfRenderer" in d:
            s = J(d["shelfRenderer"])
            title = s["title"].text_value
            if not title:
                title = s["headerRenderer"]["shelfHeaderRenderer"]["avatarLockup"]["avatarLockupRenderer"]["title"].text_value
            self.sections.append({"title": title, "items": []})
            saved = self.current_section
            self.current_section = len(self.sections) - 1
            self.shelf_depth += 1
            self.visit(s["content"].raw, depth + 1)
            self.shelf_depth -= 1
            self.current_section = saved
            if self.sections and not self.sections[-1]["items"]:
                self.sections.pop()
            return
        n = d.get("nextContinuationData")
        if isinstance(n, dict) and isinstance(n.get("continuation"), str):
            if self.shelf_depth == 0:
                self.tokens.append(n["continuation"])
            return
        if "continuationItemRenderer" in d:
            t = J(d["continuationItemRenderer"])["continuationEndpoint"]["continuationCommand"]["token"].str
            if t:
                self.tokens.append(t)
            return
        for k in sorted(d.keys()):
            if k in ("menu", "thumbnailOverlays", "trackingParams"):
                continue
            self.visit(d[k], depth + 1)


def feed(root):
    """Generic list parser: walks the whole response and collects every recognised item in document order."""
    w = _FeedWalker()
    w.visit(root.raw if isinstance(root, J) else root, 0)
    return {"items": group_shorts(w.items), "sections": w.sections, "continuation": w.tokens[-1] if w.tokens else None}


def group_shorts(items):
    out = []
    run = []
    for it in items:
        if it["type"] == "video" and it["video"]["isShort"]:
            run.append(it["video"])
        else:
            if run:
                out.append({"type": "shorts", "videos": run})
                run = []
            out.append(it)
    if run:
        out.append({"type": "shorts", "videos": run})
    return out


def page_videos(page):
    out = []
    for it in page["items"]:
        if it["type"] == "video":
            out.append(it["video"])
        elif it["type"] == "shorts":
            out.extend(it["videos"])
    return out


def about_text(root):
    """Channel "About" tab: description, stats and links as one text block."""
    a = root.find_first("channelAboutMetadataRenderer")
    if a is None:
        return None
    blocks = []
    desc = a["description"].text_value.strip()
    if desc:
        blocks.append(desc)
    stats = []
    for key in ("joinedDateText", "viewCountText", "country"):
        t = a[key].text_value
        if t:
            stats.append(t)
    if stats:
        blocks.append("\n".join(stats))
    links = []
    for l in a["primaryLinks"].array:
        title = l["title"].text_value
        url = l["navigationEndpoint"]["urlEndpoint"]["url"].str
        if url:
            links.append(url if not title else title + "\n" + url)
    if links:
        blocks.append("\n\n".join(links))
    out = "\n\n".join(blocks)
    return out or None


# ---------------------------------------------------------------------------------------------------------------------
# watch page (`next`)
# ---------------------------------------------------------------------------------------------------------------------

def watch(root, video_id):
    info = {"videoId": video_id, "title": "", "views": "", "viewsShort": "", "date": "", "description": "",
            "likeText": "", "likeCount": None, "channel": None, "related": {"items": [], "sections": [], "continuation": None},
            "commentsToken": None, "commentCount": "", "commentSortTokens": [], "autoplay": None,
            "queue": [], "queueTitle": "", "queueIndex": 0}
    m = root.find_first("videoMetadataRenderer")
    if m is not None:
        info["title"] = m["title"].text_value
        info["views"] = m["viewCountText"].text_value
        info["viewsShort"] = m["shortViewCountText"].text_value
        info["date"] = m["dateText"].text_value
        info["description"] = m["description"].text_value
        like = m["likeButton"]["likeButtonRenderer"]
        info["likeText"] = like["likeCountText"].text_value
        info["likeCount"] = like["likeCount"].int
        owner = m["owner"]["videoOwnerRenderer"]
        cid = owner["navigationEndpoint"]["browseEndpoint"]["browseId"].str
        if not cid:
            cid = owner["subscribeButton"]["subscribeButtonRenderer"]["channelId"].str
        if cid:
            ch = new_channel(cid)
            ch["name"] = owner["title"].text_value
            ch["avatar"] = thumb(owner["thumbnail"], 88)
            ch["subscribers"] = owner["subscriberCountText"].text_value
            ch["handle"] = owner["navigationEndpoint"]["browseEndpoint"]["canonicalBaseUrl"].str
            info["channel"] = ch

    # Related videos live in the second tab of the tabbed results.
    tabs_node = root.find_first("watchNextTabbedResultsRenderer")
    tabs = tabs_node["tabs"].array if tabs_node is not None else []
    if len(tabs) >= 2:
        info["related"] = feed(tabs[1])
    elif len(tabs) == 1:
        rel = feed(tabs[0])
        rel["items"] = [it for it in rel["items"] if not (it["type"] == "video" and it["video"]["id"] == video_id)]
        info["related"] = rel

    nxt = root["contents"]["singleColumnWatchNextResults"]["autoplay"]["autoplay"]["sets"][0]["autoplayVideoRenderer"]["compactVideoRenderer"]
    if nxt.exists:
        info["autoplay"] = video(nxt)

    # Comments panel: count + the continuation token that loads the first page.
    for p in root["engagementPanels"].array:
        panel = p["engagementPanelSectionListRenderer"]
        if panel["panelIdentifier"].str != "comment-item-section":
            continue
        header = panel["header"]["engagementPanelTitleHeaderRenderer"]
        info["commentCount"] = header["contextualInfo"].text_value
        info["commentsToken"] = panel["content"]["sectionListRenderer"]["continuations"][0]["reloadContinuationData"]["continuation"].string
        for item in header["menu"]["sortFilterSubMenuRenderer"]["subMenuItems"].array:
            tok = item["continuation"]["reloadContinuationData"]["continuation"].str
            if tok:
                info["commentSortTokens"].append({"title": item["title"].text_value, "token": tok})

    # Playlist queue (only present when the request carried a playlistId).
    pl = root["contents"]["singleColumnWatchNextResults"]["playlist"]["playlist"]
    if pl.exists:
        info["queueTitle"] = pl["title"].text_value
        info["queueIndex"] = pl["currentIndex"].int or 0
        for it in pl["contents"].array:
            v = video(it["playlistPanelVideoRenderer"])
            if v is not None:
                info["queue"].append(v)
    return info


# ---------------------------------------------------------------------------------------------------------------------
# comments
# ---------------------------------------------------------------------------------------------------------------------

def comment(cr):
    cid = cr["commentId"].str
    if not cid:
        return None
    return {
        "id": cid,
        "author": cr["authorText"].text_value,
        "authorId": cr["authorEndpoint"]["browseEndpoint"]["browseId"].str,
        "avatar": thumb(cr["authorThumbnail"], 48),
        "text": cr["contentText"].text_value,
        "published": cr["publishedTimeText"].text_value,
        "likes": cr["voteCount"].text_value,
        "isOwner": cr["authorIsChannelOwner"].bool or False,
        "isPinned": cr["pinnedCommentBadge"].exists,
        "replyCount": cr["replyCount"].int or 0,
    }


def comments(root):
    page = {"comments": [], "continuation": None, "totalText": "", "sortTokens": []}
    for t in root.find_all("commentThreadRenderer"):
        cr = t["comment"]["commentRenderer"]
        c = comment(cr)
        if c is None:
            continue
        c["replyCount"] = max(c["replyCount"], cr["replyCount"].int or 0)
        page["comments"].append(c)
    tokens = []
    for n in root.find_all("nextContinuationData"):
        t = n["continuation"].str
        if t:
            tokens.append(t)
    page["continuation"] = tokens[-1] if tokens else None
    h = root.find_first("commentsHeaderRenderer")
    if h is not None:
        page["totalText"] = h["countText"].text_value
        for item in h["sortMenu"]["sortFilterSubMenuRenderer"]["subMenuItems"].array:
            tok = item["continuation"]["reloadContinuationData"]["continuation"].str
            if tok:
                page["sortTokens"].append({"title": item["title"].text_value, "token": tok})
    return page


# ---------------------------------------------------------------------------------------------------------------------
# channel / playlist pages
# ---------------------------------------------------------------------------------------------------------------------

def channel_info(root, cid):
    info = {"id": cid, "name": "", "handle": "", "avatar": "", "banner": "", "subscribers": "", "videoCount": "",
            "verified": False, "tabs": [], "firstPage": None}
    h = root["header"]["c4TabbedHeaderRenderer"]
    real = h["channelId"].string
    if real:
        info["id"] = real
    info["name"] = h["title"].text_value
    info["avatar"] = thumb(h["avatar"], 88)
    info["banner"] = thumb(h["banner"], 640)
    info["subscribers"] = h["subscriberCountText"].text_value
    info["videoCount"] = h["videosCountText"].text_value
    info["handle"] = h["channelHandleText"].text_value
    info["verified"] = bool(h["badges"].array)
    for t in root["contents"]["singleColumnBrowseResultsRenderer"]["tabs"].array:
        tr = t["tabRenderer"]
        title = tr["title"].text_value
        if not title:
            continue
        params = tr["endpoint"]["browseEndpoint"]["params"].str
        info["tabs"].append({"title": title, "params": params, "selected": tr["selected"].bool or False})
    info["firstPage"] = feed(root["contents"])
    return info


def playlist_info(root, pid):
    info = {"id": pid, "title": "", "owner": "", "ownerId": "", "stats": [], "thumbnail": "", "firstPage": None}
    h = root["header"]["playlistHeaderRenderer"]
    info["title"] = h["title"].text_value
    info["owner"] = h["ownerText"].text_value
    info["ownerId"] = h["ownerEndpoint"]["browseEndpoint"]["browseId"].str
    stats = []
    n = h["numVideosText"].text_value
    if n:
        stats.append(n)
    views = h["viewCountText"].text_value
    if views:
        stats.append(views)
    info["stats"] = stats
    info["firstPage"] = feed(root["contents"])
    vids = page_videos(info["firstPage"])
    info["thumbnail"] = vids[0]["thumbnail"] if vids else ""
    return info


def video_owner(root):
    """The channel that owns a video, from the `next` response (id, name, icon, handle) - nothing else is read."""
    owner = root.find_first("videoOwnerRenderer")
    if owner is None:
        return None
    cid = owner["navigationEndpoint"]["browseEndpoint"]["browseId"].str
    if not cid:
        cid = owner["subscribeButton"]["subscribeButtonRenderer"]["channelId"].str
    if not cid:
        return None
    ch = new_channel(cid)
    ch["name"] = owner["title"].text_value
    ch["avatar"] = thumb(owner["thumbnail"], 88)
    ch["handle"] = owner["navigationEndpoint"]["browseEndpoint"]["canonicalBaseUrl"].str
    return ch


# ---------------------------------------------------------------------------------------------------------------------
# player
# ---------------------------------------------------------------------------------------------------------------------

def playback(root, video_id):
    """Raises InnerTubeError("botcheck" | "unplayable"). The URLs in the result are for the server only."""
    info = {"videoId": video_id, "title": "", "author": "", "channelId": "", "thumbnail": "", "duration": 0.0,
            "isLive": False, "hlsURL": None, "progressiveURL": None, "videoURL": None, "audioURL": None,
            "captions": [], "videoFormats": [], "audioFormats": [], "audioTracks": [], "maxHeight": 0,
            "storyboardSpec": ""}
    vd = root["videoDetails"]
    info["title"] = vd["title"].str
    info["author"] = vd["author"].str
    info["channelId"] = vd["channelId"].str
    try:
        info["duration"] = float(vd["lengthSeconds"].str)
    except ValueError:
        info["duration"] = 0.0
    info["isLive"] = bool(vd["isLive"].bool) or (bool(vd["isLiveContent"].bool) and info["duration"] == 0)
    info["thumbnail"] = thumb(vd["thumbnail"], 480)

    ps = root["playabilityStatus"]
    status = ps["status"].str
    sd = root["streamingData"]
    if status != "OK" and not sd.exists:
        reason = ps["reason"].text_value
        if not reason:
            reason = ps["errorScreen"]["playerErrorMessageRenderer"]["reason"].text_value
        if not reason:
            reason = status if status else "Playback error"
        if status == "LOGIN_REQUIRED":
            raise InnerTubeError("botcheck", reason)
        raise InnerTubeError("unplayable", reason)

    hls = sd["hlsManifestUrl"].string
    if hls:
        info["hlsURL"] = hls

    # Muxed progressive (rarely present for this client, kept as a fallback).
    best_muxed = 0
    for f in sd["formats"].array:
        mime = f["mimeType"].str
        u = f["url"].string
        if "video/mp4" not in mime or "avc1" not in mime or not u:
            continue
        h = f["height"].int or 0
        if h >= best_muxed:
            best_muxed = h
            info["progressiveURL"] = u

    # A video with several audio tracks lists every track in adaptiveFormats. Without a choice the original one is used.
    original_id = ""
    for f in sd["adaptiveFormats"].array:
        t = f["audioTrack"]
        tid = t["id"].str
        if not tid or any(x["id"] == tid for x in info["audioTracks"]):
            continue
        info["audioTracks"].append({"id": tid, "name": t["displayName"].str, "isDefault": t["audioIsDefault"].bool or False})
    original = None
    for x in info["audioTracks"]:
        if x["isDefault"]:
            original = x
            break
    if original is None and info["audioTracks"]:
        original = info["audioTracks"][0]
    if original is not None:
        original_id = original["id"]

    # Adaptive H.264 + AAC (sizes for the download dialog; the streams themselves are played through HLS).
    best_video_h = 0
    best_audio_rate = 0
    other_audio = []
    for f in sd["adaptiveFormats"].array:
        mime = f["mimeType"].str
        u = f["url"].string
        if not u:
            continue
        try:
            length = int(f["contentLength"].str)
        except ValueError:
            length = 0
        if "video/mp4" in mime and "avc1" in mime:
            h = f["height"].int or 0
            info["videoFormats"].append({"height": h, "url": u, "bitrate": f["bitrate"].int or 0, "contentLength": length})
            if h > best_video_h and h <= 1080:
                best_video_h = h
                info["videoURL"] = u
        elif "audio/mp4" in mime and "mp4a" in mime:
            track_id = f["audioTrack"]["id"].str
            br = f["bitrate"].int or 0
            fmt = {"height": 0, "url": u, "bitrate": br, "contentLength": length}
            if track_id and track_id != original_id:
                other_audio.append(fmt)
                continue
            info["audioFormats"].append(fmt)
            if br > best_audio_rate:
                best_audio_rate = br
                info["audioURL"] = u
    if not info["audioFormats"] and other_audio:
        best = max(other_audio, key=lambda x: x["bitrate"])
        info["audioFormats"] = other_audio
        info["audioURL"] = best["url"]
    info["maxHeight"] = max(best_video_h, best_muxed)
    info["storyboardSpec"] = root["storyboards"]["playerStoryboardSpecRenderer"]["spec"].str

    for t in root["captions"]["playerCaptionsTracklistRenderer"]["captionTracks"].array:
        url = t["baseUrl"].str
        if not url:
            continue
        info["captions"].append({"languageCode": t["languageCode"].str, "name": t["name"].text_value, "url": url,
                                 "isAuto": t["kind"].str == "asr"})

    playable = bool(info["hlsURL"] or info["progressiveURL"] or (info["videoURL"] and info["audioURL"]))
    if not playable:
        raise InnerTubeError("unplayable", ps["reason"].string or "No playable stream")
    return info


def playback_tracking(root):
    """Account-bound statistics URLs of a player response made under the signed-in account (or None)."""
    if root["playabilityStatus"]["status"].string != "OK":
        return None
    play = root["playbackTracking"]["videostatsPlaybackUrl"]["baseUrl"].string
    if not play:
        return None
    return {"playbackURL": play, "watchtimeURL": root["playbackTracking"]["videostatsWatchtimeUrl"]["baseUrl"].string}


# ---------------------------------------------------------------------------------------------------------------------
# shorts
# ---------------------------------------------------------------------------------------------------------------------

def reel_sequence(root):
    ids = []
    for e in root["entries"].array:
        vid = e["command"]["reelWatchEndpoint"]["videoId"].str
        if vid and vid not in ids:
            ids.append(vid)
    return ids


def reel_item(root, video_id):
    """Details for one Short from `reel/reel_item_watch`."""
    v = new_video(video_id)
    v["isShort"] = True
    ov = root["overlay"]["reelPlayerOverlayRenderer"]
    header = ov["reelPlayerHeaderSupportedRenderers"]["reelPlayerHeaderRenderer"]
    v["title"] = header["reelTitleText"].text_value
    v["channelName"] = header["channelTitleText"].text_value
    v["channelId"] = header["channelNavigationEndpoint"]["browseEndpoint"]["browseId"].str
    v["channelAvatar"] = thumb(header["channelThumbnail"], 48)
    v["published"] = header["timestampText"].text_value
    return {"video": v, "likes": ov["likeButton"]["likeButtonRenderer"]["likeCountText"].text_value,
            "comments": ov["viewCommentsButton"]["buttonRenderer"]["text"].text_value}


# ---------------------------------------------------------------------------------------------------------------------
# misc
# ---------------------------------------------------------------------------------------------------------------------

_AGE_UNITS = [("秒", 1), ("second", 1), ("分", 60), ("minute", 60), ("時間", 3600), ("hour", 3600),
              ("日", 86400), ("day", 86400), ("週", 7 * 86400), ("week", 7 * 86400),
              ("か月", 30 * 86400), ("ヶ月", 30 * 86400), ("ヵ月", 30 * 86400), ("month", 30 * 86400),
              ("年", 365 * 86400), ("year", 365 * 86400)]


def approximate_age(text):
    """Rough "age in seconds" of YouTube relative strings ("3 日前", "2 weeks ago", ...) so merged feeds can be ordered."""
    lower = (text or "").lower()
    digits = ""
    for ch in lower:
        if ch.isdecimal():
            digits += ch
        elif digits:
            break
    if not digits:
        return 86400 * 3650
    n = float(int(digits))
    for key, mult in _AGE_UNITS:
        if key in lower:
            return n * mult
    return 86400 * 3650
