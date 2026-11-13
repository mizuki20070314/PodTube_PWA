-- Subscriptions tab: a strip of the subscribed channels and the newest videos of them (S.subscriptions in the PWA)
local theme = require("ui.theme")
local D = require("ui.draw")
local T = require("ui.text")
local Feed = require("core.feed")
local FeedList = require("ui.feedlist")
local Net = require("core.net")
local Img = require("core.img")
local store = require("core.store")
local account = require("core.account")
local nav = require("core.nav")
local I = require("core.i18n")
local U = require("lib.util")

local c = theme.c
local W, H = theme.W, theme.H

local Subs = {}
Subs.__index = Subs

function Subs.new()
  local self = setmetatable({ name = "subs", account_channels = {}, strip_sel = 1, last_load = 0, shown_ids = "" }, Subs)
  local me = self
  self.feed = Feed.new({
    endpoint = "browse",
    fetch_first = function(cb, user, feed)
      me.last_load = love.timer.getTime()
      if account.signed_in() then me:fetch_account(cb, feed) else me:fetch_local(cb, feed) end
    end,
  })
  self.list = FeedList.new(self.feed, {
    empty_text = I.t("subs.empty"), empty_icon = "subscriptions", empty_detail = I.t("subs.emptyHint"),
    on_play = function(v) nav.play(v) end,
    on_more = function(v) nav.video_menu(v) end,
    on_shorts = function(list, i) nav.open_shorts(list, i) end,
  })
  self.list:set_pre({ self:strip_row() })
  self.shown_ids = self:ids()
  self.feed:reload()
  self.chg = store.on_change(function() end)
  return self
end

function Subs:ids()
  local t = {}
  for _, ch in ipairs(store.subscriptions()) do t[#t + 1] = ch.id end
  return table.concat(t, ",")
end

function Subs:channels()
  if account.signed_in() then return self.account_channels end
  return store.subscriptions()
end

--- the account's own feed (TV client) plus its channel strip
function Subs:fetch_account(cb, feed)
  feed.endpoint = "tv"
  Net.get("acct/subscriptions", nil, function(err, r)
    if err then cb(err); return end
    self.account_channels = r.channels or {}
    for _, ch in ipairs(self.account_channels) do store.channel_learn(ch.id, ch.name, ch.avatar) end
    store.merge_subscriptions(self.account_channels)
    self.list:invalidate()
    cb(nil, r.feed)
  end, { auth = true })
end

--- signed out: the subscriptions are stored on this device and the feed is built from each channel's Videos tab
function Subs:fetch_local(cb, feed)
  feed.endpoint = "browse"
  local subs = {}
  for _, ch in ipairs(store.subscriptions()) do subs[#subs + 1] = ch end
  if #subs == 0 then cb(nil, { items = {} }); return end
  local chunks = {}
  for i = 1, #subs, 30 do
    local chunk = {}
    for j = i, math.min(i + 29, #subs) do chunk[#chunk + 1] = { id = subs[j].id, name = subs[j].name, avatar = subs[j].avatar } end
    chunks[#chunks + 1] = chunk
  end
  local all, next_i, running = {}, 1, 0
  local function done_all()
    table.sort(all, function(a, b)
      if (a._age or 0) ~= (b._age or 0) then return (a._age or 0) < (b._age or 0) end
      return (a._order or 0) < (b._order or 0)
    end)
    local items = {}
    for i = 1, math.min(150, #all) do items[i] = { type = "video", video = all[i] } end
    cb(nil, { items = items })
  end
  local function pump()
    -- two chunks at a time keep the server's load (and the wait) reasonable
    while running < 2 and next_i <= #chunks do
      local chunk = chunks[next_i]
      next_i = next_i + 1
      running = running + 1
      Net.post("subsfeed", { channels = chunk }, function(err, r)
        running = running - 1
        if not err then for _, v in ipairs(r.videos or {}) do all[#all + 1] = v end end
        if next_i > #chunks and running == 0 then done_all() else pump() end
      end, { timeout = 90 })
    end
  end
  pump()
end

function Subs:strip_row()
  local me = self
  return {
    h = function() return #me:channels() > 0 and 64 or 0 end,
    draw = function(row, x, y, w, focused)
      local list = me:channels()
      local n = #list + 1                     -- + the "all" button
      local cw = 58
      local first = math.max(1, me.strip_sel - math.floor((w - 16) / cw) + 1)
      me.strip_first = U.damp(me.strip_first or 1, first, 14, love.timer.getDelta())
      local x0 = x + 8 - (me.strip_first - 1) * cw
      D.clip(x, y, w, 64)
      for i = 1, n do
        local cx = x0 + (i - 1) * cw
        if cx + cw > x and cx < x + w then
          local sel = focused and me.strip_sel == i
          if i <= #list then
            local ch = list[i]
            local img = Img.get(Img.avatar_url(ch.avatar, 96))
            D.avatar(img, cx + cw / 2 - 2, y + 24, 36)
            T.line(ch.name or "", cx, y + 45, cw - 4, 10, "regular", c.secondary, "center")
            if sel then D.outline(cx + cw / 2 - 2 - 20, y + 24 - 20, 40, 40, c.white, 20, 2) end
          else
            D.rect(cx + 6, y + 10, cw - 14, 28, c.surface_high, 14)
            T.line(I.t("subs.all"), cx + 6, y + 17, cw - 14, 12, "medium", c.text, "center")
            if sel then D.outline(cx + 5, y + 9, cw - 12, 30, c.white, 15, 2) end
          end
        end
      end
      D.unclip()
    end,
    action = function(act)
      local n = #me:channels() + 1
      if act == "left" and me.strip_sel > 1 then me.strip_sel = me.strip_sel - 1; return true end
      if act == "right" and me.strip_sel < n then me.strip_sel = me.strip_sel + 1; return true end
      return false
    end,
    activate = function()
      local list = me:channels()
      if me.strip_sel <= #list then nav.open_channel(list[me.strip_sel].id, list[me.strip_sel].name)
      else App.push(require("screens.library").channels()) end
    end,
  }
end

function Subs:reload_all()
  self.shown_ids = self:ids()
  self.feed:clear()
  self.list:reset()
  self.list:set_pre({ self:strip_row() })
  self.feed:reload()
end

function Subs:resume()
  App.dirty = true
  local now = love.timer.getTime()
  if account.signed_in() then
    if now - self.last_load > 600 then self:reload_all() end
  elseif self:ids() ~= self.shown_ids or now - self.last_load > 600 then
    self:reload_all()
  end
end

function Subs:scroll_top() self.list:reset(); self.list:set_pre({ self:strip_row() }) end

function Subs:action(act, kind)
  if kind == "release" then return false end
  if act == "start" then self:reload_all(); return true end
  if self.list:action(act, kind) then return true end
  return false
end

function Subs:update(dt) self.list:update(dt) end

function Subs:draw()
  local x, w = App.content_rect()
  self.list:draw(x, 0, w, H - App.bottom_inset(), App.focus == "content")
end

return Subs
