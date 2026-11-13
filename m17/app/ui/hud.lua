-- The player's on-screen controls over the picture (PWA: 08a-controls.js): title bar, transport, seek bar, captions, stats.
local theme = require("ui.theme")
local D = require("ui.draw")
local T = require("ui.text")
local U = require("lib.util")
local I = require("core.i18n")

local c = theme.c
local H = {}

local W, HH = theme.W, theme.H

--- seek bar with chapter ticks; `frac` of the played part, `target` (optional) is where a pending seek goes
local function seekbar(x, y, w, frac, target, chapters, duration, buffering)
  D.rect(x, y, w, 4, { 1, 1, 1, 0.3 }, 2)
  if frac > 0 then D.rect(x, y, math.max(4, w * U.clamp(frac, 0, 1)), 4, c.red, 2) end
  if chapters and #chapters > 1 and duration > 0 then
    for i = 2, #chapters do
      local cx = x + w * chapters[i].start / duration
      D.rect(cx - 1, y - 1, 2, 6, { 0, 0, 0, 0.8 })
    end
  end
  local kx = x + w * U.clamp(target or frac, 0, 1)
  D.circle(kx, y + 2, target and 6 or 5, c.red)
end

--- Draws the controls.  s = { title=, position=, duration=, state=, pending=, chapters=, captions_on=, alpha=,
--- has_prev=, has_next=, speed=, error=, hint=, cue=, stats=  }
function H.draw(s)
  local a = s.alpha or 1
  if s.cue and s.cue ~= "" then
    local b = T.layout(s.cue, 380, { size = 15, weight = "bold", lines = 3, pitch = 19 })
    if b.h > 0 then
      local bw = b.w + 16
      local bx = (W - bw) / 2
      local by = (a > 0.3 and HH - 56 or HH - 24) - b.h
      D.rect(bx, by - 3, bw, b.h + 6, { 0, 0, 0, 0.62 }, 5)
      T.draw_block(b, bx + 8, by, c.white)
    end
  end
  if a <= 0.01 then return end
  -- top and bottom scrims
  D.rect(0, 0, W, 40, { 0, 0, 0, 0.55 * a })
  D.rect(0, HH - 74, W, 74, { 0, 0, 0, 0.6 * a })
  -- title bar
  D.icon("keyboard_arrow_down", 6, 6, 26, c.white, a)
  local tb = T.layout(s.title or "", 340, { size = 13, weight = "medium", lines = 1 })
  T.draw_block(tb, 36, 11, { 1, 1, 1, a })
  D.icon(s.captions_on and "closed_caption" or "closed_caption_off", W - 66, 8, 22, s.captions_on and c.white or { 1, 1, 1, 0.7 }, a)
  D.icon("settings", W - 34, 8, 22, c.white, a)
  -- transport in the middle
  local st = s.state
  local cx, cy = W / 2, HH / 2 - 8
  if st == "loading" or st == "buffering" then
    D.spinner(cx, cy, 18, c.white, a)
  elseif st ~= "failed" then
    D.icon("skip_previous", cx - 78, cy - 16, 32, c.white, a * (s.has_prev and 1 or 0.35))
    D.circle(cx, cy, 27, { 0, 0, 0, 0.35 * a })
    D.icon((st == "playing") and "pause" or "play_arrow", cx - 20, cy - 20, 40, c.white, a)
    D.icon("skip_next", cx + 46, cy - 16, 32, c.white, a * (s.has_next and 1 or 0.35))
  end
  -- time + seek bar
  local pos = s.pending or s.position or 0
  local dur = s.duration or 0
  local frac = dur > 0 and pos / dur or 0
  local label = U.clock(pos) .. " / " .. U.clock(dur)
  T.print(label, 14, HH - 50, 12, "medium", { 1, 1, 1, a })
  if s.speed and math.abs(s.speed - 1) > 0.01 then
    T.print(string.format("%gx", s.speed), W - 90, HH - 50, 12, "bold", { 1, 1, 1, a })
  end
  if s.chapter then
    T.line(s.chapter, 150, HH - 50, W - 260, 12, "regular", { 1, 1, 1, a * 0.85 })
  end
  seekbar(14, HH - 28, W - 28, s.position and dur > 0 and (s.position / dur) or 0, s.pending and dur > 0 and (s.pending / dur) or nil, s.chapters, dur)
  if s.hint then
    T.line(s.hint, 8, HH - 20, W - 16, 10, "regular", { 1, 1, 1, 0.75 * a }, "center")
  end
  -- the film strip: the frame of the storyboard at the pending position, above the bar
  if s.pending and dur > 0 and s.preview then
    local lv = s.preview.lvl
    local pw = 128
    local ph = math.floor(pw * lv.h / lv.w)
    local px = U.clamp(14 + (W - 28) * s.pending / dur - pw / 2, 6, W - 6 - pw)
    local py = HH - 28 - 12 - ph
    D.rect(px - 2, py - 2, pw + 4, ph + 4, { 0, 0, 0, 0.85 }, 4)
    local img = s.preview.img
    if img then
      local iw, ih = img:getDimensions()
      local q = love.graphics.newQuad(s.preview.cell.col * lv.w, s.preview.cell.row * lv.h, lv.w, lv.h, iw, ih)
      love.graphics.setColor(1, 1, 1, 1)
      love.graphics.draw(img, q, px, py, 0, pw / lv.w, ph / lv.h)
    else
      D.rect(px, py, pw, ph, c.thumb_ph)
    end
    local label = U.clock(s.pending)
    local lw = T.width(label, 11, "bold")
    D.rect(px + pw / 2 - lw / 2 - 4, py + ph - 15, lw + 8, 14, { 0, 0, 0, 0.7 }, 3)
    T.print(label, px + pw / 2 - lw / 2, py + ph - 14, 11, "bold", c.white)
  end
end

function H.draw_error(message, hint)
  local b = T.layout(message or "", 340, { size = 13, weight = "medium", lines = 4, pitch = 18 })
  D.icon("cloud_off", W / 2 - 16, HH / 2 - 52, 32, c.secondary)
  T.draw_block(b, (W - b.w) / 2, HH / 2 - 10, c.text)
  if hint then T.line(hint, 20, HH / 2 + 20 + b.h, W - 40, 12, "medium", c.link, "center") end
end

function H.draw_stats(s)
  if not s then return end
  local lines = {
    string.format("%dx%d @%.3gfps  %s", s.w or 0, s.h or 0, s.fps or 0, s.speed and ("x" .. s.speed) or ""),
    string.format("frames %d  shown %d  dropped %d", s.frames or 0, s.displayed or 0, s.dropped or 0),
    string.format("audio buffer %d/%dms  xruns %d", math.floor(s.delay_ms or 0), math.floor(s.latency_ms or 0), s.xruns or 0),
    string.format("A/V %+dms  late %dms  repairs %d", math.floor(s.skew_ms or 0), math.floor(s.late_ms or 0), s.fixes or 0),
    string.format("fps %.1f  mem %dMB", s.ui_fps or 0, s.mem_mb or 0),
  }
  D.rect(4, 30, 210, 69, { 0, 0, 0, 0.7 }, 4)
  for i, l in ipairs(lines) do T.print(l, 8, 32 + (i - 1) * 13, 10, "regular", c.white) end
end

return H
