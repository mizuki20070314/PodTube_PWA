-- Downloads: the videos saved on this device (S.downloads in the PWA); they play without a network
local theme = require("ui.theme")
local D = require("ui.draw")
local T = require("ui.text")
local NavBar = require("ui.navbar")
local Feed = require("core.feed")
local FeedList = require("ui.feedlist")
local Downloads = require("core.downloads")
local store = require("core.store")
local nav = require("core.nav")
local I = require("core.i18n")
local U = require("lib.util")

local c = theme.c
local W, H = theme.W, theme.H

local Screen = {}
Screen.__index = Screen

local function size_text(n)
  if n >= 1048576 * 1024 then return string.format("%.1f GB", n / 1073741824) end
  if n >= 1048576 then return string.format("%.1f MB", n / 1048576) end
  return string.format("%d KB", math.floor(n / 1024))
end
Screen.size_text = size_text

function Screen.new()
  local self = setmetatable({ name = "downloads", title = I.t("library.downloads") }, Screen)
  self.feed = Feed.new({ endpoint = "browse", fetch_first = function(cb) cb(nil, { items = {} }) end })
  self.list = FeedList.new(self.feed, {
    shoulder_page = true, empty_text = I.t("downloads.empty"), empty_icon = "cloud_download",
    on_play = function(v) if not Downloads.is_downloading(v.id) then nav.play(v) end end,
    on_more = function(v) self:menu(v) end,
  })
  self.cb = store.on_change(function() self:rebuild() end)
  self:rebuild()
  return self
end

function Screen:leave() store.off_change(self.cb) end

function Screen:menu(v)
  local rec = Downloads.record(v.id)
  local items = {}
  if Downloads.is_downloading(v.id) then
    items[1] = { label = I.t("common.cancel"), icon = "close", danger = true, on = function() Downloads.cancel(v.id) end }
  elseif rec then
    items[1] = { label = I.t("common.delete"), sub = size_text(rec.bytes or 0), icon = "delete", danger = true, on = function() Downloads.remove(v.id) end }
  end
  if #items > 0 then App.open_sheet({ title = v.title, items = items }) end
end

function Screen:rebuild()
  local items = {}
  -- the one that is coming first
  for _, r in ipairs(Downloads.records()) do
    local v = U.copy(r.video)
    v.views = size_text(r.bytes or 0) .. " · " .. (r.height or 0) .. "p"
    v.published = ""
    items[#items + 1] = { type = "video", video = v }
  end
  self.feed:set_page({ items = items })
  self.feed.state = #items > 0 and "ready" or "empty"
end

function Screen:action(act, kind)
  if kind == "release" then return false end
  return self.list:action(act, kind)
end

function Screen:update(dt)
  self.list:update(dt)
  if Downloads.pending_count() > 0 then App.dirty = true end
end

function Screen:resume() self:rebuild(); App.dirty = true end

function Screen:draw()
  NavBar.draw(self.title, size_text(Downloads.total_bytes()))
  local y0 = NavBar.H
  local pend = Downloads.pending_count()
  if pend > 0 then
    D.rect(0, y0, W, 18, c.surface)
    D.spinner(14, y0 + 9, 5, c.secondary)
    T.line(I.t("downloads.started") .. " (" .. pend .. ")", 28, y0 + 3, W - 40, 11, "regular", c.text)
    y0 = y0 + 18
  end
  self.list:draw(0, y0, W, H - y0 - App.bottom_inset(), true)
end

return Screen
