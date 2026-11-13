-- Drawing primitives: rounded rectangles, icons (PNG atlases made from the PWA's Material icons), rounded images, bars.
local theme = require("ui.theme")
local icons_index = require("data.icons")

local D = {}
local g = love.graphics

local function setc(c, a)
  g.setColor(c[1], c[2], c[3], (c[4] or 1) * (a or 1))
end
D.setc = setc

---------------------------------------------------------------------------------------------------------------------
-- shapes
---------------------------------------------------------------------------------------------------------------------
function D.rect(x, y, w, h, color, r, alpha)
  setc(color, alpha)
  if r and r > 0 then g.rectangle("fill", x, y, w, h, r, r, 8) else g.rectangle("fill", x, y, w, h) end
end

function D.outline(x, y, w, h, color, r, lw, alpha)
  setc(color, alpha)
  g.setLineWidth(lw or 1)
  if r and r > 0 then g.rectangle("line", x, y, w, h, r, r, 8) else g.rectangle("line", x, y, w, h) end
end

--- focus ring around a pill / button: kept 3px away so that it shows on white buttons too
function D.focus_ring(x, y, w, h, r)
  D.outline(x - 3, y - 3, w + 6, h + 6, theme.c.white, (r or h / 2) + 3, 2)
end

function D.line(x1, y1, x2, y2, color, lw, alpha)
  setc(color, alpha)
  g.setLineWidth(lw or 1)
  g.line(x1, y1, x2, y2)
end

function D.circle(cx, cy, r, color, alpha)
  setc(color, alpha)
  g.circle("fill", cx, cy, r, 24)
end

---------------------------------------------------------------------------------------------------------------------
-- icons
---------------------------------------------------------------------------------------------------------------------
local atlases = {}
local quads = {}

local function atlas(size)
  local a = atlases[size]
  if not a then
    local img = g.newImage("data/icons_" .. size .. ".png")
    img:setFilter("linear", "linear")
    a = { img = img, w = img:getWidth(), h = img:getHeight() }
    atlases[size] = a
  end
  return a
end

local function pick_size(want)
  local best = icons_index.sizes[1]
  for _, s in ipairs(icons_index.sizes) do
    best = s
    if s >= want then break end
  end
  return best
end

--- Draws a Material icon at x,y (top-left) with the given pixel size.
function D.icon(name, x, y, size, color, alpha)
  local idx = icons_index.names[name]
  if not idx then return end
  local s = pick_size(size)
  local a = atlas(s)
  local key = s * 1000 + idx
  local q = quads[key]
  if not q then
    local cols = icons_index.cols
    q = g.newQuad((idx % cols) * s, math.floor(idx / cols) * s, s, s, a.w, a.h)
    quads[key] = q
  end
  setc(color or theme.c.text, alpha)
  local sc = size / s
  g.draw(a.img, q, x, y, 0, sc, sc)
end

function D.has_icon(name) return icons_index.names[name] ~= nil end

---------------------------------------------------------------------------------------------------------------------
-- images with rounded corners / circles
---------------------------------------------------------------------------------------------------------------------
local round_shader

local function get_round_shader()
  if not round_shader then
    round_shader = g.newShader [[
      uniform vec2 sz;
      uniform float rad;
      vec4 effect(vec4 color, Image tex, vec2 uv, vec2 sc) {
        vec2 p = uv * sz;
        vec2 q = abs(p - sz * 0.5) - (sz * 0.5 - vec2(rad));
        float d = length(max(q, vec2(0.0))) + min(max(q.x, q.y), 0.0) - rad;
        float a = clamp(0.5 - d, 0.0, 1.0);
        return Texel(tex, uv) * color * vec4(1.0, 1.0, 1.0, a);
      }
    ]]
  end
  return round_shader
end

--- image scaled into x,y,w,h (stretched; thumbnails are 16:9 already); r = corner radius
function D.image(img, x, y, w, h, r, alpha)
  local iw, ih = img:getDimensions()
  g.setColor(1, 1, 1, alpha or 1)
  if r and r > 0 then
    local sh = get_round_shader()
    g.setShader(sh)
    sh:send("sz", { w, h })
    sh:send("rad", r)
    g.draw(img, x, y, 0, w / iw, h / ih)
    g.setShader()
  else
    g.draw(img, x, y, 0, w / iw, h / ih)
  end
end

--- like image but cropped to fill (cover) the box
function D.image_cover(img, x, y, w, h, r, alpha)
  local iw, ih = img:getDimensions()
  local s = math.max(w / iw, h / ih)
  local sw, sh_ = iw * s, ih * s
  local ox, oy = (sw - w) / 2, (sh_ - h) / 2
  g.setScissor(x, y, w, h)
  g.setColor(1, 1, 1, alpha or 1)
  g.draw(img, x - ox, y - oy, 0, s, s)
  g.setScissor()
end

function D.avatar(img, cx, cy, d, alpha)
  if img then
    D.image(img, cx - d / 2, cy - d / 2, d, d, d / 2, alpha)
  else
    D.circle(cx, cy, d / 2, theme.c.surface_high, alpha)
  end
end

---------------------------------------------------------------------------------------------------------------------
-- spinner
---------------------------------------------------------------------------------------------------------------------
function D.spinner(cx, cy, r, color, alpha)
  local t = love.timer.getTime()
  setc(color or theme.c.secondary, alpha)
  g.setLineWidth(2)
  local a0 = t * 6
  g.arc("line", "open", cx, cy, r, a0, a0 + 4.2, 20)
  if App then App.dirty = true end
end

---------------------------------------------------------------------------------------------------------------------
-- clipping
---------------------------------------------------------------------------------------------------------------------
local clip_stack = {}

--- push a clip rectangle (intersects with the current one)
function D.clip(x, y, w, h)
  local cur = clip_stack[#clip_stack]
  local nx, ny, nw, nh = x, y, w, h
  if cur then
    local x2, y2 = math.min(cur[1] + cur[3], x + w), math.min(cur[2] + cur[4], y + h)
    nx, ny = math.max(cur[1], x), math.max(cur[2], y)
    nw, nh = math.max(0, x2 - nx), math.max(0, y2 - ny)
  end
  clip_stack[#clip_stack + 1] = { nx, ny, nw, nh }
  g.setScissor(nx, ny, nw, nh)
end

function D.unclip()
  clip_stack[#clip_stack] = nil
  local cur = clip_stack[#clip_stack]
  if cur then g.setScissor(cur[1], cur[2], cur[3], cur[4]) else g.setScissor() end
end

---------------------------------------------------------------------------------------------------------------------
-- bars
---------------------------------------------------------------------------------------------------------------------
function D.progress(x, y, w, h, frac, fg, bg, r)
  frac = math.max(0, math.min(1, frac or 0))
  D.rect(x, y, w, h, bg or theme.c.surface_high, r)
  if frac > 0 then D.rect(x, y, math.max(h, w * frac), h, fg or theme.c.red, r) end
end

--- vertical scroll indicator on the right side of a list
function D.scrollbar(x, y, h, offset, content, view)
  if content <= view then return end
  local th = math.max(14, h * view / content)
  local ty = y + (h - th) * (offset / (content - view))
  D.rect(x, y, 2, h, theme.c.surface, 1)
  D.rect(x, ty, 2, th, theme.c.secondary, 1)
end

return D
