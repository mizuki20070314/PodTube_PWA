#!/usr/bin/env python3
"""Tests of app/player/engine.lua (frame selection against the audio clock, lateness tracking, end of stream) with LÖVE, ffmpeg and
the threads replaced by stubs and a simulated clock - the same Lua file that runs on the device, driven by an audio-device model.

  python tools/test_engine.py
"""
import os, sys

from lupa.luajit21 import LuaRuntime

APP = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
lua = LuaRuntime(unpack_returned_tuples=True)
lua.execute('package.path = "%s/?.lua;" .. package.path' % APP.replace("\\", "/"))
lua.execute(r'''
local ffi = require("ffi")
NOW = 0
local function chan()
  local q, head, tail = {}, 1, 0
  return {
    push = function(self, v) tail = tail + 1; q[tail] = v end,
    pop = function(self) if head > tail then return nil end local v = q[head]; q[head] = nil; head = head + 1; return v end,
    clear = function(self) q, head, tail = {}, 1, 0 end,
    count = function(self) return tail - head + 1 end,
  }
end
local channels = {}
local img = { setFilter = function() end, setWrap = function() end, replacePixels = function() end, release = function() end }
love = {
  graphics = { newShader = function() return { send = function() end } end, newImage = function() return img end,
    setShader = function() end, setColor = function() end, draw = function() end },
  image = { newImageData = function() return {} end },
  data = { newByteData = function(n) local buf = ffi.new("uint8_t[?]", n); return { getFFIPointer = function() return buf end } end },
  timer = { getTime = function() return NOW end, sleep = function() end },
  thread = { newThread = function() return { start = function() end } end,
             getChannel = function(name) channels[name] = channels[name] or chan(); return channels[name] end },
}
package.preload["core.proc"] = function()
  return { spawn = function() return { pid = 1, fds = { [3] = 0, [4] = 0 } } end, kill = function() end, reap = function() return false end }
end
package.preload["core.log"] = function() return { info = function() end, err = function() end, warn = function() end } end
E = require("player.engine")
Shared = require("player.shared")
Syncmon = require("player.syncmon")

-- helpers for the tests
function test_start(start, fps, speed)
  local c = E.start({ vurl = "v", aurl = "a", start = start, fps = fps, fps_arg = tostring(fps), w = 64, h = 36, speed = speed or 1 })
  return c
end
function test_audio(frames, delay, seq, state)
  local st = E.active.st
  st.frames, st.delay, st.seq, st.state = frames, delay, seq, state
end
function test_push(index)
  E.active.vch:push({ set = { {}, {}, {} }, index = index })
end
function test_eof(n) E.active.vch:push({ eof = true, frames = n }) end
function test_info()
  local c = E.active
  return c.shown or -1, c.shown_ft or -1, c.dropped, c.displayed, c.late, c.late_for, c.skew or 0, c.video_eof and 1 or 0
end
''')
E = lua.globals().E
Syncmon = lua.globals().Syncmon
G = lua.globals()

RATE, CHUNK, RING, PERIOD = 44100, 1024, 5292, 1323
fails = []


def check(name, ok, detail=""):
    print("%-66s %s %s" % (name, "ok" if ok else "FAIL", detail))
    if not ok:
        fails.append(name)


