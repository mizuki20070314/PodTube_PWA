-- Library lists: stored lists (history, watch later, liked, a local playlist), the account's own lists, the local playlists
-- and the channel manager (S.storedList / S.accountList / S.userPlaylists / S.channelsManager in the PWA).
local theme = require("ui.theme")
local D = require("ui.draw")
local T = require("ui.text")
local NavBar = require("ui.navbar")
local Feed = require("core.feed")
local FeedList = require("ui.feedlist")
local MenuList = require("ui.menulist")
local Net = require("core.net")
local store = require("core.store")
local account = require("core.account")
local nav = require("core.nav")
local I = require("core.i18n")
local HistoryMerge = require("core.historymerge")
local U = require("lib.util")

local c = theme.c
local W, H = theme.W, theme.H
local L = {}

local function confirm(text, ok_label, on_ok)
  App.open_sheet({ title = text, items = {
    { label = ok_label, icon = "delete", danger = true, on = on_ok },
    { label = I.t("common.cancel"), icon = "close" },
  } })
end
L.confirm = confirm

---------------------------------------------------------------------------------------------------------------------
-- a screen made of a nav bar and a FeedList
---------------------------------------------------------------------------------------------------------------------
local Base = {}
Base.__index = Base

function Base:action(act, kind)
  if kind == "release" then return false end
  if self.extra_action and self.extra_action(act) then return true end
  if self.list:action(act, kind) then return true end
  return false
end
function Base:update(dt) self.list:update(dt) end
function Base:resume() App.dirty = true end
function Base:leave() if self.store_cb then store.off_change(self.store_cb) end end
function Base:draw()
  NavBar.draw(self.title, self.hint)
  self.list:draw(0, NavBar.H, W, H - NavBar.H - App.bottom_inset(), true)
end

