-- On-screen keyboard for a gamepad: hiragana (gojuon table), katakana, latin, symbols.  No conversion engine: the
-- candidates (YouTube's search suggestions) are shown by the caller; typing kana and picking a suggestion is the "conversion".
local theme = require("ui.theme")
local D = require("ui.draw")
local T = require("ui.text")
local U = require("lib.util")
local I = require("core.i18n")
local utf8 = require("utf8")

local c = theme.c
local K = {}
K.__index = K

---------------------------------------------------------------------------------------------------------------------
-- layouts: rows of keys; "" is an empty cell; specials start with "@"
---------------------------------------------------------------------------------------------------------------------
local function row(s) local r = {}; for ch in s:gmatch("[%z\1-\127\194-\244][\128-\191]*") do r[#r + 1] = ch end; return r end

local HIRA = {
  row("あかさたなはまやらわー。"),
  row("いきしちにひみ　り　゛？"),
  row("うくすつぬふむゆる　゜！"),
  row("えけせてねへめ　れ　小・"),
  row("おこそとのほもよろを、〜"),
}
local KATA = {
  row("アカサタナハマヤラワー。"),
  row("イキシチニヒミ　リ　゛？"),
  row("ウクスツヌフムユル　゜！"),
  row("エケセテネヘメ　レ　小・"),
  row("オコソトノホモヨロヲ、〜"),
}
local LATIN = {
  row("qwertyuiop-_"),
  row("asdfghjkl'\"@"),
  row("zxcvbnm,./?!"),
  row("1234567890+="),
}
local SYMBOLS = {
  row("!?.,:;'\"()[]"),
  row("@#$%^&*-_+=~"),
  row("/\\|<>{}`・「」"),
  row("『』○×☆♪→←↑↓…"),
}
K.MODES = { "hira", "kata", "latin", "sym" }
local GRID = { hira = HIRA, kata = KATA, latin = LATIN, sym = SYMBOLS }

-- dakuten / handakuten / small
local DAKU = {}
local function pairs_of(a, b)
  local ia, ib = row(a), row(b)
  for i = 1, #ia do DAKU[ia[i]] = ib[i] end
end
pairs_of("かきくけこさしすせそたちつてとはひふへほ", "がぎぐげござじずぜぞだぢづでどばびぶべぼ")
pairs_of("カキクケコサシスセソタチツテトハヒフヘホ", "ガギグゲゴザジズゼゾダヂヅデドバビブベボ")
pairs_of("がぎぐげござじずぜぞだぢづでどばびぶべぼ", "かきくけこさしすせそたちつてとはひふへほ")
pairs_of("ガギグゲゴザジズゼゾダヂヅデドバビブベボ", "カキクケコサシスセソタチツテトハヒフヘホ")
local HANDA = {}
do
  local a, b = row("はひふへほハヒフヘホ"), row("ぱぴぷぺぽパピプペポ")
  for i = 1, #a do HANDA[a[i]] = b[i] end
  local rev_a, rev_b = row("ぱぴぷぺぽパピプペポ"), row("はひふへほハヒフヘホ")
  for i = 1, #rev_a do HANDA[rev_a[i]] = rev_b[i] end
end
local SMALL = {}
do
  local a, b = row("あいうえおつやゆよわアイウエオツヤユヨワ"), row("ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮ")
  for i = 1, #a do SMALL[a[i]] = b[i]; SMALL[b[i]] = a[i] end
end

---------------------------------------------------------------------------------------------------------------------
-- construction
---------------------------------------------------------------------------------------------------------------------
--- opts: text, on_submit(text), on_cancel(), on_change(text), submit_label, mode, password
function K.new(opts)
  local k = setmetatable({}, K)
  k.o = opts or {}
  k.text = opts.text or ""
  k.mode = opts.mode or "hira"
  k.shift = false
  k.r, k.col = 1, 1
  k.bar = 0               -- 0: key grid, 1..: function row buttons
  k.in_bar = false
  k.bar_sel = 5
  k.submit_label = opts.submit_label or I.t("kb.search")
  return k
end

local BAR = { "hira", "kata", "latin", "sym", "space", "back", "submit" }
local BAR_W = { 56, 56, 56, 56, 104, 56, 76 }

function K:set_text(s) self.text = s; if self.o.on_change then self.o.on_change(s) end end

function K:append(s)
  self:set_text(self.text .. s)
end

function K:backspace()
  self:set_text(U.ubackspace(self.text))
end

function K:grid() return GRID[self.mode] end

local function cell(self, r, c_)
  local g = self:grid()
  local rowt = g[r]
  if not rowt then return nil end
  local ch = rowt[c_]
  if ch == nil or ch == "　" then return nil end
  if self.mode == "latin" and self.shift then ch = ch:upper() end
  return ch
end

--- puts a character in, applying the dakuten / handakuten / small-letter keys to the previous one
function K:press_char(ch)
  if ch == "゛" or ch == "゜" or ch == "小" then
    local last = U.ubackspace(self.text)
    local prev = self.text:sub(#last + 1)
    if prev == "" then return end
    local map = ch == "゛" and DAKU or (ch == "゜" and HANDA or SMALL)
    local repl = map[prev]
    if repl then self:set_text(last .. repl) end
    return
  end
  self:append(ch)
end

function K:set_mode(m)
  self.mode = m
  self.shift = false
  -- keep the cursor inside the new grid
  local g = self:grid()
  self.r = math.min(self.r, #g)
  self.col = math.min(self.col, #g[1])
  App.dirty = true
end

function K:cycle_mode(d)
  local i = 1
  for n, m in ipairs(K.MODES) do if m == self.mode then i = n end end
  self:set_mode(K.MODES[(i - 1 + (d or 1)) % #K.MODES + 1])
end

function K:press_bar(i)
  local b = BAR[i]
  if b == "space" then self:append(" ")
  elseif b == "back" then self:backspace()
  elseif b == "submit" then if self.o.on_submit then self.o.on_submit(self.text) end
  else self:set_mode(b) end
end

---------------------------------------------------------------------------------------------------------------------
-- input
---------------------------------------------------------------------------------------------------------------------
local function move_in_grid(self, dr, dc)
  local g = self:grid()
  local r, col = self.r, self.col
  local nr, nc = r + dr, col + dc
  if dr ~= 0 then
    if nr < 1 then return "top" end
    if nr > #g then return "bottom" end
    -- keep the column; skip empty cells by looking sideways
    for off = 0, #g[1] do
      for _, s in ipairs({ 1, -1 }) do
        local cc = col + off * s
        if cc >= 1 and cc <= #g[1] and cell(self, nr, cc) then self.r, self.col = nr, cc; return "ok" end
      end
    end
    return "ok"
  end
  while nc >= 1 and nc <= #g[1] do
    if cell(self, r, nc) then self.col = nc; return "ok" end
    nc = nc + dc
  end
  return "edge"
end

--- returns "up_out" when the cursor leaves the keyboard upwards (the caller may focus its candidate list)
function K:action(act, kind)
  if kind == "release" then return false end
  if self.in_bar then
    if act == "left" then self.bar_sel = math.max(1, self.bar_sel - 1)
    elseif act == "right" then self.bar_sel = math.min(#BAR, self.bar_sel + 1)
    elseif act == "up" then self.in_bar = false
    elseif act == "a" then self:press_bar(self.bar_sel) end
    App.dirty = true
    return true
  end
  if act == "left" or act == "right" then
    local g = self:grid()
    local r = move_in_grid(self, 0, act == "left" and -1 or 1)
    if r == "edge" then
      -- wrap around the row
      local start = act == "left" and #g[1] or 1
      local step = act == "left" and -1 or 1
      for cc = start, act == "left" and 1 or #g[1], step do
        if cell(self, self.r, cc) then self.col = cc; break end
      end
    end
  elseif act == "up" then
    local r = move_in_grid(self, -1, 0)
    if r == "top" then return "up_out" end
  elseif act == "down" then
    local r = move_in_grid(self, 1, 0)
    if r == "bottom" then self.in_bar = true end
  elseif act == "a" then
    local ch = cell(self, self.r, self.col)
    if ch then self:press_char(ch) end
  elseif act == "b" then
    if self.text == "" then if self.o.on_cancel then self.o.on_cancel() end else self:backspace() end
  elseif act == "x" then self:append(" ")
  elseif act == "y" then self:cycle_mode(1)
  elseif act == "l" then self:cycle_mode(-1)
  elseif act == "r" then self:cycle_mode(1)
  elseif act == "select" then
    if self.mode == "latin" then self.shift = not self.shift end
  elseif act == "start" then
    if self.o.on_submit then self.o.on_submit(self.text) end
  else
    return false
  end
  App.dirty = true
  return true
end

---------------------------------------------------------------------------------------------------------------------
-- drawing
---------------------------------------------------------------------------------------------------------------------
local MODE_LABEL = { hira = "かな", kata = "カナ", latin = "ABC", sym = "記号" }

--- draws the keys in x,y,w,h (h should be about 156)
function K:draw(x, y, w, h, focused)
  local g = self:grid()
  local cols = #g[1]
  local rows = #g
  local pad = 6
  local kw = (w - pad * 2) / cols
  local barh = 24
  local kh = math.min(26, (h - barh - 4) / rows)
  for r = 1, rows do
    for col = 1, cols do
      local ch = cell(self, r, col)
      if ch then
        local kx, ky = x + pad + (col - 1) * kw, y + (r - 1) * (kh + 1)
        local sel = focused and not self.in_bar and r == self.r and col == self.col
        D.rect(kx + 1, ky, kw - 2, kh - 1, sel and c.chip_sel or c.surface, 5)
        local fg = sel and c.chip_sel_text or c.text
        local label = ch
        local lw = T.width(label, 15, "medium")
        T.print(label, kx + (kw - lw) / 2, ky + (kh - 20) / 2 + 1, 15, "medium", fg)
      end
    end
  end
  -- the function row
  local by = y + rows * (kh + 1) + 3
  local bx = x + pad
  local total = 0
  for _, bw in ipairs(BAR_W) do total = total + bw end
  local scale = (w - pad * 2) / total
  for i, b in ipairs(BAR) do
    local bw = BAR_W[i] * scale
    local sel = focused and self.in_bar and self.bar_sel == i
    local active = (b == self.mode)
    D.rect(bx + 1, by, bw - 2, barh - 2, sel and c.chip_sel or (active and c.surface_high or c.surface), 5)
    local fg = sel and c.chip_sel_text or c.text
    local label
    if MODE_LABEL[b] then label = MODE_LABEL[b]
    elseif b == "space" then label = "␣"
    elseif b == "back" then label = "⌫"
    else label = self.submit_label end
    local lw = T.width(label, 12, "medium")
    if b == "back" then D.icon("close", bx + bw / 2 - 8, by + 3, 16, fg)
    elseif b == "space" then
      D.rect(bx + bw / 2 - 18, by + barh - 9, 36, 2, fg, 1)
    else
      T.print(label, bx + (bw - lw) / 2, by + 3, 12, "medium", fg)
    end
    if b == self.mode then D.rect(bx + bw / 2 - 6, by + barh - 5, 12, 2, c.red, 1) end
    bx = bx + bw
  end
  if self.shift and self.mode == "latin" then T.print("⇧", x + w - 18, y - 12, 12, "bold", c.red) end
end

return K