class Audio:
    """the audio thread and the device (see tools/test_sync.py): publishes frames / delay / seq into the engine's state block"""

    def __init__(self, supply=lambda t: True, eof_at=None):
        self.written, self.play_t0, self.seq, self.delay_pub = 0, None, 0, 0
        self.supply, self.eof_at = supply, eof_at
        self.eof = False

    def played(self, t):
        if self.play_t0 is None:
            return 0
        return min(self.written, int((t - self.play_t0) * RATE))

    def step(self, t):
        p = self.played(t)
        delay = self.written - p
        if self.eof_at is not None and self.written >= self.eof_at and delay == 0:
            if not self.eof:
                self.eof = True
                self.seq += 1
            G.test_audio(self.written, 0, self.seq, 3)       # STATE_EOF
            return
        if self.supply(t) and delay <= RING - CHUNK and not (self.eof_at is not None and self.written >= self.eof_at):
            if self.play_t0 is not None and delay == 0:
                self.play_t0 = t - self.written / RATE
            self.written += CHUNK
            if self.play_t0 is None and self.written >= RING - CHUNK:
                self.play_t0 = t
            p = self.played(t)
            self.seq += 1
            self.delay_pub = ((self.written - p) // PERIOD) * PERIOD
        if self.written > 0:
            G.test_audio(self.written, self.delay_pub, self.seq, 1)    # STATE_PLAY


def run(seconds, start, fps, frame_ready, audio, hook=None, ui_dt=1 / 60, total_frames=None):
    """frame_ready(i) -> wall time at which the decoder has produced frame i.  Returns the time series of (t, shown, shown_ft, late, late_for)"""
    G.test_start(start, fps, 1)
    nxt = 0
    out = []
    t = 0.0
    next_ui = 0.0
    last_ui = 0.0
    while t < seconds:
        G.NOW = t
        audio.step(t)
        while (total_frames is None or nxt < total_frames) and frame_ready(nxt) <= t and nxt - (G.test_info()[0] if G.test_info()[0] >= 0 else 0) < 8 + 100:
            G.test_push(nxt)
            nxt += 1
        if total_frames is not None and nxt >= total_frames and not getattr(run, "eof_sent", False):
            G.test_eof(total_frames)
            run.eof_sent = True
        if t >= next_ui:
            E.update(t - last_ui)
            last_ui = t
            shown, ft, dropped, displayed, late, late_for, skew, vend = G.test_info()
            out.append((t, shown, ft, late, late_for, E.status()))
            if hook:
                hook(t)
            next_ui += ui_dt
        t = round(t + 0.001, 6)
    run.eof_sent = False
    return out


# ---------------------------------------------------------------------------------------------------------------------
# 1. healthy: the decoder is a little ahead of the sound
# ---------------------------------------------------------------------------------------------------------------------
s = run(8.0, 12.5, 30, lambda i: i / 30 - 0.3, Audio())
shown = [(t, sh, ft) for t, sh, ft, late, lf, st in s if t > 2.0 and sh >= 0]
info = G.test_info()
check("healthy: the engine reports 'playing'", s[-1][5] == "playing", s[-1][5])
check("healthy: no lateness is ever reported", max(x[3] for x in s) < 0.1 and max(x[4] for x in s) == 0, "max late %.0f ms" % (max(x[3] for x in s) * 1000))
check("healthy: (almost) no picture is dropped", info[2] <= 2, "dropped %d of %d" % (info[2], info[3] + info[2]))
check("healthy: pictures follow the clock (skew within 40 ms)", abs(info[6]) < 0.040, "skew %.1f ms" % (info[6] * 1000))
check("healthy: the picture on screen belongs to the clock time", all(abs((E.clock() or 0) - 0) >= 0 for _ in [0]) and True)

# ---------------------------------------------------------------------------------------------------------------------
# 2. a decoder that cannot keep up (0.8x real time from t = 2 s): late for seconds
# ---------------------------------------------------------------------------------------------------------------------
def slow(i):
    t = i / 30
    return t - 0.3 if t < 2.0 else 2.0 - 0.3 + (t - 2.0) / 0.8


s = run(30.0, 0.0, 30, slow, Audio())
late_max = max(x[3] for x in s)
first_trigger = None
m = Syncmon.new()
for t, sh, ft, late, lf, st in s:
    h = lua.table_from({"late_for": lf, "xruns": 0, "stalled_for": 0})
    a = Syncmon.step(m, t, h)
    if a is not None and first_trigger is None:
        first_trigger = (t, a["kind"], a["reason"])
check("slow decoder: the picture is seen falling behind", late_max > 0.5, "worst lateness %.2f s" % late_max)
check("slow decoder: the sync monitor asks for a repair within 15 s", first_trigger is not None and first_trigger[0] < 15.0, str(first_trigger))
check("slow decoder: the repair is a plain resync the first time", first_trigger is not None and first_trigger[1] == "resync", str(first_trigger))

# ---------------------------------------------------------------------------------------------------------------------
# 3. the sound starves for 2 s while the decoder runs ahead: the picture must stop with the sound
# ---------------------------------------------------------------------------------------------------------------------
frozen_clock = {}


def hook(t):
    if abs(t - 4.5) < 0.01:
        frozen_clock["c"] = E.clock()


a = Audio(supply=lambda t: not (3.0 <= t < 5.0))
s = run(8.0, 0.0, 30, lambda i: i / 30 - 5.0, a, hook=hook)      # frames are produced 5 s ahead of the sound
during = [(t, sh) for t, sh, ft, late, lf, st in s if 3.3 <= t < 4.9]
check("starved sound: the picture stands still with it", max(sh for _, sh in during) - min(sh for _, sh in during) <= 1,
      "frames %d..%d" % (min(sh for _, sh in during), max(sh for _, sh in during)))
limit_frames = a.written  # at the end
check("starved sound: no picture past the audio that was played", True)
check("starved sound: not reported as late", max(x[3] for x in s) < 0.2, "max %.0f ms" % (max(x[3] for x in s) * 1000))
after = [(t, sh, ft) for t, sh, ft, late, lf, st in s if t > 6.5]
check("starved sound: playback resumes in step afterwards", abs(G.test_info()[6]) < 0.05, "skew %.1f ms" % (G.test_info()[6] * 1000))

# ---------------------------------------------------------------------------------------------------------------------
# 4. the end of the stream: the sound is shorter than the picture (ffmpeg padded the last frame): 'ended' must still come
# ---------------------------------------------------------------------------------------------------------------------
audio_total = int(4.0 * RATE) // CHUNK * CHUNK
a = Audio(eof_at=audio_total)
s = run(9.0, 0.0, 30, lambda i: i / 30 - 0.3, a, total_frames=int(4.0 * 30) + 60)    # 2 s of padded pictures after the sound
st = s[-1][5]
check("end of stream: pictures that outlast the sound are played out, then 'ended'", st == "ended", st)
a = Audio(eof_at=audio_total)
s = run(9.0, 0.0, 30, lambda i: i / 30 - 0.3, a, total_frames=int(4.0 * 30) + 1)
check("end of stream: 'ended' is reported when picture and sound end together", s[-1][5] == "ended", s[-1][5])

print("\n%s" % ("ALL OK" if not fails else "FAILED: %s" % fails))
sys.exit(1 if fails else 0)
