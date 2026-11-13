-- Settings and the local data (history, subscriptions, watch later, likes, playlists, searches ...).
-- Same meaning as the PWA's 03-store.js; every list lives in its own JSON file in the save directory.
local json = require("lib.json")
local log = require("core.log")
local U = require("lib.util")

local S = { settings_saved = {}, server = {} }

local savedir
local lists = {}      -- name -> table
local pending = {}    -- name -> due time

local function path(name) return savedir .. "/" .. name .. ".json" end

local function read(name, default)
  local txt = U.read_file(path(name))
  if not txt or txt == "" then return default end
  local ok, v = pcall(json.decode, txt)
  if ok and v ~= nil then return v end
  log.warn("store: cannot parse", name)
  return default
end

local function write(name, value)
  local tmp = path(name) .. ".tmp"
  local ok = U.write_file(tmp, json.encode(value))
  if not ok then log.warn("store: cannot write", name); return false end
  os.remove(path(name))
  if not os.rename(tmp, path(name)) then log.warn("store: rename failed", name); return false end
  return true
end

function S.init()
  savedir = love.filesystem.getSaveDirectory()
  love.filesystem.createDirectory("")
  lists.history = read("history", {})
  lists.subs = read("subs", {})
  lists.watchlater = read("watchlater", {})
  lists.liked = read("liked", {})
  lists.playlists = read("playlists", {})
  lists.searches = read("searches", {})
  lists.homeseen = read("homeseen", {})
  lists.chdir = read("chdir", {})
  S.settings_saved = read("settings", {})
  S.server = read("server", {})
  S.auth = read("auth", nil)
  S.profile = read("profile", nil)
  S.visitor_rec = read("visitor", nil)
  S.input_map = read("inputmap", nil)
  S.dir = savedir
end

function S.later(name, delay)
  pending[name] = love.timer.getTime() + (delay or 1.0)
end

local getters = {
  history = function() return lists.history end, subs = function() return lists.subs end,
  watchlater = function() return lists.watchlater end, liked = function() return lists.liked end,
  playlists = function() return lists.playlists end, searches = function() return lists.searches end,
  homeseen = function() return lists.homeseen end, chdir = function() return lists.chdir end,
  settings = function() return S.settings_saved end, server = function() return S.server end,
  auth = function() return S.auth end, profile = function() return S.profile end,
  visitor = function() return S.visitor_rec end, inputmap = function() return S.input_map end,
}

function S.save_now(name)
  pending[name] = nil
  local g = getters[name]
  local v = g and g()
  if v == nil then
    os.remove(path(name))
    return
  end
  write(name, v)
end

function S.update()
  if next(pending) == nil then return end
  local now = love.timer.getTime()
  for name, due in pairs(pending) do
    if now >= due then S.save_now(name) end
  end
end

function S.flush()
  for name in pairs(pending) do S.save_now(name) end
end

---------------------------------------------------------------------------------------------------------------------
-- settings
---------------------------------------------------------------------------------------------------------------------
local DEFAULTS = {
  autoplay = true,
  pauseHistory = false,
  captionsAlways = false,
  maxQuality = 360,         -- the highest picture height for playback (this screen is 480x272: 360 is plenty)
  playbackSpeed = 1,
  preferredAudio = "",
  uiLanguage = "auto",      -- auto | ja | en
  contentRegion = "",
  showStats = false,
  videoFps = 30,            -- cap for 50/60 fps videos
  avOffsetMs = 0,           -- shifts the picture against the sound (positive = the picture comes later)
  autoSync = true,          -- repair a picture that falls out of step with the sound (resync, lower quality when it is too heavy)
}
S.DEFAULTS = DEFAULTS

function S.get(key)
  local v = S.settings_saved[key]
  if v == nil then return DEFAULTS[key] end
  return v
end

function S.set(key, value)
  S.settings_saved[key] = value
  S.later("settings", 0.3)
end

S.REGIONS = {
  { "JP", "日本 / Japan" }, { "US", "United States" }, { "GB", "United Kingdom" }, { "KR", "한국 / Korea" },
  { "DE", "Deutschland" }, { "FR", "France" }, { "ES", "España" }, { "BR", "Brasil" }, { "IN", "India" }, { "AU", "Australia" },
}
local LANG_OF_REGION = { JP = "ja", KR = "ko", DE = "de", FR = "fr", ES = "es", BR = "pt" }

function S.is_japanese()
  local l = S.get("uiLanguage")
  if l == "ja" then return true end
  if l == "en" then return false end
  return true -- the device is used in Japanese by default
end

function S.region()
  local r = S.get("contentRegion")
  if r and r ~= "" then return r end
  return S.is_japanese() and "JP" or "US"
