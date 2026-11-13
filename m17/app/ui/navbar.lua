-- The bar of a pushed screen: back arrow, title, optional hint on the right
local theme = require("ui.theme")
local D = require("ui.draw")
local T = require("ui.text")

local c = theme.c
local N = { H = 26 }

function N.draw(title, right)
  D.rect(0, 0, theme.W, N.H, c.bg)
  D.rect(0, N.H - 1, theme.W, 1, c.divider)
  D.icon("arrow_back", 5, 3, 20, c.text)
  local rw = 0
  if right and right ~= "" then
    rw = T.width(right, 10, "regular") + 14
    T.line(right, theme.W - rw, 7, rw - 8, 10, "regular", c.secondary, "right")
  end
  T.line(title or "", 32, 5, theme.W - 40 - rw, 14, "bold", c.text)
end

return N
