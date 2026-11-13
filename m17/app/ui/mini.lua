-- The mini player: a bar at the bottom of every screen while something plays and the watch screen is not open (PWA: .w-mini).
local theme = require("ui.theme")
local D = require("ui.draw")
local T = require("ui.text")
local Img = require("core.img")
local Player = require("player.player")
local I = require("core.i18n")

local c = theme.c
local M = { H = 30 }

function M.visible()
  if not Player.current then return false end
  local top = App.top()
  if top and (top.name == "watch" or top.hide_mini) then return false end
  return true
end

function M.inset() return M.visible() and M.H or 0 end

local cache = {}

function M.draw()
  if not M.visible() then return end
  local x0, w = App.content_rect()
  local y = theme.H - M.H
  D.rect(x0, y, w, M.H, c.surface)
  D.rect(x0, y, w, 1, c.divider)
  local dur, pos = Player.duration(), Player.position()
  if dur > 0 then D.rect(x0, y, w * math.min(1, pos / dur), 2, c.red) end
  local v = Player.current
  local img = Img.get(Img.thumb_url(v))
  if img then D.image(img, x0 + 6, y + 5, 36, 20, 3) else D.rect(x0 + 6, y + 5, 36, 20, c.thumb_ph, 3) end
  local key = v.id .. "|" .. w
  local e = cache[key]
  if not e then
    cache = {}
    e = {
      title = T.layout(v.title or "", w - 124, { size = 11, weight = "medium", lines = 1 }),
      sub = T.layout(v.channelName or "", w - 124, { size = 9, lines = 1 }),
    }
    cache[key] = e
  end
  T.draw_block(e.title, x0 + 50, y + 3, c.text)
  T.draw_block(e.sub, x0 + 50, y + 17, c.secondary)
  local st = Player.state
  if st == "loading" or st == "buffering" then
    D.spinner(x0 + w - 56, y + 15, 7, c.text)
  else
    D.icon((st == "playing") and "pause" or "play_arrow", x0 + w - 66, y + 5, 20, c.text)
  end
  T.print("SELECT", x0 + w - 40, y + 9, 9, "medium", c.secondary)
end

return M
