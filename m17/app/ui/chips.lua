-- ChipBar: the row of pills under the app bar (Home topics, channel tabs ...)
local theme = require("ui.theme")
local D = require("ui.draw")
local T = require("ui.text")
local U = require("lib.util")

local c = theme.c
local Chips = {}
Chips.__index = Chips

local H = 22
local GAP = 6

function Chips.new(titles, selected)
  local s = setmetatable({}, Chips)
  s.titles = titles
  s.sel = selected or 1       -- the active chip
  s.focus = selected or 1     -- where the cursor is
  s.scroll = 0
  s.height = H + 8
  return s
end

function Chips:set(titles, selected)
  self.titles = titles
  self.sel = selected or 1
  self.focus = self.sel
end

local function widths(self)
  local ws, x = {}, 0
  for i, t in ipairs(self.titles) do
    local w = math.floor(T.width(t, 12, "medium") + 22)
    ws[i] = { x = x, w = w }
    x = x + w + GAP
  end
  return ws, x
end

function Chips:move(d)
  local n = #self.titles
  local nf = U.clamp(self.focus + d, 1, n)
  if nf == self.focus then return false end
  self.focus = nf
  App.dirty = true
  return true
end

function Chips:update(dt, w)
  local ws, total = widths(self)
  local f = ws[self.focus]
  if f then
    local target = self.scroll
    if f.x - 8 < target then target = f.x - 8 end
    if f.x + f.w + 8 > target + w then target = f.x + f.w + 8 - w end
    target = U.clamp(target, 0, math.max(0, total - w - GAP))
    self.target = target
  end
  self.scroll = U.damp(self.scroll, self.target or 0, 16, dt)
  if math.abs(self.scroll - (self.target or 0)) > 0.3 then App.dirty = true end
end

function Chips:draw(x, y, w, focused)
  local ws = widths(self)
  D.clip(x, y, w, self.height)
  for i, t in ipairs(self.titles) do
    local r = ws[i]
    local cx = x + 8 + r.x - self.scroll
    if cx + r.w > x and cx < x + w then
      local sel = (i == self.sel)
      D.rect(cx, y + 4, r.w, H, sel and c.chip_sel or c.surface, H / 2)
      if focused and i == self.focus then D.focus_ring(cx, y + 4, r.w, H, H / 2) end
      T.line(t, cx + 11, y + 4 + (H - 16) / 2, r.w - 22, 12, "medium", sel and c.chip_sel_text or c.text)
    end
  end
  D.unclip()
end

return Chips
