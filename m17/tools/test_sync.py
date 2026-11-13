#!/usr/bin/env python3
"""Tests of the pure parts of the sync machinery (app/player/clock.lua, syncmon.lua, ffargs.lua) with simulated time, run in LuaJIT
through lupa.   python tools/test_sync.py

The clock is simulated against a model of the audio device: the audio thread writes 1024-frame chunks into a 120 ms ring, the
device plays them in real time, and snd_pcm_delay is known to a period (1323 frames) only.
"""
import os, sys

from lupa.luajit21 import LuaRuntime

APP = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
lua = LuaRuntime(unpack_returned_tuples=True)
lua.execute('package.path = "%s/?.lua;" .. package.path' % APP.replace("\\", "/"))
Clock = lua.eval('(require("player.clock"))')
Syncmon = lua.eval('(require("player.syncmon"))')
Ffargs = lua.eval('(require("player.ffargs"))')

RATE = 44100
CHUNK = 1024
RING = 5292                    # 120 ms
PERIOD = 1323                  # 30 ms
fails = []


def check(name, ok, detail=""):
    print("%-62s %s %s" % (name, "ok" if ok else "FAIL", detail))
    if not ok:
        fails.append(name)


class Device:
    """audio thread + device: `step(t)` at 1 ms resolution; the thread writes whenever the ring has room and data is available"""

    def __init__(self, start=0.0, speed=1.0, supply=lambda t: True):
        self.start, self.speed, self.supply = start, speed, supply
        self.written = 0            # frames handed to the device
        self.play_t0 = None         # wall time the device started playing
        self.seq = 0
        self.delay_pub = 0
        self.paused = False

    def played(self, t):
        if self.play_t0 is None or self.paused:
            return getattr(self, "_p", 0)
        return min(self.written, int((t - self.play_t0) * RATE))

    def step(self, t):
        if self.paused:
            return
        p = self.played(t)
        delay = self.written - p
        if self.supply(t) and delay <= RING - CHUNK:
            if self.play_t0 is not None and delay == 0:
                self.play_t0 = t - self.written / RATE      # the device ran dry and starts again with this write (xrun recovery)
            self.written += CHUNK
            if self.play_t0 is None and self.written >= RING - CHUNK:       # the device starts when its ring is nearly full
                self.play_t0 = t
            p = self.played(t)
            self.seq += 1
            self.delay_pub = ((self.written - p) // PERIOD) * PERIOD        # known to a period only
        self._p = p

    def state(self, t):
        return lua.table_from({"started": self.written > 0, "seq": self.seq, "frames": self.written, "delay": self.delay_pub})

    def audible(self, t):
        return self.start + self.played(t) / RATE * self.speed


def run_clock(dev, clock, seconds, dt_ui=0.016, hook=None):
    series = []
    t = 0.0
    next_ui = 0.0
    while t < seconds:
        dev.step(t)
        if hook:
            hook(t)
        if t >= next_ui:
            c = Clock.get(clock, t, dev.state(t))
            if c is not None:
                series.append((t, c, dev.audible(t)))
            next_ui += dt_ui
        t = round(t + 0.001, 6)
    return series


# ---------------------------------------------------------------------------------------------------------------------
# clock
# ---------------------------------------------------------------------------------------------------------------------
dev = Device(start=12.5)
clk = Clock.new(12.5, RATE, 1)
s = run_clock(dev, clk, 6.0)
warm = [(t, c, a) for t, c, a in s if t > 1.0]
err = [c - a for _, c, a in warm]
check("clock: steady playback stays within 45 ms of the audible position", max(abs(e) for e in err) < 0.045,
      "max %.1f ms, mean %.1f ms" % (max(abs(e) for e in err) * 1000, sum(err) / len(err) * 1000))
mono = all(s[i + 1][1] >= s[i][1] - 1e-9 for i in range(len(s) - 1))
check("clock: never goes backwards in steady playback", mono)
check("clock: is nil before the audio has started", Clock.get(Clock.new(0, RATE, 1), 0.0, lua.table_from({"started": False, "seq": 0, "frames": 0, "delay": 0})) is None)

# an under-run: the pipe from ffmpeg is empty from t=3 s to t=4.5 s
dev = Device(start=0.0, supply=lambda t: not (3.0 <= t < 4.5))
clk = Clock.new(0.0, RATE, 1)
s = run_clock(dev, clk, 7.0)
# replay to know the written frames over time
dev2 = Device(start=0.0, supply=lambda t: not (3.0 <= t < 4.5))
w_at = []
t = 0.0
while t < 7.0:
    dev2.step(t)
    w_at.append((t, dev2.written))
    t = round(t + 0.001, 6)
lim = {round(t, 3): w / RATE for t, w in w_at}
bad = [(t, c) for t, c, a in s if c > lim[round(t, 3)] + 1e-6]
check("clock: never runs past the end of the audio handed to the device", not bad, "%d violations" % len(bad))
during = [(t, c) for t, c, a in s if 3.3 <= t < 4.5]
spread = max(c for _, c in during) - min(c for _, c in during)
check("clock: stands still while the sound is starved", spread < 0.005, "moved %.1f ms in 1.2 s" % (spread * 1000))
after = [(t, c, a) for t, c, a in s if t > 5.5]
check("clock: follows the sound again after an under-run", max(abs(c - a) for _, c, a in after) < 0.045,
      "max %.1f ms" % (max(abs(c - a) for _, c, a in after) * 1000))
jump = max((s[i][1] - s[i - 1][1]) for i in range(1, len(s)))
back = min((s[i][1] - s[i - 1][1]) for i in range(1, len(s)))
check("clock: no jump and no step back at the under-run", jump < 0.06 and back > -0.01, "max step %.1f ms, min step %.1f ms" % (jump * 1000, back * 1000))

# the audio has ended for good: the clock runs on (a picture that outlasts the sound plays out)
dev = Device(start=0.0)
clk = Clock.new(0.0, RATE, 1)
run_clock(dev, clk, 2.0)
final = dev.written
c1 = Clock.get(clk, 2.0, lua.table_from({"started": True, "seq": dev.seq + 1, "frames": final, "delay": 0, "eof": True}))
c2 = Clock.get(clk, 4.0, lua.table_from({"started": True, "seq": dev.seq + 1, "frames": final, "delay": 0, "eof": True}))
check("clock: runs on after the audio has ended", c2 - c1 > 1.9 and c2 > final / RATE + 1.5, "%.2f -> %.2f (audio ended at %.2f)" % (c1, c2, final / RATE))

# speed 1.5 (atempo): media time runs 1.5x
dev = Device(start=0.0, speed=1.5)
clk = Clock.new(0.0, RATE, 1.5)
s = run_clock(dev, clk, 6.0)
err = [c - a for t, c, a in s if t > 1.0]
check("clock: playback speed 1.5 follows the audible position", max(abs(e) for e in err) < 0.06, "max %.1f ms" % (max(abs(e) for e in err) * 1000))

# pause / resume
dev = Device(start=0.0)
clk = Clock.new(0.0, RATE, 1)
state = {}


def pause_hook(t):
    if abs(t - 2.0) < 5e-4:
        state["at_pause"] = Clock.get(clk, t, dev.state(t))
        Clock.pause(clk)
        dev._p = dev.played(t)
        dev.paused = True
        dev.written = dev._p            # snd_pcm_drop: what was queued is gone
        dev.delay_pub = 0
        dev.seq += 1
    if abs(t - 3.0) < 5e-4:
        dev.paused = False
        dev.play_t0 = t - dev._p / RATE
        Clock.resume(clk)


s = run_clock(dev, clk, 5.0, hook=pause_hook)
in_pause = [c for t, c, a in s if 2.05 < t < 2.95]
check("clock: stands still while paused", max(in_pause) - min(in_pause) < 0.01, "moved %.1f ms" % ((max(in_pause) - min(in_pause)) * 1000))
after = [(t, c, a) for t, c, a in s if t > 3.5]
check("clock: follows the sound after a pause", max(abs(c - a) for _, c, a in after) < 0.06, "max %.1f ms" % (max(abs(c - a) for _, c, a in after) * 1000))

# ---------------------------------------------------------------------------------------------------------------------
# sync monitor
# ---------------------------------------------------------------------------------------------------------------------
def H(late_for=0.0, xruns=0, stalled_for=0.0):
    return lua.table_from({"late_for": late_for, "xruns": xruns, "stalled_for": stalled_for})


m = Syncmon.new()
acts = [Syncmon.step(m, t, H()) for t in range(0, 120)]
check("syncmon: a healthy playback is left alone", all(a is None for a in acts))

m = Syncmon.new()
a1 = Syncmon.step(m, 10.0, H(late_for=3.2))
check("syncmon: picture late for 3 s -> resync", a1 is not None and a1["kind"] == "resync" and a1["reason"] == "late")
check("syncmon: not twice within the minimum gap", Syncmon.step(m, 12.0, H(late_for=3.5)) is None)
Syncmon.new_run(m)
a2 = Syncmon.step(m, 30.0, H(late_for=3.1))
check("syncmon: the trouble coming back soon -> lighter picture", a2 is not None and a2["kind"] == "degrade", str(a2["kind"] if a2 else None))
a3 = Syncmon.step(m, 130.0, H(late_for=3.1))
check("syncmon: trouble long after the last one -> plain resync", a3 is not None and a3["kind"] == "resync", str(a3["kind"] if a3 else None))

m = Syncmon.new()
res = None
for i, t in enumerate([100, 101, 102, 103, 104, 105]):
    r = Syncmon.step(m, float(t), H(xruns=i * 1))
    if r:
        res = r
check("syncmon: 4+ under-runs within 10 s -> bigger device buffer", res is not None and res["reason"] == "xruns" and res["latency"], str(res["reason"] if res else None))
m = Syncmon.new()
res = [Syncmon.step(m, 5.0 * i, H(xruns=i)) for i in range(20)]
check("syncmon: a slow trickle of under-runs is ignored", all(r is None for r in res))

m = Syncmon.new()
r = Syncmon.step(m, 50.0, H(stalled_for=16))
check("syncmon: nothing moving for 15 s -> plain resync", r is not None and r["reason"] == "stall" and r["kind"] == "resync")

m = Syncmon.new()
n = 0
for i in range(40):
    if Syncmon.step(m, 10.0 + i * 20, H(late_for=4.0)):
        n += 1
check("syncmon: gives up after the maximum number of repairs", n == int(Syncmon.MAX_ACTIONS), "repairs %d" % n)

# ---------------------------------------------------------------------------------------------------------------------
# command line
# ---------------------------------------------------------------------------------------------------------------------
def argv(**spec):
    base = {"vurl": "V", "aurl": "A", "start": 0, "fps": 30, "fps_arg": "30", "speed": 1, "rate": 44100, "threads": 3}
    base.update(spec)
    t = Ffargs.build(lua.table_from(base))
    return [t[i] for i in range(1, len(t) + 1)]


a = argv()
check("ffargs: from the start no -ss and no pre-roll", "-ss" not in a and "-itsoffset" not in a)
check("ffargs: both inputs keep the stream's time stamps", a.count("-seek_timestamp") == 2)
a = argv(start=100.7)
i = a.index("-itsoffset")
vi = a.index("V")
check("ffargs: a seek reads the video from before the position and shifts it back", a[a.index("-ss") + 1] == "94.2" and a[i + 1] == "-6.5" and i < vi,
      "ss %s itsoffset %s" % (a[a.index("-ss") + 1], a[i + 1]))
check("ffargs: audio is cut at the exact position", a[a.index("A") - 3:a.index("A") - 1] == ["-ss", "100.7"])
a = argv(start=3.2)
check("ffargs: near the start the pre-roll is the whole start", a[a.index("-itsoffset") + 1] == "-3.2" and "-ss" not in a[:a.index("V")], str(a[:16]))
vf = a[a.index("-vf") + 1]
check("ffargs: pictures are made constant-rate from time 0", "fps=fps=30:start_time=0" in vf and "trim=start=0" in vf, vf)
af = a[a.index("-af") + 1]
check("ffargs: audio starts exactly at time 0", "aresample=async=1:first_pts=0" in af, af)
a = argv(single="/x.mp4", vurl=None, aurl=None, start=20)
check("ffargs: a downloaded file is one input", a.count("-i") == 1 and a[a.index("-ss") + 1] == "20", str(a[:12]))

print("\n%s" % ("ALL OK" if not fails else "FAILED: %s" % fails))
sys.exit(1 if fails else 0)
