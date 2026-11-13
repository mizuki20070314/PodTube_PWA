-- Channel: header (avatar, name, stats, subscribe), tabs and the tab's feed (S.channel in the PWA)
local theme = require("ui.theme")
local D = require("ui.draw")
local T = require("ui.text")
local NavBar = require("ui.navbar")
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

local Channel = {}
Channel.__index = Channel

local asked = {}

local function as_item(i)
  return { id = i.id, name = i.name, handle = i.handle, avatar = i.avatar, subscribers = i.subscribers, videoCount = i.videoCount }
end

--- videos on channel tabs carry no byline of their own
local function fill(page, info)
  local out = { items = {}, sections = page.sections, continuation = page.continuation }
  for _, it in ipairs(page.items or {}) do
    if it.type == "video" then
      local v = U.copy(it.video)
      if not v.channelName or v.channelName == "" then v.channelName = info.name end
      if not v.channelId or v.channelId == "" then v.channelId = info.id end
      out.items[#out.items + 1] = { type = "video", video = v }
    elseif it.type == "shorts" then
      local vs = {}
      for _, v in ipairs(it.videos) do
        local cp = U.copy(v)
        if not cp.channelName or cp.channelName == "" then cp.channelName = info.name end
        vs[#vs + 1] = cp
      end
      out.items[#out.items + 1] = { type = "shorts", videos = vs }
    else
      out.items[#out.items + 1] = it
    end
  end
  return out
end

function Channel.new(channel_id, name)
  local self = setmetatable({ name = "channel", channel_id = channel_id, title = name or "", info = nil, tab = 1, tab_focus = 1, loaded_info = false }, Channel)
  local me = self
  self.feed = Feed.new({
    endpoint = "browse",
    fetch_first = function(cb, user, feed)
      feed.endpoint = "browse"
      local info = me.info
      if info and me.tab <= #info.tabs and (not me.loaded_info or me.tab ~= 1) then
        local tab = info.tabs[me.tab]
        Net.get("channeltab", { id = info.id, params = tab.params }, function(err, page)
          if err then cb(err); return end
          cb(nil, fill(page, info))
        end)
        return
      end
      Net.get("channel", { id = channel_id }, function(err, i)
        if err then cb(err); return end
        me.info, me.loaded_info = i, true
        me.title = i.name
        me:sync_subscription(i)
        me.list:set_pre(me:make_pre())
        local page = U.copy(i.firstPage or { items = {} })
        page.continuation = nil          -- the Home tab is a set of shelves; shown as a flat list
        cb(nil, fill(page, i))
      end)
    end,
  })
  self.list = FeedList.new(self.feed, {
    shoulder_page = true,
    on_play = function(v, l) nav.play(v) end,
    on_more = function(v) nav.video_menu(v) end,
    on_channel = function(ch) nav.open_channel(ch.id, ch.name) end,
    on_playlist = function(p) nav.open_playlist(p.id, p.title) end,
    on_shorts = function(list, i) nav.open_shorts(list, i) end,
  })
  self.list:set_pre(self:make_pre())
  self.feed:reload()
  return self
end

--- signed in: the account knows whether this channel is subscribed
function Channel:sync_subscription(i)
  if not account.signed_in() or store.is_subscribed(i.id) or asked[i.id] then return end
  asked[i.id] = true
  Net.get("acct/subscribed", { id = i.id }, function(err, r)
    if not err and r.subscribed then store.subscribe(as_item(i)) end
  end, { auth = true })
end

function Channel:select_tab(i)
  if not self.info or i > #self.info.tabs or i == self.tab then return end
  self.tab = i
  self.feed:clear()
  self.list:reset()
  if i == 1 then self.loaded_info = false; self.info = nil end
  self.list:set_pre(self:make_pre())
  self.feed:reload()
end

function Channel:make_pre()
  local me = self
  local rows = {}
  -- header: avatar, name, meta, subscribe
  rows[#rows + 1] = {
    h = 58,
    draw = function(row, x, y, w, focused)
      local i = me.info
      local name = (i and i.name) or me.title
      local img = i and Img.get(Img.avatar_url(i.avatar, 96)) or nil
      D.avatar(img, x + 8 + 22, y + 29, 44)
      local sub = i and store.is_subscribed(i.id)
      local label = sub and I.t("video.subscribed") or I.t("video.subscribe")
      local bw = math.floor(T.width(label, 11, "medium")) + 24
      local tw = w - 8 - 52 - bw - 22
      T.line(name or "", x + 62, y + 10, tw, 14, "bold", c.text)
      local meta = {}
      if i then
        if i.handle and i.handle ~= "" then meta[#meta + 1] = i.handle end
        if i.subscribers and i.subscribers ~= "" then meta[#meta + 1] = i.subscribers end
        if i.videoCount and i.videoCount ~= "" then meta[#meta + 1] = i.videoCount end
      end
      T.line(table.concat(meta, " · "), x + 62, y + 30, tw, 10, "regular", c.secondary)
      if i then
        local px = x + w - bw - 10
        D.rect(px, y + 16, bw, 26, sub and c.surface_high or c.chip_sel, 13)
        T.line(label, px + 12, y + 16 + 6, bw - 24, 11, "medium", sub and c.text or c.chip_sel_text)
        if focused then D.focus_ring(px, y + 16, bw, 26, 13) end
      end
    end,
    activate = function()
      if me.info then
        account.toggle_subscribe(as_item(me.info))
        App.toast(store.is_subscribed(me.info.id) and I.t("video.subscribed") or I.t("video.subscribe"))
      end
    end,
  }
  -- tabs
  rows[#rows + 1] = {
    h = function() return (me.info and #me.info.tabs > 0) and 34 or 0 end,
    draw = function(row, x, y, w, focused)
      local info = me.info
      if not info then return end
      local cx = x + 8
      for i, t in ipairs(info.tabs) do
        local tw = math.floor(T.width(t.title, 12, "medium")) + 22
        local sel = i == me.tab
        D.rect(cx, y + 5, tw, 24, sel and c.chip_sel or c.surface, 12)
        T.line(t.title, cx + 11, y + 5 + 4, tw - 22, 12, "medium", sel and c.chip_sel_text or c.text)
        if focused and i == me.tab_focus then D.focus_ring(cx, y + 5, tw, 24, 12) end
        cx = cx + tw + 6
      end
    end,
    action = function(act)
      local info = me.info
      if not info then return false end
      if act == "left" and me.tab_focus > 1 then me.tab_focus = me.tab_focus - 1; return true end
      if act == "right" and me.tab_focus < #info.tabs then me.tab_focus = me.tab_focus + 1; return true end
      return false
    end,
    activate = function() me:select_tab(me.tab_focus) end,
  }
  return rows
end

function Channel:action(act, kind)
  if kind == "release" then return false end
  if self.list:action(act, kind) then return true end
  if act == "y" then App.open_search(); return true end
  return false
end

function Channel:update(dt) self.list:update(dt) end
function Channel:resume() App.dirty = true end

function Channel:draw()
  NavBar.draw(self.title)
  self.list:draw(0, NavBar.H, W, H - NavBar.H - App.bottom_inset(), true)
end

return Channel
