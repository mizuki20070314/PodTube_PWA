-- Home: topic chips + the recommendation feed (S.home in the PWA's 09a-screens.js)
local theme = require("ui.theme")
local Feed = require("core.feed")
local FeedList = require("ui.feedlist")
local Chips = require("ui.chips")
local Net = require("core.net")
local store = require("core.store")
local account = require("core.account")
local nav = require("core.nav")
local I = require("core.i18n")

local Home = {}
Home.__index = Home

local function chip_defs()
  local video = { kind = 1 }
  local live = { kind = 1, live = true }
  local week = { kind = 1, date = 3 }
  return {
    { title = I.t("chip.all") }, { title = I.t("chip.music"), filter = video }, { title = I.t("chip.gaming"), filter = video },
    { title = I.t("chip.live"), filter = live }, { title = I.t("chip.news"), filter = week }, { title = I.t("chip.anime"), filter = video },
    { title = I.t("chip.sports"), filter = video }, { title = I.t("chip.cooking"), filter = video },
    { title = I.t("chip.comedy"), filter = video }, { title = I.t("chip.tech"), filter = video },
    { title = I.t("chip.travel"), filter = video }, { title = I.t("chip.pets"), filter = video },
  }
end

function Home.new()
  local self = setmetatable({ name = "home", zone = "list" }, Home)
  self.defs = chip_defs()
  self.chips = Chips.new((function() local t = {}; for i, d in ipairs(self.defs) do t[i] = d.title end; return t end)(), 1)
  self.selected = 1
  local me = self
  self.feed = Feed.new({
    endpoint = "browse",
    fetch_first = function(cb, user_refresh, feed)
      if me.selected == 1 then
        Net.post("home", { seen = store.home_seen_ids(), fresh = user_refresh and true or false }, function(err, page)
          if page then feed.endpoint = page.endpoint or "browse" end
          cb(err, page)
        end, { auth = account.signed_in() })
      else
        local d = me.defs[me.selected]
        feed.endpoint = "search"
        local f = d.filter or {}
        Net.get("search", { q = d.title, kind = f.kind, live = f.live and 1 or nil, date = f.date }, cb)
      end
    end,
  })
  self.list = FeedList.new(self.feed, {
    on_play = function(v) nav.play(v) end,
    on_more = function(v) nav.video_menu(v) end,
    on_channel = function(ch) nav.open_channel(ch.id, ch.name) end,
    on_playlist = function(p) nav.open_playlist(p.id, p.title) end,
    on_shorts = function(list, i) nav.open_shorts(list, i) end,
    on_display = function(v) if me.selected == 1 then store.home_seen_mark(v.id) end end,
  })
  self.feed:reload()
  account.on_change = function() me.feed:clear(); me.feed:reload() end
  return self
end

function Home:scroll_top()
  self.list:reset()
  self.zone = "list"
end

function Home:resume() App.dirty = true end

function Home:select_chip(i)
  if i == self.selected then self.list:reset(); return end
  self.selected = i
  self.chips.sel = i
  self.feed:clear()
  self.list:reset()
  self.feed:reload()
end

function Home:refresh()
  self.list:reset()
  self.feed:reload(true)
  App.toast(I.t("common.loading"), 1.0)
end

function Home:action(act, kind)
  if kind == "release" then return false end
  if self.zone == "chips" then
    if act == "left" then return self.chips:move(-1) end
    if act == "right" then return self.chips:move(1) end
    if act == "down" then self.zone = "list"; App.dirty = true; return true end
    if act == "a" then self:select_chip(self.chips.focus); self.zone = "list"; App.dirty = true; return true end
    if act == "up" then return true end
    return false
  end
  if act == "start" then self:refresh(); return true end
  if self.list:action(act, kind) then return true end
  if act == "up" then self.zone = "chips"; self.chips.focus = self.chips.sel; App.dirty = true; return true end
  return false
end

function Home:update(dt)
  local x, w = App.content_rect()
  self.chips:update(dt, w - 16)
  self.list:update(dt)
end

function Home:draw()
  local x, w = App.content_rect()
  local ch = self.chips.height
  self.chips:draw(x, 0, w, App.focus == "content" and self.zone == "chips")
  self.list:draw(x, ch, w, theme.H - ch - App.bottom_inset(), App.focus == "content" and self.zone == "list")
end

return Home
