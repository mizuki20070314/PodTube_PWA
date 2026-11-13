-- Sign-in session (tokens live on this device only; the server keeps none) and the account actions.
-- Same behaviour as the PWA's 04-api.js: the local store stays the source of truth for the UI; while signed in every
-- change is also sent to the account and rolled back when YouTube refuses it.
local store = require("core.store")
local Net = require("core.net")
local I = require("core.i18n")
local log = require("core.log")

local A = {}

local refreshing   -- list of callbacks waiting for a refresh

function A.init()
  Net.token_provider = A.token
  Net.refresh_token = A.refresh
  if A.signed_in() and not store.profile then A.refresh_profile() end
end

function A.signed_in() return store.auth ~= nil end
function A.profile() return store.profile end

local function auth_error()
  return { code = "auth", message = I.t("account.signInRequired"), status = 401 }
end

--- after the device code was approved
function A.adopt(t)
  store.auth = {
    accessToken = t.accessToken, refreshToken = t.refreshToken,
    expiresAt = os.time() + (t.expiresIn or 3600),
  }
  store.save_now("auth")
  if A.on_change then A.on_change() end
end

function A.clear_local()
  store.auth, store.profile = nil, nil
  store.save_now("auth")
  store.save_now("profile")
  if A.on_change then A.on_change() end
end

--- cb(err, accessToken): a valid token, refreshed first when it is about to expire
function A.token(cb)
  local rec = store.auth
  if not rec then cb(auth_error(), nil); return end
  if rec.expiresAt - os.time() > 90 then cb(nil, rec.accessToken); return end
  A.refresh(cb)
end

function A.refresh(cb)
  local rec = store.auth
  if not rec then cb(auth_error(), nil); return end
  if refreshing then refreshing[#refreshing + 1] = cb; return end
  refreshing = { cb }
  Net.post("auth/refresh", { refreshToken = rec.refreshToken }, function(err, r)
    local waiting = refreshing
    refreshing = nil
    local e, token = nil, nil
    if err then
      e = err
    elseif r.status == "ok" and store.auth then
      store.auth.accessToken = r.accessToken
      store.auth.expiresAt = os.time() + (r.expiresIn or 3600)
      store.save_now("auth")
      token = store.auth.accessToken
    else
      if r.status == "revoked" then A.clear_local() end   -- revoked from the Google account page
      e = auth_error()
    end
    for _, f in ipairs(waiting) do f(e, token) end
  end)
end

function A.sign_out()
  local rec = store.auth
  A.clear_local()
  if rec then Net.post("auth/revoke", { token = rec.refreshToken }, function() end) end
end

function A.refresh_profile()
  Net.get("acct/profile", nil, function(err, p)
    if err or not p then return end
    store.profile = { name = p.name, handle = p.handle, avatar = p.avatar }
    store.save_now("profile")
    if A.on_change then A.on_change() end
  end, { auth = true })
end

--- name / avatar and the channels that can be mirrored locally
function A.did_sign_in()
  A.refresh_profile()
  Net.get("acct/subscriptions", nil, function(err, s)
    if not err and s then store.merge_subscriptions(s.channels or {}) end
  end, { auth = true })
  Net.get("acct/channels", nil, function(err, s)
    if not err and s then store.merge_subscriptions(s.channels or {}) end
  end, { auth = true })
end

---------------------------------------------------------------------------------------------------------------------
-- account actions
---------------------------------------------------------------------------------------------------------------------
local function rollback(undo)
  undo()
  App.toast(I.t("account.actionFailed"))
end

function A.set_like(video, status)
  local before = store.is_liked(video.id)
  store.set_liked(video, status == "like")
  if not A.signed_in() then return end
  Net.post("acct/like", { v = video.id, status = status }, function(err)
    if err then rollback(function() store.set_liked(video, before) end) end
  end, { auth = true })
end

function A.toggle_like(video)
  A.set_like(video, store.is_liked(video.id) and "none" or "like")
end

function A.set_subscribed(channel, on)
  local before = store.is_subscribed(channel.id)
  if on then store.subscribe(channel) else store.unsubscribe(channel.id) end
  if not A.signed_in() then return end
  Net.post("acct/subscribe", { id = channel.id, on = on }, function(err)
    if err then
      rollback(function() if before then store.subscribe(channel) else store.unsubscribe(channel.id) end end)
    end
  end, { auth = true })
end

function A.toggle_subscribe(channel) A.set_subscribed(channel, not store.is_subscribed(channel.id)) end

function A.set_watch_later(video, on)
  local before = store.is_watch_later(video.id)
  if before ~= on then store.toggle_watch_later(video) end
  if not A.signed_in() then return end
  Net.post("acct/editplaylist", { id = "WL", v = video.id, add = on }, function(err)
    if err then
      rollback(function() if store.is_watch_later(video.id) ~= before then store.toggle_watch_later(video) end end)
    end
  end, { auth = true })
end

function A.add_to_playlist(playlist, video)
  Net.post("acct/editplaylist", { id = playlist.id, v = video.id, add = true }, function(err)
    if err then App.toast(I.t("account.actionFailed")) else App.toast(I.t("video.addedTo", playlist.title)) end
  end, { auth = true })
end

local playlist_cache
--- the account's own playlists (without "Watch later" / "Liked videos"), cached for the save sheet
function A.load_playlists(force, cb)
  if not force and playlist_cache then cb(playlist_cache); return end
  Net.post("acct/browse", { browseId = "FEplaylist_aggregation" }, function(err, page)
    if err or not page then cb({}); return end
    local list = {}
    for _, it in ipairs(page.items or {}) do
      if it.type == "playlist" and it.playlist.id ~= "WL" and it.playlist.id ~= "LL" then list[#list + 1] = it.playlist end
    end
    playlist_cache = list
    cb(list)
  end, { auth = true })
end

function A.reset_cache() playlist_cache = nil end

function A.load_watch_state(video, cb)
  if not A.signed_in() then cb(nil); return end
  Net.get("acct/watchstate", { v = video.id }, function(err, st) cb(not err and st or nil) end, { auth = true })
end

return A
