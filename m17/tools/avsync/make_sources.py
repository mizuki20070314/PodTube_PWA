#!/usr/bin/env python3
"""A/V sync test sources: a white flash (video) and a 1 kHz beep (audio) start together at media time 0.5 + k seconds (k = 0..10).

Video and audio are separate HLS playlists, like the ones the server hands to the player: MPEG-TS segments ("ts") and
fragmented MP4 with an init segment ("fmp4", what the real server serves).  Both tracks come from ONE combined encode (so a flash and
its beep carry the very same container time stamp) and are split afterwards by stream copy; the head of either track can be cut
(its first time stamp is then later than the other's, as with real streams whose video starts a frame in).  A correct player shows
the flash and plays the beep at the same moment whatever the start times of the two tracks are.

  python tools/avsync/make_sources.py [outdir]        (needs an ffmpeg with libx264: pip install imageio-ffmpeg)

Writes <outdir>/<kind>_<variant>/{v,a}/index.m3u8 and truth.json (container times of the first flash / first beep).
"""
import json, os, re, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 64, 36
DUR = 11.0

# name: (video_cut, audio_cut, fps)
VARIANTS = {
    "base":    (0.0, 0.0, "24"),
    "vlate":   (0.5, 0.0, "24"),                 # the video track starts 0.5 s into the media
    "alate":   (0.0, 0.3, "24"),                 # the audio track starts 0.3 s into the media
    "vlate1f": (0.0417, 0.0, "24"),              # one frame in, like the real streams (start 0.033)
    "ntsc":    (0.0, 0.0, "30000/1001"),
}
KINDS = ("ts", "fmp4")


def find_ffmpeg():
    p = os.environ.get("FFMPEG_PC")
    if p and os.path.exists(p):
        return p
    for d in sys.path:
        c = os.path.join(d, "imageio_ffmpeg", "binaries")
        if os.path.isdir(c):
            for f in os.listdir(c):
                if f.startswith("ffmpeg"):
                    return os.path.join(c, f)
    w = shutil.which("ffmpeg")
    if w:
        return w
    raise SystemExit("ffmpeg (libx264) not found: set FFMPEG_PC or pip install imageio-ffmpeg")


def run(cmd, cwd=None, what=""):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True)
    if r.returncode != 0:
        sys.stderr.write(r.stderr.decode("utf-8", "replace")[-2500:])
        raise SystemExit("ffmpeg failed: " + what)
    return r.stderr.decode("utf-8", "replace")


def combined(ff, d, vcut, acut, fps):
    on = "gte(t,0.5)*lt(mod(t-0.5,1),0.12)"
    vsrc = "color=c=black:s=%dx%d:r=%s:d=%g,drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='%s'" % (W, H, fps, DUR, on)
    asrc = "aevalsrc=exprs='0.8*sin(2*PI*1000*t)*%s|0.8*sin(2*PI*1000*t)*%s':s=44100:d=%g" % (on, on, DUR)
    if vcut > 0:
        vsrc += ",trim=start=%g" % vcut
    if acut > 0:
        asrc += ",atrim=start=%g" % acut
    gop = "48" if fps == "24" else "60"
    mux = os.path.join(d, "mux.ts")
    run([ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", vsrc, "-f", "lavfi", "-i", asrc, "-copyts",
         "-c:v", "libx264", "-preset", "veryfast", "-bf", "2", "-g", gop, "-keyint_min", gop, "-sc_threshold", "0",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k", "-ar", "44100",
         "-muxdelay", "0", "-muxpreload", "0", "-f", "mpegts", mux], what="combined")
    return mux


def split_ts(ff, mux, d):
    for sub, mp in (("v", "0:v:0"), ("a", "0:a:0")):
        os.makedirs(os.path.join(d, sub))
        run([ff, "-y", "-loglevel", "error", "-copyts", "-i", mux, "-map", mp, "-c", "copy", "-avoid_negative_ts", "disabled",
             "-muxdelay", "0", "-muxpreload", "0",
             "-f", "hls", "-hls_time", "2", "-hls_playlist_type", "vod", "-hls_flags", "independent_segments",
             "-hls_segment_type", "mpegts", "-hls_segment_filename", "seg%d.ts", "index.m3u8"],
            cwd=os.path.join(d, sub), what="ts " + sub)


def split_fmp4(ff, mux, d):
    # one muxer run writes both playlists, so the relative time stamps of the two tracks are kept
    run([ff, "-y", "-loglevel", "error", "-copyts", "-i", mux, "-map", "0:v:0", "-map", "0:a:0", "-c", "copy", "-bsf:a", "aac_adtstoasc",
         "-avoid_negative_ts", "disabled", "-f", "hls", "-hls_time", "2", "-hls_playlist_type", "vod",
         "-hls_flags", "independent_segments", "-hls_segment_type", "fmp4",
         "-hls_fmp4_init_filename", "init.mp4", "-hls_segment_filename", "s%v/seg%d.m4s",
         "-master_pl_name", "master.m3u8", "-var_stream_map", "v:0,agroup:aud a:0,agroup:aud,default:yes", "s%v/index.m3u8"],
        cwd=d, what="fmp4")
    os.rename(os.path.join(d, "s0"), os.path.join(d, "v"))
    os.rename(os.path.join(d, "s1"), os.path.join(d, "a"))


def truth(ff, d):
    """container times (seconds) of the first flash and the first beep, read back from the playlists"""
    log = run([ff, "-hide_banner", "-copyts", "-i", os.path.join(d, "v", "index.m3u8"), "-vf", "showinfo", "-f", "null", "-"], what="showinfo")
    vstart, flash = None, None
    for m in re.finditer(r"pts_time:([\d.]+).*?mean:\[(\d+)", log):
        t, y = float(m.group(1)), int(m.group(2))
        if vstart is None:
            vstart = t
        if flash is None and y > 128:
            flash = t
    log = run([ff, "-hide_banner", "-copyts", "-i", os.path.join(d, "a", "index.m3u8"), "-af", "silencedetect=n=-30dB:d=0.3", "-f", "null", "-"],
              what="silencedetect")
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", log)]
    m = re.search(r"start: (-?[\d.]+)", log)
    astart = float(m.group(1)) if m else None
    return {"vstart": vstart, "flash": flash, "astart": astart, "beep": ends[0] if ends else None}


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "out")
    ff = find_ffmpeg()
    os.makedirs(out, exist_ok=True)
    for kind in KINDS:
        for name, (vc, ac, fps) in VARIANTS.items():
            d = os.path.join(out, kind + "_" + name)
            shutil.rmtree(d, ignore_errors=True)
            os.makedirs(d)
            mux = combined(ff, d, vc, ac, fps)
            (split_ts if kind == "ts" else split_fmp4)(ff, mux, d)
            os.remove(mux)
            for junk in ("master.m3u8",):
                p = os.path.join(d, junk)
                if os.path.exists(p):
                    os.remove(p)
            t = truth(ff, d)
            t["fps"] = 30000 / 1001 if fps != "24" else 24
            json.dump(t, open(os.path.join(d, "truth.json"), "w"))
            print("%-14s video start %.4f first flash %.4f | audio start %.4f first beep %.4f | flash-beep %+.4f" % (
                kind + "_" + name, t["vstart"], t["flash"], t["astart"], t["beep"], t["flash"] - t["beep"]))
    print("sources in", out)


if __name__ == "__main__":
    main()