end
function S.hl() return LANG_OF_REGION[S.region()] or "en" end
function S.gl() return S.region() end

---------------------------------------------------------------------------------------------------------------------
-- helpers over the lists
---------------------------------------------------------------------------------------------------------------------
local function idx(list, id)
  for i = 1, #list do if list[i].id == id then return i end end
  return nil
end

local function hidx(video_id)
  local h = lists.history
  for i = 1, #h do if h[i].video.id == video_id then return i end end
  return nil
end

function S.slim(v)
  return {
    id = v.id, title = v.title or "", channelName = v.channelName or "", channelId = v.channelId or "",
    channelAvatar = v.channelAvatar or "", thumbnail = v.thumbnail or "", duration = v.duration or "",
    views = v.views or "", published = v.published or "", isLive = v.isLive and true or false,
    isUpcoming = v.isUpcoming and true or false, isShort = v.isShort and true or false,
  }
end

local changed_cb = {}
function S.on_change(fn) changed_cb[#changed_cb + 1] = fn; return fn end
function S.off_change(fn)
  for i, f in ipairs(changed_cb) do if f == fn then table.remove(changed_cb, i); return end end
end
local function changed()
  for _, fn in ipairs({ unpack(changed_cb) }) do fn() end
  if App then App.dirty = true end
end
S.notify = changed

-- history ------------------------------------------------------------------------------------------------------------
function S.history() return lists.history end

function S.add_history(video, position, duration)
  if S.get("pauseHistory") then return end
  local i = hidx(video.id)
  if i then table.remove(lists.history, i) end
  table.insert(lists.history, 1, { video = S.slim(video), watchedAt = os.time() * 1000, position = position or 0, duration = duration or 0 })
  while #lists.history > 500 do table.remove(lists.history) end
  S.later("history"); changed()
end

function S.update_history_video(video)
  local i = hidx(video.id)
  if not i then return end
  local v = lists.history[i].video
  for _, k in ipairs { "title", "channelName", "channelId", "channelAvatar", "thumbnail" } do
    if video[k] and video[k] ~= "" then v[k] = video[k] end
  end
  S.later("history")
end

function S.update_progress(video_id, position, duration)
  local i = hidx(video_id)
  if not i then return end
  lists.history[i].position = position
  if duration and duration > 0 then lists.history[i].duration = duration end
  S.later("history", 2.0)
end

function S.progress(video_id)
  local i = hidx(video_id)
  if not i then return nil end
  local e = lists.history[i]
  if not (e.duration and e.duration > 0) then return nil end
  return U.clamp(e.position / e.duration, 0, 1)
end

function S.resume_position(video_id)
  local i = hidx(video_id)
  if not i then return nil end
  local e = lists.history[i]
  if not (e.duration and e.duration > 0) then return nil end
  if e.position < 5 or e.position > e.duration - 10 then return nil end
  return e.position
end

function S.remove_history(video_id)
  local i = hidx(video_id)
  if i then table.remove(lists.history, i); S.later("history"); changed() end
end

function S.clear_history()
  lists.history = {}
  S.save_now("history"); changed()
end

-- subscriptions ------------------------------------------------------------------------------------------------------
function S.subscriptions() return lists.subs end
function S.is_subscribed(cid) return idx(lists.subs, cid) ~= nil end

function S.subscribe(ch)
  if S.is_subscribed(ch.id) then return end
  table.insert(lists.subs, 1, {
    id = ch.id, name = ch.name or "", handle = ch.handle or "", avatar = ch.avatar or "",
    subscribers = ch.subscribers or "", videoCount = ch.videoCount or "",
  })
  S.later("subs"); changed()
end

function S.unsubscribe(cid)
  local i = idx(lists.subs, cid)
  if i then table.remove(lists.subs, i); S.later("subs"); changed() end
end

function S.merge_subscriptions(list)
  local added = false
  for _, c in ipairs(list or {}) do
    if not S.is_subscribed(c.id) then lists.subs[#lists.subs + 1] = c; added = true end
  end
  if added then S.later("subs"); changed() end
end

-- watch later / liked ------------------------------------------------------------------------------------------------
function S.watch_later() return lists.watchlater end
function S.is_watch_later(id) return idx(lists.watchlater, id) ~= nil end
function S.toggle_watch_later(video)
  local i = idx(lists.watchlater, video.id)
  if i then table.remove(lists.watchlater, i) else table.insert(lists.watchlater, 1, S.slim(video)) end
  S.later("watchlater"); changed()
end

function S.liked() return lists.liked end
function S.is_liked(id) return idx(lists.liked, id) ~= nil end
function S.toggle_like(video)
  local i = idx(lists.liked, video.id)
  if i then table.remove(lists.liked, i) else table.insert(lists.liked, 1, S.slim(video)) end
  S.later("liked"); changed()
end
function S.set_liked(video, on)
  if S.is_liked(video.id) ~= on then S.toggle_like(video) end
end

-- playlists ----------------------------------------------------------------------------------------------------------
function S.playlists() return lists.playlists end

function S.create_playlist(name, video)
  local p = { id = string.format("%08x%08x", math.random(0, 0x7fffffff), os.time()), name = name, videos = {} }
  if video then p.videos[1] = S.slim(video) end
  table.insert(lists.playlists, 1, p)
  S.later("playlists"); changed()
  return p
end

function S.delete_playlist(id)
  local i = idx(lists.playlists, id)
  if i then table.remove(lists.playlists, i); S.later("playlists"); changed() end
end

function S.toggle_in_playlist(video, id)
  local i = idx(lists.playlists, id)
  if not i then return end
  local vs = lists.playlists[i].videos
  local j = idx(vs, video.id)
  if j then table.remove(vs, j) else vs[#vs + 1] = S.slim(video) end
  S.later("playlists"); changed()
end

function S.remove_from_playlist(video_id, id)
  local i = idx(lists.playlists, id)
  if not i then return end
  local vs = lists.playlists[i].videos
  local j = idx(vs, video_id)
  if j then table.remove(vs, j); S.later("playlists"); changed() end
end

-- searches -----------------------------------------------------------------------------------------------------------
function S.searches() return lists.searches end

function S.add_search(q)
  q = U.trim(q or "")
  if q == "" or S.get("pauseHistory") then return end
  for i, s in ipairs(lists.searches) do
    if s == q then table.remove(lists.searches, i); break end
  end
  table.insert(lists.searches, 1, q)
  while #lists.searches > 50 do table.remove(lists.searches) end
  S.later("searches")
end

function S.remove_search(q)
  for i, s in ipairs(lists.searches) do
    if s == q then table.remove(lists.searches, i); S.later("searches"); return end
  end
end

function S.clear_searches() lists.searches = {}; S.save_now("searches") end

-- HomeSeen: Home videos that were on screen (newest last); a refresh moves these behind new videos -------------------
local seen_set
local function seen_build()
  if seen_set then return end
  seen_set = {}
  for _, id in ipairs(lists.homeseen) do seen_set[id] = true end
end

function S.home_seen_ids()
  seen_build()
  local all = {}
  for i = 1, #lists.homeseen do all[i] = lists.homeseen[i] end
  for _, e in ipairs(lists.history) do
    if not seen_set[e.video.id] then all[#all + 1] = e.video.id end
  end
  return all
end

function S.home_seen_mark(id)
  if not id then return end
  seen_build()
  if seen_set[id] then return end
  seen_set[id] = true
  lists.homeseen[#lists.homeseen + 1] = id
  if #lists.homeseen > 600 then seen_set[table.remove(lists.homeseen, 1)] = nil end
  S.later("homeseen", 3.0)
end

-- ChannelDirectory: channel name -> (id, avatar) learned from every screen that knows it ------------------------------
local chdir_by_name, chdir_by_id
local function chdir_build()
  if chdir_by_name then return end
  chdir_by_name, chdir_by_id = {}, {}
  for _, e in ipairs(lists.chdir) do
    chdir_by_name[(e.name or ""):lower()] = e
    if e.id and e.id ~= "" then chdir_by_id[e.id] = e end
  end
end

function S.channel_learn(id, name, avatar)
  if not name or name == "" or not avatar or avatar == "" then return end
  chdir_build()
  local key = name:lower()
  local old = chdir_by_name[key]
  if old and old.avatar == avatar and (not id or id == "" or old.id == id) then return end
  local e = { id = id or (old and old.id) or "", name = name, avatar = avatar }
  if old then
    for i, x in ipairs(lists.chdir) do if x == old then table.remove(lists.chdir, i); break end end
  end
  lists.chdir[#lists.chdir + 1] = e
  chdir_by_name[key] = e
  if e.id ~= "" then chdir_by_id[e.id] = e end
  while #lists.chdir > 800 do
    local gone = table.remove(lists.chdir, 1)
    chdir_by_name[(gone.name or ""):lower()] = nil
    if gone.id and chdir_by_id[gone.id] == gone then chdir_by_id[gone.id] = nil end
  end
  S.later("chdir", 3.0)
end

function S.channel_lookup(id, name)
  chdir_build()
  if id and id ~= "" and chdir_by_id[id] then return chdir_by_id[id] end
  if name and name ~= "" then return chdir_by_name[name:lower()] end
  return nil
end

return S
