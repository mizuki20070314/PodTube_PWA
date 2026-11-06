"""Calls the real YouTube through the server package and prints what the parsers made of it.
usage: python tests/live_parse.py [section ...]   (sections: home search watch comments channel playlist player reel suggest)
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "srv"))
os.environ.setdefault("PT_HOME", os.path.join(os.path.dirname(HERE), ".dev-home"))

from podtube import config, yt, parsers  # noqa: E402
from podtube.innertube import InnerTube, InnerTubeError  # noqa: E402

config.ensure_dirs()


def show(title, obj, limit=400):
    s = json.dumps(obj, ensure_ascii=False)
    print("%-22s %s%s" % (title, s[:limit], " ..." if len(s) > limit else ""))


def timed(label, fn):
    t = time.time()
    try:
        r = fn()
        print("[ok ] %-14s %.2fs" % (label, time.time() - t))
        return r
    except InnerTubeError as e:
        print("[NG ] %-14s %.2fs %s: %s" % (label, time.time() - t, e.kind, e.message))
    except Exception as e:  # noqa
        import traceback
        traceback.print_exc()
        print("[ERR] %-14s %r" % (label, e))
    return None


def main():
    want = set(sys.argv[1:]) or {"home", "search", "watch", "comments", "channel", "playlist", "player", "reel", "suggest"}
    it = InnerTube("ja", "JP")
    if "suggest" in want:
        r = timed("suggest", lambda: yt.suggestions("ja", "ホロライブ"))
        show("suggestions", r)
    if "home" in want:
        page = timed("home", lambda: yt.home(it))
        if page:
            kinds = {}
            for x in page["items"]:
                kinds[x["type"]] = kinds.get(x["type"], 0) + 1
            print("   items", len(page["items"]), kinds, "sections", [s["title"] for s in page["sections"]], "cont", bool(page["continuation"]))
            for x in page["items"][:3]:
                show("   item", x)
            if page["continuation"]:
                p2 = timed("home page2", lambda: yt.continuation(it, page["continuation"], "browse"))
                if p2:
                    print("   items", len(p2["items"]), "cont", bool(p2["continuation"]))
    if "search" in want:
        page = timed("search", lambda: yt.search(it, "ホロライブ"))
        if page:
            kinds = {}
            for x in page["items"]:
                kinds[x["type"]] = kinds.get(x["type"], 0) + 1
            print("   items", len(page["items"]), kinds, "cont", bool(page["continuation"]))
            show("   first", page["items"][0] if page["items"] else None)
        params = yt.search_params(sort=2, kind=1, duration=3)
        print("   params", params)
        page = timed("search+filter", lambda: yt.search(it, "ホロライブ", params))
        if page:
            print("   items", len(page["items"]))
    if "watch" in want:
        w = timed("watch", lambda: yt.watch(it, "dQw4w9WgXcQ"))
        if w:
            show("   title", [w["title"], w["views"], w["viewsShort"], w["date"], w["likeText"], w["likeCount"]])
            show("   channel", w["channel"])
            print("   related", len(w["related"]["items"]), "autoplay", bool(w["autoplay"]), "commentsToken", bool(w["commentsToken"]),
                  w["commentCount"], [s["title"] for s in w["commentSortTokens"]])
            if w["commentsToken"] and "comments" in want:
                c = timed("comments", lambda: yt.comments(it, w["commentsToken"]))
                if c:
                    print("   comments", len(c["comments"]), "cont", bool(c["continuation"]), c["totalText"])
                    show("   first", c["comments"][0] if c["comments"] else None)
        wl = timed("watch+list", lambda: yt.watch(it, "dQw4w9WgXcQ", "RDdQw4w9WgXcQ"))
        if wl:
            print("   queue", len(wl["queue"]), wl["queueTitle"], wl["queueIndex"])
    if "channel" in want:
        ch = timed("channel", lambda: yt.channel(it, "UCuAXFkgsw1L7xaCfnd5JJOw"))
        if ch:
            show("   info", {k: ch[k] for k in ("id", "name", "handle", "subscribers", "videoCount", "verified")})
            print("   tabs", [t["title"] for t in ch["tabs"]], "banner", bool(ch["banner"]), "items", len(ch["firstPage"]["items"]))
            for t in ch["tabs"][:4]:
                p = timed("tab " + t["title"], lambda t=t: yt.channel_tab(it, ch["id"], t["params"]))
                if p:
                    print("   items", len(p["items"]), {x["type"] for x in p["items"]})
        rc = timed("resolve @", lambda: yt.resolve_channel(it, "https://www.youtube.com/@YouTubeJapan"))
        print("   ->", rc)
        cb = timed("basics", lambda: yt.channel_basics(it, "UCuAXFkgsw1L7xaCfnd5JJOw"))
        if cb:
            show("   basics", {k: cb[k] for k in ("id", "name", "avatar")})
    if "playlist" in want:
        pl = timed("playlist", lambda: yt.playlist(it, "PLFgquLnL59alCl_2TQvOiD5Vgm1hCaGSI"))
        if pl:
            print("   ", pl["title"], pl["owner"], pl["stats"], len(pl["firstPage"]["items"]), bool(pl["firstPage"]["continuation"]))
    if "player" in want:
        for vid in ("dQw4w9WgXcQ", "jNQXAC9IVRw", "jfKfPfyJRdk"):
            info = timed("player " + vid, lambda vid=vid: yt.playback(it, vid))
            if info:
                print("   client", info["client"], "hls", bool(info["hlsURL"]), "prog", bool(info["progressiveURL"]),
                      "vf", len(info["videoFormats"]), "af", len(info["audioFormats"]), "maxH", info["maxHeight"],
                      "live", info["isLive"], "dur", info["duration"], "caps", len(info["captions"]),
                      "tracks", len(info["audioTracks"]), "sb", bool(info["storyboardSpec"]))
    if "reel" in want:
        ids = timed("reel seq", lambda: yt.reel_sequence(it, "dQw4w9WgXcQ"))
        print("   ids", ids[:5] if ids else ids)
        if ids:
            e = timed("reel item", lambda: yt.reel_item(it, ids[0]))
            show("   item", e)
    print("visitor changed:", it.visitor_changed)


if __name__ == "__main__":
    main()
