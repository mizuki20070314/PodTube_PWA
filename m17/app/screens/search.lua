-- Search: a text field with the on-screen keyboard, history while the field is empty and YouTube's suggestions as you type
-- (typing kana and picking a suggestion is how Japanese gets "converted" here).
local theme = require("ui.theme")
local D = require("ui.draw")
local T = require("ui.text")
local Keyboard = require("ui.keyboard")
local Net = require("core.net")
local store = require("core.store")
local nav = require("core.nav")
local I = require("core.i18n")
local U = require("lib.util")
local utf8 = require("utf8")

local c = theme.c
local W, H = theme.W, theme.H

local Search = {}
Search.__index = Search

local KB_H = 156
local SUG_ROW = 23

function Search.new(prefill)
  local self = setmetatable({ name = "search", zone = "kb", sug = {}, sug_sel = 1, sug_top = 1, hide_mini = true }, Search)
  self.timer = nil
  self.query = ""
  self.kb = Keyboard.new({
    text = prefill or "", mode = "hira", submit_label = I.t("kb.search"),
    on_change = function(t) self:changed(t) end,
    on_submit = function(t) self:submit(t) end,
    on_cancel = function() App.pop() end,
  })
  self.prefill = prefill
  return self
end

function Search:enter()
  if self.prefill and self.prefill ~= "" then self:fetch(self.prefill) end
end

function Search:changed(text)
  self.sug_sel, self.sug_top = 1, 1
  local q = U.trim(text)
  if q == "" then self.sug = {}; self.timer = nil; App.dirty = true; return end
  self.timer = love.timer.getTime() + 0.2
  self.pending_q = q
end

function Search:fetch(q)
  Net.get("suggest", { q = q }, function(err, r)
    if err or U.trim(self.kb.text) ~= q then return end
    self.sug = r.suggestions or {}
    App.dirty = true
  end)
end

function Search:update(dt)
  if self.timer and love.timer.getTime() >= self.timer then
    self.timer = nil
    self:fetch(self.pending_q)
  end
end

function Search:rows()
  if U.trim(self.kb.text) == "" then return store.searches(), true end
  return self.sug, false
end

function Search:submit(text)
  local t = U.trim(text or "")
  if t == "" then return end
  App.pop()
  if nav.open_text(t) then return end
  nav.open_search_results(t)
end

function Search:type_text(s)
  self.kb:append(s)
  self.zone = "kb"
end

function Search:action(act, kind)
  if kind == "release" then return false end
  local rows, is_history = self:rows()
  if self.zone == "sug" then
    local n = #rows
    if act == "down" then
      if self.sug_sel < n then self.sug_sel = self.sug_sel + 1 else self.zone = "kb" end
    elseif act == "up" then
      if self.sug_sel > 1 then self.sug_sel = self.sug_sel - 1 end
    elseif act == "a" then
      if rows[self.sug_sel] then self:submit(rows[self.sug_sel]) end
    elseif act == "x" then
      local s = rows[self.sug_sel]
      if s then
        if is_history then store.remove_search(s)
        else self.kb:set_text(s .. " "); self.zone = "kb" end
      end
    elseif act == "b" then self.zone = "kb"
    elseif act == "start" then self:submit(self.kb.text)
    else return false end
    if self.sug_sel < self.sug_top then self.sug_top = self.sug_sel end
    if self.sug_sel > self.sug_top + 2 then self.sug_top = self.sug_sel - 2 end
    App.dirty = true
    return true
  end
  local r = self.kb:action(act, kind)
  if r == "up_out" then
    if #rows > 0 then self.zone = "sug"; self.sug_sel = 1; self.sug_top = 1 end
    App.dirty = true
    return true
  end
  if r then return true end
  if act == "left" then return true end
  return false
end

function Search:draw()
  D.rect(0, 0, W, H, c.bg)
  -- the text field
  D.rect(6, 4, W - 12, 28, c.surface, 14)
  D.icon("search", 14, 9, 18, c.secondary)
  local text = self.kb.text
  local fw = W - 12 - 50
  if text == "" then
    T.line(I.t("search.placeholder"), 40, 9, fw, 14, "regular", c.secondary)
  else
    local shown = text
    local tw = T.width(shown, 14, "medium")
    while tw > fw - 6 and #shown > 1 do shown = shown:sub(utf8.offset(shown, 2)); tw = T.width(shown, 14, "medium") end
    T.print(shown, 40, 8, 14, "medium", c.text)
    if math.floor(love.timer.getTime() * 2) % 2 == 0 then D.rect(40 + tw + 1, 9, 2, 16, c.text) end
    App.dirty = true
  end
  -- candidates
  local rows, is_history = self:rows()
  local y0 = 36
  for i = 0, 2 do
    local idx = self.sug_top + i
    local s = rows[idx]
    if s then
      local y = y0 + i * SUG_ROW
      local sel = self.zone == "sug" and idx == self.sug_sel
      if sel then
        D.rect(6, y, W - 12, SUG_ROW - 1, c.surface_high, 6)
        D.outline(6, y, W - 12, SUG_ROW - 1, c.white, 6, 1.5)
      end
      D.icon(is_history and "history" or "search", 12, y + 3, 16, c.secondary)
      T.line(s, 36, y + 4, W - 36 - 40, 13, "regular", c.text)
      D.icon(is_history and "close" or "north_west", W - 30, y + 3, 16, c.secondary)
    end
  end
  if #rows > 3 then
    D.rect(W - 4, y0, 2, SUG_ROW * 3, c.surface)
    local th = SUG_ROW * 3 * 3 / #rows
    D.rect(W - 4, y0 + (SUG_ROW * 3 - th) * (self.sug_top - 1) / math.max(1, #rows - 3), 2, th, c.secondary)
  end
  if #rows == 0 and text == "" then
    -- nothing typed, no history: a short hint
    T.line("Ⓨ " .. I.t("kb.hintMode") .. "   Ⓧ " .. I.t("kb.hintSpace") .. "   Ⓑ " .. I.t("kb.hintDelete"), 8, 50, W - 16, 11, "regular", c.secondary, "center")
  end
  self.kb:draw(0, H - KB_H - 4, W, KB_H, self.zone == "kb")
end

return Search
