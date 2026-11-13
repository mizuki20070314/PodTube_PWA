-- Sheet: a modal list of actions (menus, pickers, confirmations).  Gamepad: up/down, A = choose, B = close.
local theme = require("ui.theme")
local D = require("ui.draw")
local T = require("ui.text")
local U = require("lib.util")

local c = theme.c
local Sheet = {}
Sheet.__index = Sheet

local PW = 340
local ROW, ROW_SUB, HEAD = 34, 46, 30

--- opts: title, items={ {label=, sub=, icon=, checked=, danger=, keep_open=, on=function() end}, ... }, sel=, on_close=
function Sheet.new(opts)
  local s = setmetatable({}, Sheet)
  s.title = opts.title
  s.items = opts.items or {}
  s.sel = opts.sel or 1
  if s.sel > #s.items then s.sel = 1 end
  s.on_close = opts.on_close
  s.top = 0
  s.pw = opts.width or PW
  s.name = "sheet"
  -- if the caller did not say which row is current, start on the checked one
  if not opts.sel then
    for i, it in ipairs(s.items) do if it.checked then s.sel = i; break end end
  end
  return s
end

local function item_h(it) return it.sub and ROW_SUB or ROW end

function Sheet:total()
  local h = 0
  for _, it in ipairs(self.items) do h = h + item_h(it) end
  return h
end

function Sheet:close()
  App.close_sheet()
  if self.on_close then self.on_close() end
end

function Sheet:action(act, kind)
  if kind == "release" then return true end
  local n = #self.items
  if act == "down" then
    if n > 0 then self.sel = self.sel % n + 1 end
  elseif act == "up" then
    if n > 0 then self.sel = (self.sel - 2) % n + 1 end
  elseif act == "a" then
    local it = self.items[self.sel]
    if it then
      if not it.keep_open then self:close() end
      if it.on then it.on(it) end
    end
  elseif act == "b" or act == "start" or act == "menu" then
    self:close()
  end
  App.dirty = true
  return true
end

function Sheet:update(dt)
  -- keep the selected row visible
  local y = 0
  for i, it in ipairs(self.items) do
    local h = item_h(it)
    if i == self.sel then
      local avail = self.avail or 200
      if y < self.top then self.top = y end
      if y + h > self.top + avail then self.top = y + h - avail end
    end
    y = y + h
  end
end

function Sheet:draw()
  D.rect(0, 0, theme.W, theme.H, c.black, 0, 0.55)
  local total = self:total()
  local head = self.title and HEAD or 6
  local ph = math.min(head + total + 8, theme.H - 24)
  self.avail = ph - head - 8
  local px = math.floor((theme.W - self.pw) / 2)
  local py = math.floor((theme.H - ph) / 2)
  D.rect(px, py, self.pw, ph, c.sheet, 10)
  if self.title then
    T.line(self.title, px + 14, py + 6, self.pw - 28, 13, "bold", c.text)
    D.rect(px + 8, py + HEAD - 2, self.pw - 16, 1, c.divider)
  end
  D.clip(px, py + head, self.pw, ph - head - 4)
  local y = py + head - self.top
  for i, it in ipairs(self.items) do
    local h = item_h(it)
    if y + h > py + head - 2 and y < py + ph then
      if i == self.sel then
        D.rect(px + 6, y + 1, self.pw - 12, h - 2, c.surface_high, 8)
        D.outline(px + 6, y + 1, self.pw - 12, h - 2, c.white, 8, 1.5, 0.9)
      end
      local tx = px + 16
      if it.icon then D.icon(it.icon, tx, y + (h - 18) / 2, 18, it.danger and c.red or c.text); tx = tx + 28 end
      local tw = px + self.pw - 40 - tx
      if it.sub then
        T.line(it.label or "", tx, y + 5, tw, 13, "medium", it.danger and c.red or c.text)
        T.line(it.sub, tx, y + 24, tw, 11, "regular", c.secondary)
      else
        T.line(it.label or "", tx, y + (h - 16) / 2, tw, 13, "regular", it.danger and c.red or c.text)
      end
      if it.checked then D.icon("check", px + self.pw - 34, y + (h - 18) / 2, 18, c.white) end
    end
    y = y + h
  end
  D.unclip()
end

return Sheet