---------------------------------------------------------------------------------------------------------------------
-- stored lists
---------------------------------------------------------------------------------------------------------------------
function L.stored(kind, playlist_id)
  local titles = { history = I.t("library.history"), watchLater = I.t("library.watchLater"), liked = I.t("library.liked") }
  local function pl()
    for _, p in ipairs(store.playlists()) do if p.id == playlist_id then return p end end
  end
  local function videos()
    if kind == "history" then
      local out = {}
      for _, e in ipairs(store.history()) do out[#out + 1] = e.video end
      return out
    elseif kind == "watchLater" then return store.watch_later()
    elseif kind == "liked" then return store.liked() end
    local p = pl()
    return p and p.videos or {}
  end
  local self = setmetatable({ name = "stored_" .. kind, title = kind == "playlist" and (pl() and pl().name or "") or titles[kind] }, Base)
  self.feed = Feed.new({ endpoint = "browse", fetch_first = function(cb) cb(nil, { items = {} }) end })
  local function rebuild()
    local items = {}
    for _, v in ipairs(videos()) do items[#items + 1] = { type = "video", video = v } end
    self.feed:set_page({ items = items })
    self.feed.state = #items > 0 and "ready" or "empty"
  end
  self.list = FeedList.new(self.feed, {
    shoulder_page = true,
    empty_text = kind == "history" and I.t("library.emptyHistory") or I.t("common.empty"),
    on_play = function(v)
      if kind == "history" then nav.play(v) else nav.play(v, { queue = self.feed:videos() }) end
    end,
    on_more = function(v)
      local extra = {}
      if kind == "history" then
        extra[1] = { label = I.t("video.notInterested"), icon = "delete", on = function() store.remove_history(v.id) end }
      elseif kind == "playlist" then
        extra[1] = { label = I.t("common.delete"), icon = "delete", on = function() store.remove_from_playlist(v.id, playlist_id) end }
      elseif kind == "liked" then
        extra[1] = { label = I.t("common.delete"), icon = "delete", on = function() store.toggle_like(v) end }
      end
      nav.video_menu(v, extra)
    end,
  })
  if kind == "history" then
    self.hint = "START: " .. I.t("common.delete")
    self.extra_action = function(act)
      if act == "start" then
        confirm(I.t("library.confirmClear"), I.t("common.delete"), function() store.clear_history() end)
        return true
      end
    end
  end
  self.store_cb = store.on_change(rebuild)
  rebuild()
  return self
end

---------------------------------------------------------------------------------------------------------------------
-- the account's lists
---------------------------------------------------------------------------------------------------------------------
function L.account(kind)
  local browse_id = ({ history = "FEhistory", watchLater = "VLWL", liked = "VLLL", playlists = "FEplaylist_aggregation" })[kind]
  local titles = { history = I.t("library.history"), watchLater = I.t("library.watchLater"), liked = I.t("library.liked"), playlists = I.t("library.playlists") }
  local self = setmetatable({ name = "account_" .. kind, title = titles[kind] }, Base)
  local merge
  local me = self
  self.feed = Feed.new({
    endpoint = "tv",
    fetch_first = function(cb, user, feed)
      feed.endpoint = "tv"
      if not account.signed_in() then cb({ code = "auth", message = I.t("account.signInRequired"), status = 401 }); return end
      merge = kind == "history" and HistoryMerge.session() or nil
      Net.post("acct/browse", { browseId = browse_id }, function(err, page)
        if err then
          -- the account's list could not be loaded: what was played here is better than nothing
          if merge and err.code ~= "auth" then
            local items = merge.page({}, true)
            local cut = {}
            for i = 1, math.min(#items, HistoryMerge.limit) do cut[i] = items[i] end
            cb(nil, { items = cut })
            return
          end
          cb(err)
          return
        end
        if merge then page.items = merge.page(page.items or {}, not page.continuation) end
        cb(nil, page)
      end, { auth = true })
    end,
    fetch_more = function(token, endpoint, cb)
      Net.post("continuation", { token = token, endpoint = endpoint }, function(err, page)
        if err then cb(err); return end
        if merge then page.items = merge.page(page.items or {}, not page.continuation) end
        cb(nil, page)
      end, { auth = true })
    end,
  })
  self.list = FeedList.new(self.feed, {
    shoulder_page = true,
    empty_text = kind == "history" and I.t("library.emptyHistory") or I.t("common.empty"),
    on_play = function(v)
      if kind == "watchLater" or kind == "liked" then nav.play(v, { queue = self.feed:videos() }) else nav.play(v) end
    end,
    on_playlist = function(p) nav.open_playlist(p.id, p.title) end,
    on_channel = function(ch) nav.open_channel(ch.id, ch.name) end,
    on_shorts = function(list, i) nav.open_shorts(list, i) end,
    on_more = function(v)
      local extra = {}
      if kind == "watchLater" then
        extra[1] = { label = I.t("video.removeWatchLater"), icon = "delete", on = function() account.set_watch_later(v, false); self.feed:reload() end }
      elseif kind == "liked" then
        extra[1] = { label = I.t("video.unlike"), icon = "delete", on = function() account.set_like(v, "none"); self.feed:reload() end }
      end
      nav.video_menu(v, extra)
    end,
  })
  self.feed:reload()
  self.extra_action = function(act) if act == "start" then self.feed:reload(true); return true end end
  return self
end

---------------------------------------------------------------------------------------------------------------------
-- local playlists
---------------------------------------------------------------------------------------------------------------------
function L.user_playlists()
  local self = setmetatable({ name = "user_playlists", title = I.t("library.playlists"), hint = "Ⓧ " .. I.t("common.delete") .. "  START: +" }, Base)
  self.menu = MenuList.new({})
  local function rebuild()
    local items = {}
    for _, p in ipairs(store.playlists()) do
      items[#items + 1] = { kind = "item", icon = "playlist_play", label = p.name, count = tostring(#p.videos), pl = p,
        on = function() App.push(L.stored("playlist", p.id)) end }
    end
    if #items == 0 then items[1] = { kind = "note", text = I.t("library.emptyPlaylists") } end
    self.menu:set_items(items)
  end
  self.store_cb = store.on_change(rebuild)
  rebuild()
  local function create()
    require("screens.osk").ask({ title = I.t("video.newPlaylist"), on_submit = function(name)
      name = U.trim(name or "")
      if name ~= "" then store.create_playlist(name, nil) end
    end })
  end
  function self:action(act, kind)
    if kind == "release" then return false end
    if self.menu:action(act, kind) then return true end
    if act == "start" then create(); return true end
    if act == "x" then
      local it = self.menu.items[self.menu.sel]
      if it and it.pl then confirm(it.pl.name, I.t("common.delete"), function() store.delete_playlist(it.pl.id) end) end
      return true
    end
    return false
  end
  function self:update(dt) self.menu:update(dt) end
  function self:draw()
    NavBar.draw(self.title, self.hint)
    self.menu:draw(0, NavBar.H, W, H - NavBar.H - App.bottom_inset())
  end
  return self
end

---------------------------------------------------------------------------------------------------------------------
-- all subscribed channels, with unsubscribe
---------------------------------------------------------------------------------------------------------------------
function L.channels()
  local self = setmetatable({ name = "channels", title = I.t("subs.manage"), hint = "START: " .. I.t("subs.import") .. "  Ⓧ " .. I.t("video.subscribed") }, Base)
  self.feed = Feed.new({ endpoint = "browse", fetch_first = function(cb) cb(nil, { items = {} }) end })
  local function rebuild()
    local items = {}
    for _, ch in ipairs(store.subscriptions()) do items[#items + 1] = { type = "channel", channel = ch } end
    self.feed:set_page({ items = items })
    self.feed.state = #items > 0 and "ready" or "empty"
  end
  self.list = FeedList.new(self.feed, {
    shoulder_page = true, empty_text = I.t("subs.empty"), empty_icon = "subscriptions",
    empty_detail = I.t("subs.importHint"),
    on_channel = function(ch) nav.open_channel(ch.id, ch.name) end,
  })
  self.extra_action = function(act)
    if act == "start" then
      local n = require("core.subimport").run()
      if n then App.toast(I.t("subs.imported", tostring(n))) else App.toast(I.t("subs.importFailed")) end
      return true
    end
    if act == "x" then
      local it = self.list:selected()
      if it and it.type == "channel" then
        account.set_subscribed(it.channel, false)
        App.toast(I.t("video.subscribe"))
      end
      return true
    end
  end
  self.store_cb = store.on_change(rebuild)
  rebuild()
  return self
end

return L
