-- Shorts: a pager of vertical clips that loop (ShortsViewController in the original, 10-shorts.js in the PWA).
-- The clip is shown in the middle; the channel / title sit on its left, the actions on its right (the screen is wide).
local theme = require("ui.theme")
local D = require("ui.draw")
local T = require("ui.text")
local Player = require("player.player")
local Engine = require("player.engine")
local Net = require("core.net")
local Img = require("core.img")
local store = require("core.store")
local account = require("core.account")
local nav = require("core.nav")
local I = require("core.i18n")
local U = require("lib.util")

local c = theme.c
local W, H = theme.W, theme.H

local Shorts = {}
Shorts.__index = Shorts

local function bare(id)
  return { id = id, title = "", channelName = "", channelId = "", channelAvatar = "", thumbnail = "", duration = "", views = "", published = "",
    isLive = false, isUpcoming = false, isShort = true }
end

local function new(rooted)
  local self = setmetatable({ name = "shorts", videos = {}, index = 0, entries = {}, requested = {}, loading_seq = false, seeded = false,
    active = false, rooted = rooted, hide_mini = true, hud_until = 0, captures_shoulders = false }, Shorts)
  return self
end

function Shorts.new() return new(true) end

--- opened from a shelf of Shorts: `list` of videos, start at `index`
function Shorts.new_player(list, index)
  local s = new(false)
  s.videos = {}
  for _, v in ipairs(list) do s.videos[#s.videos + 1] = v end
  s.seeded = true
  s.start_index = index or 1
  return s
end

function Shorts:enter()
  self.active = true
  if self.start_index then
    local i = self.start_index
    self.start_index = nil
    self:activate(i)
    local last = self.videos[#self.videos]
    if last then self:fetch_sequence(last.id) end
  end
end

function Shorts:resume()
  self.active = true
  if not self.seeded then self:seed() end
  if self.index > 0 and not (Player.current and self.videos[self.index] and Player.current.id == self.videos[self.index].id) then
    self:activate(self.index)
  end
  App.dirty = true
end

function Shorts:suspend() self.active = false end
function Shorts:leave() self.active = false; self:stop() end
function Shorts:leave_view() self.active = false; self:stop() end

function Shorts:stop()
  if self.playing then
    self.playing = false
    Player.loops, Player.no_history = self.prev_loops or false, false
    Player.stop()
  end
end

---------------------------------------------------------------------------------------------------------------------
-- data
---------------------------------------------------------------------------------------------------------------------
function Shorts:seed()
  if self.seeding then return end
  self.seeding = true
  self.state = "loading"
  Net.post("home", { seen = {}, fresh = false }, function(err, page)
    self.seeding = false
    if err then self.state = "error"; self.err = err; return end
    local all = {}
    for _, it in ipairs(page.items or {}) do
      if it.type == "video" then all[#all + 1] = it.video
      elseif it.type == "shorts" then for _, v in ipairs(it.videos) do all[#all + 1] = v end end
    end
    local shorts = {}
    for _, v in ipairs(all) do if v.isShort then shorts[#shorts + 1] = v end end
    self.seeded = true
    if #shorts > 0 then
      self.videos = shorts
      self:activate(1)
    end
    local seed = #shorts > 0 and shorts[#shorts].id or (all[1] and all[1].id)
    if seed then self:fetch_sequence(seed) elseif #shorts == 0 then self.state = "error" end
  end)
end

function Shorts:fetch_sequence(seed)
  if self.loading_seq then return end
  self.loading_seq = true
  Net.get("reel/seq", { seed = seed }, function(err, r)
    self.loading_seq = false
    if err then if #self.videos == 0 then self.state = "error"; self.err = err end; return end
    local known = {}
    for _, v in ipairs(self.videos) do known[v.id] = true end
    local fresh = {}
    for _, id in ipairs(r.ids or {}) do if not known[id] then fresh[#fresh + 1] = bare(id) end end
    local was_empty = #self.videos == 0
    for _, v in ipairs(fresh) do self.videos[#self.videos + 1] = v end
    if was_empty and #self.videos > 0 then self:activate(1) end
    if #self.videos == 0 then self.state = "error" end
    App.dirty = true
  end)
end

function Shorts:load_details(i)
  local v = self.videos[i]
  if not v or self.entries[v.id] or self.requested[v.id] then return end
  self.requested[v.id] = true
  Net.get("reel/item", { v = v.id }, function(err, entry)
    if err or not entry then return end
    self.entries[v.id] = entry
    local m = U.copy(v)
    for _, k in ipairs { "title", "channelName", "channelId", "channelAvatar" } do
      if entry.video and entry.video[k] and entry.video[k] ~= "" then m[k] = entry.video[k] end
    end
    local j
    for n, x in ipairs(self.videos) do if x.id == v.id then j = n; break end end
    if j then self.videos[j] = m end
    if Player.current and Player.current.id == m.id then Player.update_metadata(m) end
    App.dirty = true
  end)
end

function Shorts:activate(i)
  if i < 1 or i > #self.videos then return end
  self.index = i
  local v = self.videos[i]
  if not self.playing then self.prev_loops = Player.loops end
  self.playing = true
  Player.loops = true
  Player.no_history = true
  Player.play(v, nil, nil)
  self:load_details(i)
  self:load_details(i + 1)
  self.state = "ready"
  self.hud_until = love.timer.getTime() + 5
  if i >= #self.videos - 2 and #self.videos > 0 then self:fetch_sequence(self.videos[#self.videos].id) end
  App.dirty = true
end

---------------------------------------------------------------------------------------------------------------------
-- input
---------------------------------------------------------------------------------------------------------------------
function Shorts:action(act, kind)
  if kind == "release" then return false end
  local v = self.videos[self.index]
  if act == "down" then
    if self.index < #self.videos then self:activate(self.index + 1) end
    return true
  elseif act == "up" then
    if self.index > 1 then self:activate(self.index - 1) end
    return true
  elseif act == "a" then
    if self.state == "error" then self.seeded = false; self:seed(); return true end
    if Player.state == "failed" then Player.retry() else Player.toggle() end
    self.hud_until = love.timer.getTime() + 3
    return true
  elseif act == "x" and v then
    account.toggle_like(v)
    if store.is_liked(v.id) then App.toast(I.t("library.liked")) end
    return true
  elseif act == "y" and v then
    nav.video_menu(v)
    return true
  elseif act == "right" and v then
    Player.loops = self.prev_loops or false
    Player.no_history = false
    nav.play(v)
    return true
  elseif act == "start" and v and v.channelId and v.channelId ~= "" then
    account.toggle_subscribe({ id = v.channelId, name = v.channelName, avatar = v.channelAvatar })
    App.toast(store.is_subscribed(v.channelId) and I.t("video.subscribed") or I.t("video.subscribe"))
    return true
  elseif act == "b" and not self.rooted then
    App.pop()
    return true
  end
  return false
end

---------------------------------------------------------------------------------------------------------------------
-- draw
---------------------------------------------------------------------------------------------------------------------
function Shorts:update(dt)
  if self.playing then App.dirty = true end
end

function Shorts:draw()
  D.rect(0, 0, W, H, c.black)
  local x0, w = App.content_rect()
  local v = self.videos[self.index]
  if not v then
    if self.state == "error" then
      D.icon("cloud_off", x0 + w / 2 - 16, H / 2 - 36, 32, c.secondary)
      T.line(I.t("common.error"), x0, H / 2 + 4, w, 13, "medium", c.text, "center")
      T.line("Ⓐ " .. I.t("common.retry"), x0, H / 2 + 24, w, 12, "medium", c.link, "center")
    else
      D.spinner(x0 + w / 2, H / 2, 14, c.white)
    end
    return
  end
  -- the clip, centred
  local drawn_x, drawn_y, drawn_w, drawn_h = Engine.draw(x0, 0, w, H)
  if not drawn_x then
    local img = Img.get(v.thumbnail ~= "" and v.thumbnail or Img.thumb_url(v))
    if img then
      local iw, ih = img:getDimensions()
      local s = math.min(w / iw, H / ih)
      love.graphics.setColor(1, 1, 1, 0.6)
      love.graphics.draw(img, x0 + (w - iw * s) / 2, (H - ih * s) / 2, 0, s, s)
    end
    drawn_x, drawn_w = x0 + w / 2 - 76, 153
  end
  local st = Player.state
  if st == "loading" or st == "buffering" then D.spinner(x0 + w / 2, H / 2, 14, c.white)
  elseif st == "paused" then D.icon("play_arrow", x0 + w / 2 - 28, H / 2 - 28, 56, c.white, 0.9)
  elseif st == "failed" then
    local b = T.layout(Player.error_message or "", 150, { size = 11, weight = "medium", lines = 5, pitch = 15 })
    T.draw_block(b, x0 + w / 2 - b.w / 2, H / 2 - b.h / 2, c.text)
  end
  local dur = Player.duration()
  if dur > 0 then D.rect(drawn_x, H - 3, drawn_w * math.min(1, Player.position() / dur), 3, c.red) end
  -- left: channel, title
  local lx = x0 + 8
  local lw = (drawn_x - x0) - 16
  if lw > 40 then
    local img = Img.get(Img.avatar_url(v.channelAvatar, 64))
    if v.channelAvatar and v.channelAvatar ~= "" then D.avatar(img, lx + 12, H - 78, 24) end
    local nb = T.layout(v.channelName or "", lw - 30, { size = 11, weight = "bold", lines = 1 })
    T.draw_block(nb, lx + 30, H - 85, c.white)
    local tb = T.layout(v.title or "", lw, { size = 11, lines = 4, pitch = 14 })
    T.draw_block(tb, lx, H - 60, c.white)
    if v.channelId and v.channelId ~= "" and love.timer.getTime() < self.hud_until then
      T.print("Ⓢ " .. (store.is_subscribed(v.channelId) and I.t("video.subscribed") or I.t("video.subscribe")), lx, H - 22, 10, "bold", c.secondary)
    end
  end
  -- right: actions
  local rx = drawn_x + drawn_w + 14
  if rx + 40 < x0 + w then
    local entry = self.entries[v.id]
    local liked = store.is_liked(v.id)
    D.icon(liked and "thumb_up" or "thumb_up_outline", rx, 76, 26, liked and c.white or c.white)
    T.print(entry and entry.likes or "", rx, 104, 10, "medium", c.white)
    D.icon("video_library", rx, 130, 26, c.white)
    T.print(entry and entry.comments or "", rx, 158, 10, "medium", c.white)
    D.icon("more_vert", rx, 184, 26, c.white)
    if love.timer.getTime() < self.hud_until then
      T.print("Ⓧ", rx + 28, 82, 10, "bold", c.secondary)
      T.print("▶", rx + 28, 136, 10, "bold", c.secondary)
      T.print("Ⓨ", rx + 28, 190, 10, "bold", c.secondary)
    end
  end
  T.print(string.format("%d/%d", self.index, #self.videos), x0 + w - 44, 6, 10, "regular", c.secondary)
end

return Shorts
