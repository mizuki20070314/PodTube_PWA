#!/usr/bin/env python3
"""PodTube の api.cgi を手元から叩いて応答の形を見る道具。

  python tools/api.py GET  search q=猫
  python tools/api.py POST home '{"seen":[],"fresh":true}'
  python tools/api.py GET  watch v=dQw4w9WgXcQ
  オプション: --depth N (表示する入れ子の深さ、既定 4) --max N (配列の表示個数、既定 3) --raw
"""
import json, os, sys, urllib.parse, urllib.request

BASE = "https://my-dev.sakura.ne.jp/podtube/api.cgi/"
HERE = os.path.dirname(os.path.abspath(__file__))
KEY = open(os.path.join(os.path.dirname(HERE), "secrets", "pt_key")).read().strip()


def call(method, route, params=None, body=None, hl="ja", gl="JP", visitor=None):
    url = BASE + route + ("?" + urllib.parse.urlencode(params) if params else "")
    h = {"X-PT-Key": KEY, "X-PT-Hl": hl, "X-PT-Gl": gl, "Accept-Encoding": "gzip"}
    if visitor:
        h["X-PT-Visitor"] = visitor
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                import gzip
                raw = gzip.decompress(raw)
            return r.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read()
        if e.headers.get("Content-Encoding") == "gzip":
            import gzip
            raw = gzip.decompress(raw)
        return e.code, raw


def shrink(o, depth, mx):
    if isinstance(o, dict):
        if depth <= 0:
            return "{...%d keys}" % len(o)
        return {k: shrink(v, depth - 1, mx) for k, v in o.items()}
    if isinstance(o, list):
        if depth <= 0:
            return "[...%d items]" % len(o)
        r = [shrink(v, depth - 1, mx) for v in o[:mx]]
        if len(o) > mx:
            r.append("... (+%d more)" % (len(o) - mx))
        return r
    if isinstance(o, str) and len(o) > 90:
        return o[:90] + "…(%d)" % len(o)
    return o


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    depth = int(sys.argv[sys.argv.index("--depth") + 1]) if "--depth" in sys.argv else 4
    mx = int(sys.argv[sys.argv.index("--max") + 1]) if "--max" in sys.argv else 3
    a = [x for x in a if x not in (str(depth), str(mx))] if ("--depth" in sys.argv or "--max" in sys.argv) else a
    method, route = a[0].upper(), a[1]
    params, body = None, None
    for x in a[2:]:
        if x.startswith("{"):
            body = json.loads(x)
        elif "=" in x:
            params = params or {}
            k, v = x.split("=", 1)
            params[k] = v
    if method == "POST" and body is None:
        body = {}
    st, raw = call(method, route, params, body)
    print("HTTP", st, len(raw), "bytes")
    try:
        js = json.loads(raw)
    except Exception:
        print(raw[:500])
        return
    if "--raw" in sys.argv:
        print(json.dumps(js, ensure_ascii=False)[:20000])
    else:
        print(json.dumps(shrink(js, depth, mx), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
