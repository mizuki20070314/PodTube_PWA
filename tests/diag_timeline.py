"""Scratch (runs on the server): when were videos last resolved successfully?  Reads only the session files' time and video id."""
import glob
import json
import os
import time

rows = []
for p in glob.glob(os.path.expanduser("~/.podtube/cache/sess/*.json")):
    try:
        d = json.load(open(p))
    except Exception:
        continue
    vid = d.get("videoId") or (d.get("info") or {}).get("videoId") or "?"
    rows.append((os.path.getmtime(p), vid, d.get("client") or (d.get("info") or {}).get("client") or "?"))
rows.sort()
print("sessions on disk: %d (older ones are purged after 8 hours)" % len(rows))
for t, vid, client in rows:
    print("%s  %-12s %s" % (time.strftime("%m-%d %H:%M", time.localtime(t)), vid, client))
print("now: " + time.strftime("%m-%d %H:%M"))
