-- Sync monitor: decides when the player should repair a playback that has fallen out of step, from the health numbers of the
-- engine (Engine.health()).  Pure code (no LÖVE): tools/test_sync.py runs it with simulated time.
--
-- What can go wrong while playing, with the sound as the master clock:
--   late    the picture is behind the sound (the decoder cannot keep up, a video segment is slow): frames are dropped to catch up,
--           and when that does not work for seconds, the only repair is to start again from the current position - and, if it
--           happens again soon, with a lighter picture (lower quality / frame rate);
--   xruns   the sound itself breaks up (the device ran dry): start again with a bigger device buffer (and a lighter picture);
--   stall   nothing moves for a long time: start again from the current position.
-- Everything else (an offset from the start of the stream, a seek that lands late) is made right by construction in ffargs.lua.
local M = {}

M.LATE_S = 0.25          -- the next picture is overdue by more than this ...
M.LATE_FOR = 3.0         -- ... for this long: act
M.STALL_FOR = 15.0       -- nothing new from the stream for this long: act
M.XRUN_COUNT = 4         -- this many device under-runs ...
M.XRUN_WINDOW = 10.0     -- ... within this many seconds: act
M.MIN_GAP = 6.0          -- never act twice within this many seconds
M.REPEAT_S = 45.0        -- a second trouble within this many seconds of the first one means: lighter picture
M.MAX_ACTIONS = 6        -- per video; then give up (the sound plays on, the picture follows as well as it can)

function M.new()
  return { actions = 0, last = -1e9, events = {}, xr = {} }
end

--- a new engine run starts (after a seek / a repair): the windows of the old run mean nothing any more
function M.new_run(m)
  m.xr = {}
end

--- h = { late_for = seconds the next picture has been overdue by more than LATE_S, stalled_for = seconds without news from the
--- stream, xruns = under-runs of this engine run so far }.  Returns nil or { kind = "resync" | "degrade", reason =, latency = bool }
function M.step(m, now, h)
  if m.actions >= M.MAX_ACTIONS then return nil end
  local reason
  if h.late_for and h.late_for >= M.LATE_FOR then
    reason = "late"
  elseif h.stalled_for and h.stalled_for >= M.STALL_FOR then
    reason = "stall"
  elseif h.xruns then
    local xr = m.xr
    xr[#xr + 1] = { now, h.xruns }
    while #xr > 1 and now - xr[1][1] > M.XRUN_WINDOW do table.remove(xr, 1) end
    if h.xruns - xr[1][2] >= M.XRUN_COUNT then reason = "xruns" end
  end
  if not reason then return nil end
  if now - m.last < M.MIN_GAP then return nil end
  m.last = now
  m.actions = m.actions + 1
  local act = { kind = "resync", reason = reason, latency = (reason == "xruns") }
  if reason ~= "stall" then
    local recent = 0
    for _, t in ipairs(m.events) do if now - t < M.REPEAT_S then recent = recent + 1 end end
    if recent >= 1 then act.kind = "degrade" end
    m.events[#m.events + 1] = now
  end
  return act
end

return M
