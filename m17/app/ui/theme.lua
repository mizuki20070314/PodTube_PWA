-- Colors and metrics (the PWA's dark theme, scaled for 480x272)
local T = {}

local function rgb(hex, a)
  local r = tonumber(hex:sub(2, 3), 16) / 255
  local g = tonumber(hex:sub(4, 5), 16) / 255
  local b = tonumber(hex:sub(6, 7), 16) / 255
  return { r, g, b, a or 1 }
end
T.rgb = rgb

T.c = {
  bg = rgb("#0f0f0f"),
  surface = rgb("#272727"),
  surface_high = rgb("#3f3f3f"),
  text = rgb("#f1f1f1"),
  secondary = rgb("#aaaaaa"),
  divider = rgb("#303030"),
  chip_sel = rgb("#f1f1f1"),
  chip_sel_text = rgb("#0f0f0f"),
  sheet = rgb("#212121"),
  link = rgb("#3ea6ff"),
  thumb_ph = rgb("#1f1f1f"),
  red = rgb("#ff0000"),
  white = { 1, 1, 1, 1 },
  black = { 0, 0, 0, 1 },
  scrim = { 0, 0, 0, 0.6 },
  focus = rgb("#ffffff"),
  badge = { 0, 0, 0, 0.8 },
}

T.W, T.H = 480, 272
T.RAIL_W = 38
T.BAR_H = 26          -- header of a content screen
T.PAD = 8

return T
