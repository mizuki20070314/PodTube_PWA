-- Navigation helpers shared by the screens (the PWA's PT.router): open a video / channel / playlist / search, menus.
local store = require("core.store")
local account = require("core.account")
local I = require("core.i18n")
local Net = require("core.net")
local log = require("core.log")
local U = require("lib.util")

local N = {}

function N.play(video, opts)
  local watch = require("screens.watch")
  App.push(watch.new(video, opts))
end

function N.open_channel(id, name)
  if not id or id == "" then App.toast(I.t("common.error")); return end
  App.push(require("screens.channel").new(id, name))
end

function N.open_playlist(id, title)
  if id:sub(1, 2) == "RD" and #id == 13 then
    -- A Mix ("RD" + video id) cannot be browsed; play its seed video and let autoplay follow the related list.
    N.play({ id = id:sub(3), title = title })
    return
  end
  App.push(require("screens.playlist").new(id, title))
end

function N.open_search_results(q)
  store.add_search(q)
  App.push(require("screens.results").new(q))
end

function N.open_shorts(list, index)
  App.push(require("screens.shorts").new_player(list, index))
end

--- the owner of a video whose channel id is not known yet
function N.open_owner(video)
  local known = store.channel_lookup(video.channelId, video.channelName)
  local id = video.channelId
  if (not id or id == "") and known then id = known.id end
  if id and id ~= "" then N.open_channel(id, video.channelName); return end
  Net.get("owner", { v = video.id }, function(err, r)
    if err or not r.channel then App.toast(I.t("common.error")); return end
    N.open_channel(r.channel.id, r.channel.name)
  end)
end

---------------------------------------------------------------------------------------------------------------------
-- links typed or pasted into the search field (PT.parseLink in the PWA)
---------------------------------------------------------------------------------------------------------------------
local function is_id(x) return type(x) == "string" and #x == 11 and x:match("^[%w_%-]+$") ~= nil end

function N.parse_link(text)
  local t = U.trim(text or "")
  if t == "" or t:find("%s") then return nil end
  local s = t
  if not s:find("://", 1, true) then s = "https://" .. s end
  local host, path, query = s:match("^%a[%w+.%-]*://([^/?#:]+)[^/?#]*([^?#]*)%??([^#]*)")
  if not host then return nil end
  host = host:lower()
  for _, pre in ipairs { "www.", "m.", "music." } do
    if host:sub(1, #pre) == pre then host = host:sub(#pre + 1) end
  end
  local q = {}
  for kv in (query or ""):gmatch("[^&]+") do
    local k, v = kv:match("^([^=]*)=?(.*)$")
    if k and q[k] == nil then q[k] = v end
  end
  local parts = {}
  for part in (path or ""):gmatch("[^/]+") do parts[#parts + 1] = part end
  if host == "youtu.be" then
    if is_id(parts[1]) then return { type = "video", id = parts[1], list = q.list } end
    return nil
  end
  if host ~= "youtube.com" and host ~= "youtube-nocookie.com" then return nil end
  local first = parts[1]
  if not first then return nil end
  if first == "watch" then
    if is_id(q.v) then return { type = "video", id = q.v, list = q.list } end
  elseif first == "shorts" or first == "live" or first == "embed" or first == "v" or first == "e" then
    if is_id(parts[2]) then return { type = "video", id = parts[2] } end
  elseif first == "playlist" then
    if q.list and q.list ~= "" then return { type = "playlist", id = q.list } end
  elseif first == "channel" then
    if parts[2] and parts[2]:sub(1, 2) == "UC" then return { type = "channel", id = parts[2] } end
  elseif first == "user" or first == "c" then
    return { type = "resolve", url = "https://www.youtube.com" .. path }
  elseif first:sub(1, 1) == "@" then
    return { type = "resolve", url = "https://www.youtube.com/" .. first }
  end
  return nil
end

--- opens what a link points to; false when the text is not a link
function N.open_text(text)
  local target = N.parse_link(text)
  if not target then return false end
  if target.type == "video" then
    N.play({ id = target.id, title = "", channelName = "", channelId = "", channelAvatar = "", thumbnail = "", duration = "", views = "", published = "",
      isLive = false, isUpcoming = false, isShort = false }, { playlist_id = target.list })
  elseif target.type == "playlist" then N.open_playlist(target.id, "")
  elseif target.type == "channel" then N.open_channel(target.id, "")
  elseif target.type == "resolve" then
    Net.get("resolve", { url = target.url }, function(err, r)
      if err or not r.id then App.toast(I.t("common.error")); return end
      N.open_channel(r.id, "")
    end)
  end
  return true
end

---------------------------------------------------------------------------------------------------------------------
-- menus
---------------------------------------------------------------------------------------------------------------------
function N.playlist_picker(video)
  local items = {}
  if account.signed_in() then
    App.toast(I.t("common.loading"), 1.2)
    account.load_playlists(false, function(list)
      if #list == 0 then App.toast(I.t("common.empty")); return end
      local rows = {}
      for _, p in ipairs(list) do
        rows[#rows + 1] = { label = p.title, icon = "playlist_add", on = function() account.add_to_playlist(p, video) end }
      end
      App.open_sheet({ title = I.t("video.addToPlaylist"), items = rows })
    end)
    return
  end
  local lists = store.playlists()
  for _, p in ipairs(lists) do
    local has = false
    for _, v in ipairs(p.videos) do if v.id == video.id then has = true end end
    items[#items + 1] = {
      label = p.name, sub = tostring(#p.videos), icon = "playlist_add_check", checked = has, keep_open = false,
      on = function() store.toggle_in_playlist(video, p.id); App.toast(has and I.t("video.removedFrom", p.name) or I.t("video.addedTo", p.name)) end,
    }
  end
  items[#items + 1] = {
    label = I.t("video.newPlaylist"), icon = "add",
    on = function()
      require("screens.osk").ask({ title = I.t("video.newPlaylist"), text = "", on_submit = function(name)
        name = (name or ""):gsub("^%s+", ""):gsub("%s+$", "")
        if name ~= "" then store.create_playlist(name, video); App.toast(I.t("video.addedTo", name)) end
      end })
    end,
  }
  App.open_sheet({ title = I.t("video.addToPlaylist"), items = items })
end

--- start / delete / cancel a download of `video`
function N.download_menu(video)
  local Downloads = require("core.downloads")
  if Downloads.record(video.id) then
    local rec = Downloads.record(video.id)
    App.open_sheet({ title = I.t("video.download"), items = {
      { label = I.t("downloads.saved"), sub = (rec.height or 0) .. "p", icon = "offline_pin" },
      { label = I.t("common.delete"), icon = "delete", danger = true, on = function() Downloads.remove(video.id) end } } })
  elseif Downloads.is_downloading(video.id) then
    App.open_sheet({ title = I.t("video.download"), items = {
      { label = I.t("common.cancel"), icon = "close", danger = true, on = function() Downloads.cancel(video.id) end } } })
  else
    local items = {}
    for _, h in ipairs { 144, 240, 360, 480 } do
      items[#items + 1] = { label = h .. "p", icon = "file_download", on = function() Downloads.start(video, h) end }
    end
    App.open_sheet({ title = I.t("video.download"), items = items })
  end
end

function N.video_menu(video, extra)
  if not video then return end
  local saved = store.is_watch_later(video.id)
  local items = {}
  items[#items + 1] = {
    label = saved and I.t("video.removeWatchLater") or I.t("video.watchLater"), icon = "watch_later",
    on = function()
      account.set_watch_later(video, not saved)
      App.toast(saved and I.t("video.removed") or I.t("video.saved"))
    end,
  }
  items[#items + 1] = { label = I.t("video.addToPlaylist"), icon = "playlist_add", on = function() N.playlist_picker(video) end }
  if (video.channelId and video.channelId ~= "") or (video.channelName and video.channelName ~= "") then
    items[#items + 1] = { label = I.t("video.channel"), icon = "account_circle", on = function() N.open_owner(video) end }
  end
  if not video.isLive and not video.isUpcoming then
    local Downloads = require("core.downloads")
    items[#items + 1] = { label = Downloads.record(video.id) and I.t("downloads.saved") or I.t("video.download"),
      icon = Downloads.record(video.id) and "offline_pin" or "file_download", on = function() N.download_menu(video) end }
  end
  items[#items + 1] = {
    label = I.t("video.share"), icon = "share",
    on = function() N.show_link(video) end,
  }
  for _, e in ipairs(extra or {}) do items[#items + 1] = e end
  App.open_sheet({ title = video.title, items = items })
end

--- there is no clipboard on the device: show the link instead
function N.show_link(video)
  local url = "https://youtu.be/" .. video.id
  App.open_sheet({ title = I.t("video.share"), items = { { label = url, icon = "link" } } })
end

return N
