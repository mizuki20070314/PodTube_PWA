-- MenuList: vertical list of settings-style rows with gamepad focus.
--   {kind="section", label=}            heading
--   {kind="choice", label=, value=, on=}   value + chevron
--   {kind="toggle", label=, get=, set=}    switch
--   {kind="button", label=, danger=, on=}  action
--   {kind="info", label=, value=}           not focusable
--   {kind="note", text=}                    paragraph, not focusable
--   {kind="item", icon=, label=, count=, on=, sub=, avatar=}   library-style row with icon and chevron
local theme = require("ui.theme")
local D = require("ui.draw")
local T = require("ui.text")
local Img = require("core.img")
local U = require("lib.util")

local c = theme.c
local M = {}
M.__index = M

local ROW = 34
local ROW_ITEM = 40

function M.new(items, opts)
  local m = setmetatable({}, M)
  m.o = opts or {}
  m.items = items or {}
  m.sel = 1
  m.scroll, m.target = 0, 0
  m.view_h = 200
  m.w = 0
  m.layout_w = -1
  m:first_focusable()
  return m
end

function M:set_items(items)
  self.items = items
  self.layout_w = -1
  if self.sel > #items then self.sel = math.max(1, #items) end
  self:fix_sel(1)
  App.dirty = true
end

local function focusable(it) return it.kind ~= "section" and it.kind ~= "note" and it.kind ~= "info" end

function M:first_focusable()
  for i, it in ipairs(self.items) do if focusable(it) then self.sel = i; return end end
end

function M:fix_sel(dir)
  local i = self.sel
  while self.items[i] and not focusable(self.items[i]) do i = i + dir end
  if not self.items[i] then
    i = self.sel
    while self.items[i] and not focusable(self.items[i]) do i = i - dir end
  end
  if self.items[i] then self.sel = i end
end

local function layout(self, w)
  if self.layout_w == w then return end
  self.layout_w = w
  local y = 0
  for _, it in ipairs(self.items) do
    it.y = y
    if it.kind == "section" then it.h = 26
    elseif it.kind == "note" then
      it.block = T.layout(it.text or "", w - 36, { size = 10, lines = 6, pitch = 13 })
      it.h = it.block.h + 10
    elseif it.kind == "item" then it.h = it.sub and 46 or ROW_ITEM
    else it.h = ROW end
    y = y + it.h
  end
  self.total = y
end

local function ensure_visible(self)
  local it = self.items[self.sel]
  if not it or not it.y then return end
  local margin = 6
  if it.y - margin < self.target then self.target = math.max(0, it.y - margin - ((self.items[self.sel - 1] and self.items[self.sel - 1].kind == "section") and self.items[self.sel - 1].h or 0)) end
  if it.y + it.h + margin > self.target + self.view_h then self.target = it.y + it.h + margin - self.view_h end
  self.target = U.clamp(self.target, 0, math.max(0, (self.total or 0) - self.view_h))
end

function M:update(dt)
  self.scroll = U.damp(self.scroll, self.target, 16, dt)
  if math.abs(self.scroll - self.target) < 0.3 then self.scroll = self.target else App.dirty = true end
end

function M:move(d)
  local i = self.sel + d
  while self.items[i] and not focusable(self.items[i]) do i = i + d end
  if self.items[i] then self.sel = i; ensure_visible(self); App.dirty = true; return true end
  return false
end

function M:action(act, kind)
  if kind == "release" then return false end
  local it = self.items[self.sel]
  if act == "down" then return self:move(1) or true
  elseif act == "up" then return self:move(-1)
  elseif act == "a" and it then
    if it.kind == "toggle" then it.set(not it.get()); App.dirty = true
    elseif it.on then it.on(it) end
    return true
  elseif (act == "left" or act == "right") and it and it.kind == "toggle" then
    local want = act == "right"
    if it.get() ~= want then it.set(want); App.dirty = true end
    return true
  end
  return false
end

function M:draw(x, y, w, h)
  self.view_h = h
  layout(self, w)
  ensure_visible(self)
  D.clip(x, y, w, h)
  local top = self.scroll
  for i, it in ipairs(self.items) do
    local ry = y + it.y - top
    if ry + it.h >= y and ry <= y + h then
      local foc = i == self.sel and focusable(it)
      if foc then
        D.rect(x + 4, ry + 1, w - 8, it.h - 2, c.surface, 8)
        D.outline(x + 4, ry + 1, w - 8, it.h - 2, c.white, 8, 1.5)
      end
      local k = it.kind
      if k == "section" then
        T.line(it.label or "", x + 14, ry + 8, w - 28, 11, "bold", c.secondary)
      elseif k == "note" then
        T.draw_block(it.block, x + 16, ry + 4, c.secondary)
      elseif k == "choice" then
        local vw = math.min(150, T.width(it.value or "", 12, "regular"))
        T.line(it.label or "", x + 16, ry + 9, w - 60 - vw, 13, "regular", c.text)
        T.line(it.value or "", x + w - 36 - vw, ry + 10, vw, 12, "regular", c.secondary, "right")
        D.icon("chevron_right", x + w - 28, ry + 7, 20, c.secondary)
      elseif k == "toggle" then
        T.line(it.label or "", x + 16, ry + 9, w - 80, 13, "regular", c.text)
        local on = it.get()
        local sx = x + w - 52
        D.rect(sx, ry + 9, 34, 16, on and c.red or c.surface_high, 8)
        D.circle(on and sx + 25 or sx + 9, ry + 17, 6.5, c.white)
      elseif k == "button" then
        T.line(it.label or "", x + 16, ry + 9, w - 32, 13, "medium", it.danger and c.red or c.link)
      elseif k == "info" then
        T.line(it.label or "", x + 16, ry + 9, w - 150, 13, "regular", c.text)
        T.line(it.value or "", x + w - 150, ry + 10, 134, 12, "regular", c.secondary, "right")
      elseif k == "item" then
        local tx = x + 16
        if it.avatar ~= nil then
          local img = it.avatar ~= "" and Img.get(Img.avatar_url(it.avatar, 96)) or nil
          D.avatar(img, x + 16 + 14, ry + it.h / 2, 28)
          tx = x + 54
        elseif it.icon then
          D.icon(it.icon, x + 16, ry + (it.h - 22) / 2, 22, c.text)
          tx = x + 50
        end
        if it.sub then
          T.line(it.label or "", tx, ry + 6, w - (tx - x) - 70, 13, "medium", c.text)
          T.line(it.sub, tx, ry + 25, w - (tx - x) - 70, 10, "regular", c.secondary)
        else
          T.line(it.label or "", tx, ry + (it.h - 16) / 2, w - (tx - x) - 70, 13, "regular", c.text)
        end
        if it.count and it.count ~= "" then T.line(tostring(it.count), x + w - 70, ry + (it.h - 14) / 2, 40, 12, "regular", c.secondary, "right") end
        D.icon("chevron_right", x + w - 28, ry + (it.h - 20) / 2, 20, c.secondary)
      end
    end
  end
  D.unclip()
  D.scrollbar(x + w - 3, y, h, self.scroll, self.total or 0, h)
end

return M
