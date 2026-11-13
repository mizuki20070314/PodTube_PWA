-- Text: fonts, cleaning (glyphs the font lacks), wrapping with an ellipsis, cached Text objects.
local U = require("lib.util")
local utf8 = require("utf8")

local T = {}

local FILES = { regular = "fonts/NotoSansJP-Regular.ttf", medium = "fonts/NotoSansJP-Medium.ttf", bold = "fonts/NotoSansJP-Bold.ttf" }
local filedata = {}
local fonts = {}
local HINTING = "normal"

function T.set_hinting(h) HINTING = h; fonts = {} end

local function data(weight)
  local d = filedata[weight]
  if not d then
    d = love.filesystem.newFileData(FILES[weight] or FILES.regular)
    filedata[weight] = d
  end
  return d
end

--- font of a pixel size and weight ("regular" | "medium" | "bold")
function T.font(size, weight)
  weight = weight or "regular"
  local key = weight .. size
  local f = fonts[key]
  if not f then
    f = love.graphics.newFont(data(weight), size, HINTING)
    f:setFilter("linear", "linear")
    fonts[key] = f
  end
  return f
end

local ref_font
local glyph_ok = {}

local function has_glyph(cp)
  local r = glyph_ok[cp]
  if r == nil then
    ref_font = ref_font or T.font(12, "regular")
    r = ref_font:hasGlyphs(utf8.char(cp))
    glyph_ok[cp] = r
  end
  return r
end

local cleaned = setmetatable({}, { __mode = "k" })
local cleaned_n = 0

--- Single line, printable text: control characters become spaces and glyphs the font lacks (emoji ...) are dropped.
function T.clean(s)
  if s == nil then return "" end
  s = tostring(s)
  local c = cleaned[s]
  if c then return c end
  local out = {}
  local ok = pcall(function()
    for _, cp in utf8.codes(s) do
      if cp == 10 or cp == 13 or cp == 9 or cp == 0xA0 then out[#out + 1] = " "
      elseif cp < 32 or cp == 0x200B or cp == 0x200D or cp == 0xFE0F or (cp >= 0x200E and cp <= 0x200F) or cp == 0xFEFF then -- skip
      elseif has_glyph(cp) then out[#out + 1] = utf8.char(cp)
      end
    end
  end)
  if not ok then c = s:gsub("[%c]", " ") else c = table.concat(out) end
  c = c:gsub("%s+", " ")
  cleaned_n = cleaned_n + 1
  if cleaned_n > 4000 then cleaned = setmetatable({}, { __mode = "k" }); cleaned_n = 0 end
  cleaned[s] = c
  return c
end

--- like clean, but keeps line breaks (descriptions, comments)
function T.clean_multiline(s)
  if s == nil then return "" end
  s = tostring(s):gsub("\r\n?", "\n")
  local lines = {}
  for line in (s .. "\n"):gmatch("(.-)\n") do lines[#lines + 1] = T.clean(line) end
  return table.concat(lines, "\n")
end

function T.width(s, size, weight)
  return T.font(size, weight):getWidth(s)
end

--- shortens one line to `w` pixels with an ellipsis
function T.ellipsize(s, w, size, weight)
  local f = T.font(size, weight)
  if f:getWidth(s) <= w then return s end
  local ell = "…"
  if not has_glyph(0x2026) then ell = "..." end
  local n = U.ulen(s)
  -- binary search on the character count
  local lo, hi = 0, n
  while lo < hi do
    local mid = math.ceil((lo + hi) / 2)
    if f:getWidth(U.usub_head(s, mid) .. ell) <= w then lo = mid else hi = mid - 1 end
  end
  return U.usub_head(s, lo) .. ell
end

local blocks = {}
local nblocks = 0

--- Lays a text out once.  Returns a block {lines, h, w, text(Text object)} to draw with T.draw_block.
--- opts: size, weight, lines (max, default 1), pitch (line pitch), multiline (keep \n), nowrap
function T.layout(s, w, opts)
  opts = opts or {}
  local size, weight = opts.size or 12, opts.weight or "regular"
  local maxl = opts.lines or 1
  local pitch = opts.pitch or math.floor(size * 1.32 + 0.5)
  local key = table.concat({ size, weight, math.floor(w), maxl, pitch, opts.multiline and 1 or 0, s }, "|")
  local b = blocks[key]
  if b then return b end
  local f = T.font(size, weight)
  local text = opts.multiline and T.clean_multiline(s) or T.clean(s)
  local lines = {}
  local more = false
  if text ~= "" then
    local _, wrapped = f:getWrap(text, w)
    for i, l in ipairs(wrapped) do
      if i > maxl then more = true; break end
      lines[#lines + 1] = l
    end
  end
  if more and #lines > 0 then
    lines[#lines] = T.ellipsize(lines[#lines] .. "…", w, size, weight)
  end
  local tobj = love.graphics.newText(f)
  local maxw = 0
  for i, l in ipairs(lines) do
    tobj:add(l, 0, (i - 1) * pitch)
    local lw = f:getWidth(l)
    if lw > maxw then maxw = lw end
  end
  b = { lines = lines, text = tobj, w = maxw, h = #lines * pitch, pitch = pitch, size = size, more = more }
  nblocks = nblocks + 1
  if nblocks > 1500 then blocks = {}; nblocks = 0 end
  blocks[key] = b
  return b
end

function T.draw_block(b, x, y, color)
  if #b.lines == 0 then return end
  if color then love.graphics.setColor(color[1], color[2], color[3], color[4] or 1) end
  love.graphics.draw(b.text, x, y)
end

--- single-line helper (cached through layout): draws `s` at x,y, clipped to w with an ellipsis
function T.line(s, x, y, w, size, weight, color, align)
  local b = T.layout(s, w or 4000, { size = size, weight = weight, lines = 1 })
  local dx = 0
  if align == "center" then dx = (w - b.w) / 2 elseif align == "right" then dx = w - b.w end
  T.draw_block(b, x + dx, y, color)
  return b.w
end

--- uncached print for text that changes every frame (clock, counters)
function T.print(s, x, y, size, weight, color)
  love.graphics.setFont(T.font(size, weight))
  if color then love.graphics.setColor(color[1], color[2], color[3], color[4] or 1) end
  love.graphics.print(s, x, y)
end

return T
