-- Playlist (S.playlist in the PWA): title, owner, "play all" / "shuffle" and the videos
local theme = require("ui.theme")
local D = require("ui.draw")
local T = require("ui.text")
local NavBar = require("ui.navbar")
local Feed = require("core.feed")
local FeedList = require("ui.feedlist")
local Net = require("core.net")
local account = require("core.account")
local nav = require("core.nav")
local I = require("core.i18n")

local c = theme.c
local W, H = theme.W, theme.H

local Playlist = {}
Playlist.__index = Playlist

function Playlist.new(playlist_id, title)
  local self = setmetatable({ name = "playlist", playlist_id = playlist_id, title = title or "", meta = "", btn = 1 }, Playlist)
  local me = self
  self.feed = Feed.new({
    endpoint = "browse",
    fetch_first = function(cb, user, feed)
      local function adopt(info) me.list:invalidate(); me.title = info.title or me.title; me.meta = table.concat({ info.owner or "", table.concat(info.stats or {}, " · ") }, (info.owner and info.owner ~= "" and info.stats and #info.stats > 0) and " · " or "") end
      local function anonymous()
        feed.endpoint = "browse"
        Net.get("playlist", { id = playlist_id }, function(err, info)
          if err then cb(err); return end
          adopt(info)
          cb(nil, info.firstPage)
        end)
      end
      -- signed in: the TV client can also read private lists (Watch later, Liked videos, own playlists)
      if account.signed_in() then
        feed.endpoint = "tv"
        Net.get("acct/playlist", { id = playlist_id }, function(err, info)
          if not err and info.firstPage and #(info.firstPage.items or {}) > 0 then adopt(info); cb(nil, info.firstPage)
          else anonymous() end
        end, { auth = true })
        return
      end
      anonymous()
    end,
  })
  self.list = FeedList.new(self.feed, {
    shoulder_page = true,
    on_play = function(v) nav.play(v, { queue = self.feed:videos(), playlist_id = self:queue_id() }) end,
    on_more = function(v) nav.video_menu(v) end,
  })
  local function title_block(w) return T.layout(me.title, w - 24, { size = 14, weight = "bold", lines = 2, pitch = 18 }) end
  self.list:set_pre({ {
    h = function(row, w) return 4 + title_block(w).h + 15 + 36 end,
    draw = function(row, x, y, w, focused)
      local b = title_block(w)
      T.draw_block(b, x + 12, y + 4, c.text)
      T.line(me.meta, x + 12, y + 4 + b.h + 1, w - 24, 10, "regular", c.secondary)
      local by = y + 4 + b.h + 17
      local labels = { { "play_arrow", I.t("playlist.playAll") }, { "shuffle", I.t("playlist.shuffle") } }
      local bx = x + 12
      for i, l in ipairs(labels) do
        local bw = math.floor(T.width(l[2], 11, "medium")) + 42
        D.rect(bx, by, bw, 24, i == 1 and c.chip_sel or c.surface_high, 12)
        local fg = i == 1 and c.chip_sel_text or c.text
        D.icon(l[1], bx + 9, by + 4, 16, fg)
        T.line(l[2], bx + 29, by + 5, bw - 36, 11, "medium", fg)
        if focused and me.btn == i then D.focus_ring(bx, by, bw, 24, 12) end
        bx = bx + bw + 8
      end
    end,
    action = function(act)
      if act == "left" and me.btn > 1 then me.btn = me.btn - 1; return true end
      if act == "right" and me.btn < 2 then me.btn = me.btn + 1; return true end
      return false
    end,
    activate = function() me:play_all(me.btn == 2) end,
  } })
  self.feed:reload()
  return self
end

--- lists read through the account carry no playlist id for the player: the list itself is the queue
function Playlist:queue_id()
  return self.feed.endpoint == "tv" and nil or self.playlist_id
end

function Playlist:play_all(shuffle)
  local list = self.feed:videos()
  if #list == 0 then return end
  if shuffle then
    for i = #list, 2, -1 do
      local j = math.random(1, i)
      list[i], list[j] = list[j], list[i]
    end
  end
  nav.play(list[1], { queue = list, playlist_id = (not shuffle) and self:queue_id() or nil })
end

function Playlist:action(act, kind)
  if kind == "release" then return false end
  if self.list:action(act, kind) then return true end
  if act == "y" then App.open_search(); return true end
  return false
end

function Playlist:update(dt) self.list:update(dt) end
function Playlist:resume() App.dirty = true end

function Playlist:draw()
  NavBar.draw(self.title)
  self.list:draw(0, NavBar.H, W, H - NavBar.H - App.bottom_inset(), true)
end

return Playlist
