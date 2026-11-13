-- Search results with the filter sheets (S.searchResults in the PWA)
local theme = require("ui.theme")
local D = require("ui.draw")
local T = require("ui.text")
local Feed = require("core.feed")
local FeedList = require("ui.feedlist")
local Net = require("core.net")
local nav = require("core.nav")
local I = require("core.i18n")

local c = theme.c
local W, H = theme.W, theme.H
local BAR = 26

local Results = {}
Results.__index = Results

local function default_filter() return { sort = 0, date = 0, kind = 0, duration = 0, live = false, hd = false, subtitles = false, fourK = false } end

function Results.new(query)
  local self = setmetatable({ name = "results", query = query, filter = default_filter() }, Results)
  local me = self
  self.feed = Feed.new({
    endpoint = "search",
    fetch_first = function(cb, user, feed)
      feed.endpoint = "search"
      local f = me.filter
      Net.get("search", {
        q = query, sort = f.sort, date = f.date, kind = f.kind, dur = f.duration,
        live = f.live and 1 or nil, hd = f.hd and 1 or nil, cc = f.subtitles and 1 or nil, ["4k"] = f.fourK and 1 or nil,
      }, cb)
    end,
  })
  self.list = FeedList.new(self.feed, {
    shoulder_page = true,
    on_play = function(v) nav.play(v) end,
    on_more = function(v) nav.video_menu(v) end,
    on_channel = function(ch) nav.open_channel(ch.id, ch.name) end,
    on_playlist = function(p) nav.open_playlist(p.id, p.title) end,
    on_shorts = function(list, i) nav.open_shorts(list, i) end,
  })
  self.feed:reload()
  return self
end

function Results:is_default()
  local f = self.filter
  return f.sort == 0 and f.date == 0 and f.kind == 0 and f.duration == 0 and not f.live and not f.hd and not f.subtitles and not f.fourK
end

function Results:apply()
  self.feed:clear()
  self.list:reset()
  self.feed:reload()
end

function Results:show_filters()
  local names = {
    sort = { I.t("search.relevance"), I.t("search.ratingSort"), I.t("search.dateSort"), I.t("search.viewSort") },
    date = { I.t("search.any"), I.t("search.hour"), I.t("search.today"), I.t("search.week"), I.t("search.month"), I.t("search.year") },
    kind = { I.t("search.any"), I.t("search.video"), I.t("search.channel"), I.t("search.playlist"), I.t("search.movie") },
    duration = { I.t("search.any"), I.t("search.short"), I.t("search.long"), I.t("search.medium") },
  }
  local function pick(title, key, order)
    local items = {}
    for _, val in ipairs(order) do
      items[#items + 1] = { label = names[key][val + 1], checked = self.filter[key] == val, on = function() self.filter[key] = val; self:apply() end }
    end
    App.open_sheet({ title = title, items = items })
  end
  local f = self.filter
  App.open_sheet({ title = I.t("search.filters"), items = {
    { label = I.t("search.sort"), icon = "swap_vert", sub = names.sort[f.sort + 1], on = function() pick(I.t("search.sort"), "sort", { 0, 2, 3, 1 }) end },
    { label = I.t("search.uploadDate"), icon = "schedule", sub = names.date[f.date + 1], on = function() pick(I.t("search.uploadDate"), "date", { 0, 1, 2, 3, 4, 5 }) end },
    { label = I.t("search.type"), icon = "video_library", sub = names.kind[f.kind + 1], on = function() pick(I.t("search.type"), "kind", { 0, 1, 2, 3, 4 }) end },
    { label = I.t("search.duration"), icon = "timer", sub = names.duration[f.duration + 1], on = function() pick(I.t("search.duration"), "duration", { 0, 1, 3, 2 }) end },
    { label = I.t("search.reset"), icon = "refresh", on = function() self.filter = default_filter(); self:apply() end },
  } })
end

function Results:action(act, kind)
  if kind == "release" then return false end
  if self.list:action(act, kind) then return true end
  if act == "x" then self:show_filters(); return true end
  if act == "y" then App.push(require("screens.search").new(self.query)); return true end
  if act == "start" then self:apply(); return true end
  return false
end

function Results:update(dt) self.list:update(dt) end
function Results:resume() App.dirty = true end

function Results:draw()
  D.rect(0, 0, W, BAR, c.bg)
  D.rect(0, BAR - 1, W, 1, c.divider)
  D.icon("arrow_back", 5, 3, 20, c.text)
  D.rect(32, 3, W - 32 - 60, 20, c.surface, 10)
  D.icon("search", 38, 5, 16, c.secondary)
  T.line(self.query, 58, 5, W - 32 - 60 - 36, 13, "regular", c.text)
  D.icon("tune", W - 52, 3, 20, self:is_default() and c.text or c.red)
  T.print("Ⓧ", W - 28, 7, 12, "bold", c.secondary)
  self.list:draw(0, BAR, W, H - BAR - App.bottom_inset(), true)
end

return Results
