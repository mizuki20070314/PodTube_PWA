-- Watch: the playing video.  Two layouts of one screen (PWA: 08b-watch.js):
--   full     the picture fills the screen, controls come and go
--   details  the picture is small on the left with title and meta; on the right the actions, channel, description,
--            comments, "up next" and the related videos
local theme = require("ui.theme")
local D = require("ui.draw")
local T = require("ui.text")
local HUD = require("ui.hud")
local Feed = require("core.feed")
local FeedList = require("ui.feedlist")
local Player = require("player.player")
local Engine = require("player.engine")
local chapters = require("player.chapters")
local Storyboard = require("player.storyboard")
local Net = require("core.net")
local Img = require("core.img")
local store = require("core.store")
local account = require("core.account")
local nav = require("core.nav")
local I = require("core.i18n")
local U = require("lib.util")

local c = theme.c
local W, H = theme.W, theme.H
local LW = 210                  -- width of the left pane in the details layout

local Watch = {}
Watch.__index = Watch

---------------------------------------------------------------------------------------------------------------------
-- construction
---------------------------------------------------------------------------------------------------------------------
--- opts: queue, playlist_id, resume (the video is already the player's current one: do not restart it)
function Watch.new(video, opts)
  opts = opts or {}
  local self = setmetatable({ name = "watch", update_always = true, captures_shoulders = true }, Watch)
  self.video = video
  self.opts = opts
  self.mode = "full"
  self.hud_until = love.timer.getTime() + 4
  self.hint_until = love.timer.getTime() + 7
  self.hud_alpha = 1
  self.seek_count = 0
  self.expanded = false
  self.disliked = false
  self.act_sel = 1
  self.ch_sel = 1
  self.info = nil
  self.first_comment = nil
  self.channel = nil
  self.cstat = { w = 0 }
  local me = self
  self.related = Feed.new({
    endpoint = "next",
    fetch_first = function(cb) me:fetch_related(cb) end,
  })
  self.list = FeedList.new(self.related, {
    style = "compact", shoulder_page = false,
    on_play = function(v) me:play_video(v) end,
    on_more = function(v) nav.video_menu(v) end,
    on_channel = function(ch) nav.open_channel(ch.id, ch.name) end,
    on_playlist = function(p) nav.open_playlist(p.id, p.title) end,
    empty_text = "",
  })
  self.pre = self:make_pre()
  self.list:set_pre(self.pre)
  return self
end

function Watch:enter()
  local resume = self.opts.resume and Player.current and Player.current.id == self.video.id
  if not resume then
    Player.play(self.video, self.opts.queue, self.opts.playlist_id)
  else
    self.mode = "details"
  end
  self:load_content(Player.current or self.video)
  if resume then Player.resume() end
end

function Watch:resume() App.dirty = true end

function Watch:load_content(v)
  self.video = v
  self.info, self.first_comment, self.channel = nil, nil, nil
  self.expanded, self.disliked = false, false
  self.related:clear()
  self.list:reset()
  self.list:set_pre(self.pre)
  self.related:reload()
  App.dirty = true
end

function Watch:play_video(v)
  Player.play(v, nil, nil)
  self:load_content(v)
  self.mode = "full"
  self.hud_until = love.timer.getTime() + 3
end

---------------------------------------------------------------------------------------------------------------------
-- data
---------------------------------------------------------------------------------------------------------------------
function Watch:fetch_related(cb)
  local v = self.video
  if not v then cb(nil, { items = {} }); return end
  local vid = v.id
  Net.get("watch", { v = vid, list = Player.playlist_id }, function(err, w)
    if not self.video or self.video.id ~= vid then return end
    if err then cb(err); return end
    self:apply_info(w)
    local page = w.related or { items = {} }
    if w.queue and #w.queue > 0 then
      local after = {}
      for i = (w.queueIndex or 0) + 2, #w.queue do after[#after + 1] = { type = "video", video = w.queue[i] } end
      for _, it in ipairs(page.items or {}) do after[#after + 1] = it end
      page = { items = after, sections = page.sections, continuation = page.continuation }
    end
    cb(nil, page)
  end)
end

function Watch:apply_info(w)
  self.info = w
  local v = self.video
  local merged = U.copy(v)
  if w.title and w.title ~= "" then merged.title = w.title end
  if w.channel then
    self.channel = w.channel
    merged.channelId, merged.channelName, merged.channelAvatar = w.channel.id, w.channel.name, w.channel.avatar
  end
  self.video = merged
  Player.update_metadata(merged)
  store.update_history_video(merged)
  store.channel_learn(merged.channelId, merged.channelName, merged.channelAvatar)
  local nxt = {}
  if w.autoplay then nxt[#nxt + 1] = w.autoplay end
  for _, it in ipairs((w.related and w.related.items) or {}) do
    if it.type == "video" then nxt[#nxt + 1] = it.video end
  end
  Player.up_next = nxt
  Player.chapters = chapters.parse(w.description)
  if w.queue and #w.queue > 0 then Player.adopt_queue(w.queue, w.videoId, Player.playlist_id) end
  if w.commentsToken then
    Net.post("comments", { token = w.commentsToken }, function(err, page)
      if err or not self.info or self.info ~= w then return end
      self.first_comment_page = page
      self.first_comment = page.comments and page.comments[1] or nil
      self.list:invalidate()
    end)
  end
  local cur = merged
  account.load_watch_state(cur, function(s)
    if not s or not self.video or self.video.id ~= cur.id then return end
    if s.likeStatus then
      self.disliked = s.likeStatus == "DISLIKE"
      store.set_liked(cur, s.likeStatus == "LIKE")
    end
    local ch = self.channel
    if ch and s.subscribed ~= nil and (not s.channelId or s.channelId == ch.id) then
      if s.subscribed then store.subscribe(ch) else store.unsubscribe(ch.id) end
    end
    App.dirty = true
  end)
  self.list:invalidate()
end

---------------------------------------------------------------------------------------------------------------------
-- the custom rows of the details list
---------------------------------------------------------------------------------------------------------------------
local function pill(x, y, w, h, label, icon, focused, on, color)
  D.rect(x, y, w, h, on and c.chip_sel or c.surface_high, h / 2)
  local fg = on and c.chip_sel_text or (color or c.text)
  local ix = x + 9
  if icon then D.icon(icon, ix, y + (h - 16) / 2, 16, fg); ix = ix + 20 end
  if label and label ~= "" then T.line(label, ix, y + (h - 14) / 2, w - (ix - x) - 9, 11, "medium", fg) end
  if focused then D.focus_ring(x, y, w, h, h / 2) end
end

function Watch:action_buttons()
  local v = self.video
  local liked = store.is_liked(v.id)
  local like_label = (self.info and self.info.likeText and self.info.likeText ~= "") and self.info.likeText or I.t("video.like")
  local saved = store.is_watch_later(v.id)
  local Downloads = require("core.downloads")
  local dl_label, dl_icon = I.t("video.download"), "file_download"
  if Downloads.record(v.id) then dl_label, dl_icon = I.t("downloads.saved"), "offline_pin"
  elseif Downloads.is_downloading(v.id) then dl_label = math.floor(Downloads.fraction(v.id) * 100) .. "%" end
  return {
    { id = "like", icon = liked and "thumb_up" or "thumb_up_outline", label = like_label, on = liked },
    { id = "dislike", icon = self.disliked and "thumb_down" or "thumb_down_outline", label = "", on = self.disliked },
    { id = "save", icon = saved and "bookmark" or "playlist_add", label = I.t("video.save"), on = saved },
    { id = "share", icon = "share_outline", label = I.t("video.share"), on = false },
    { id = "download", icon = dl_icon, label = dl_label, on = Downloads.record(v.id) ~= nil },
  }
end

function Watch:button_width(b)
  return 28 + (b.label ~= "" and math.floor(T.width(b.label, 11, "medium")) + 4 or 0) + (b.label ~= "" and 12 or 0)
end

function Watch:press_button(b)
  local v = self.video
  if b.id == "like" then
    self.disliked = false
    local was = store.is_liked(v.id)
    account.set_like(v, was and "none" or "like")
    if not was then App.toast(I.t("library.liked")) end
  elseif b.id == "dislike" then
    self.disliked = not self.disliked
    if account.signed_in() then account.set_like(v, self.disliked and "dislike" or "none")
    elseif self.disliked and store.is_liked(v.id) then store.toggle_like(v) end
  elseif b.id == "save" then
    local saved = store.is_watch_later(v.id)
    App.open_sheet({ title = I.t("video.save"), items = {
      { label = saved and I.t("video.removeWatchLater") or I.t("video.watchLater"), icon = "watch_later",
        on = function() account.set_watch_later(v, not saved); App.toast(saved and I.t("video.removed") or I.t("video.saved")) end },
      { label = I.t("video.addToPlaylist"), icon = "playlist_add", on = function() nav.playlist_picker(v) end },
    } })
  elseif b.id == "share" then
    nav.show_link(v)
  elseif b.id == "download" then
    nav.download_menu(v)
  end
  self.list:invalidate()
end

function Watch:make_pre()
  local me = self
  local rows = {}

  -- status line when the playback failed
  rows[#rows + 1] = {
    h = function(row, w) return Player.state == "failed" and 46 or 0 end,
    draw = function(row, x, y, w, focused)
      if Player.state ~= "failed" then return end
      D.rect(x + 6, y + 4, w - 12, 38, c.surface, 8)
      D.icon("cloud_off", x + 12, y + 14, 18, c.secondary)
      T.line(Player.error_message or I.t("video.unavailable"), x + 36, y + 7, w - 48, 11, "medium", c.text)
      T.line("Ⓐ " .. I.t("common.retry"), x + 36, y + 24, w - 48, 11, "medium", c.link)
      if focused then D.outline(x + 5, y + 3, w - 10, 40, c.white, 8, 2) end
    end,
    activate = function() Player.retry(); me:load_content(me.video) end,
  }

  -- actions: like / dislike / save / share
  rows[#rows + 1] = {
    h = 40,
    draw = function(row, x, y, w, focused)
      local bx = x + 8
      for i, b in ipairs(me:action_buttons()) do
        local bw = me:button_width(b)
        pill(bx, y + 6, bw, 26, b.label, b.icon, focused and me.act_sel == i, b.on)
        bx = bx + bw + 6
      end
    end,
    action = function(act, kind)
      local n = #me:action_buttons()
      if act == "left" and me.act_sel > 1 then me.act_sel = me.act_sel - 1; return true end
      if act == "right" and me.act_sel < n then me.act_sel = me.act_sel + 1; return true end
      return false
    end,
    activate = function() me:press_button(me:action_buttons()[me.act_sel]) end,
  }

  -- channel
  rows[#rows + 1] = {
    h = function(row, w) return (me.channel or (me.video and me.video.channelName ~= "" and me.video.channelName)) and 48 or 0 end,
    draw = function(row, x, y, w, focused)
      local ch = me.channel or { id = me.video.channelId, name = me.video.channelName, avatar = me.video.channelAvatar }
      if not ch.name or ch.name == "" then return end
      local img = Img.get(Img.avatar_url(ch.avatar, 96))
      D.avatar(img, x + 8 + 16, y + 24, 32)
      local subbed = ch.id and store.is_subscribed(ch.id)
      local label = subbed and I.t("video.subscribed") or I.t("video.subscribe")
      local bw = math.floor(T.width(label, 11, "medium")) + 22
      local tw = w - 8 - 40 - bw - 20
      local b1 = T.layout(ch.name, tw, { size = 12, weight = "medium", lines = 1 })
      T.draw_block(b1, x + 48, y + 8, c.text)
      T.line(ch.subscribers or "", x + 48, y + 25, tw, 10, "regular", c.secondary)
      local px = x + w - bw - 10
      D.rect(px, y + 11, bw, 26, subbed and c.surface_high or c.chip_sel, 13)
      T.line(label, px + 11, y + 11 + 6, bw - 22, 11, "medium", subbed and c.text or c.chip_sel_text)
      if focused then
        if me.ch_sel == 1 then D.outline(x + 4, y + 3, tw + 48, 42, c.white, 8, 2)
        else D.focus_ring(px, y + 11, bw, 26, 13) end
      end
    end,
    action = function(act)
      if act == "left" and me.ch_sel == 2 then me.ch_sel = 1; return true end
      if act == "right" and me.ch_sel == 1 then me.ch_sel = 2; return true end
      return false
    end,
    activate = function()
      local ch = me.channel
      if me.ch_sel == 2 and ch then
        account.toggle_subscribe(ch)
        App.toast(store.is_subscribed(ch.id) and I.t("video.subscribed") or I.t("video.subscribe"))
      else
        nav.open_owner(me.video)
      end
    end,
  }

  -- description
  local function desc_block(w)
    local text = (me.info and me.info.description) or ""
    local key = (me.expanded and "e" or "c") .. w
    if me.dblock_key ~= key or me.dblock_text ~= text then
      me.dblock_key, me.dblock_text = key, text
      me.dblock = T.layout(text, w - 20, { size = 11, lines = me.expanded and 14 or 3, pitch = 14, multiline = true })
    end
    return me.dblock
  end
  rows[#rows + 1] = {
    h = function(row, w)
      if not me.info or (me.info.description or "") == "" then return 0 end
      return desc_block(w).h + 34
    end,
    draw = function(row, x, y, w, focused)
      if not me.info or (me.info.description or "") == "" then return end
      local b = desc_block(w)
      D.rect(x + 6, y + 3, w - 12, b.h + 28, c.surface, 8)
      local meta = {}
      if me.info.viewsShort and me.info.viewsShort ~= "" then meta[#meta + 1] = me.expanded and (me.info.views or me.info.viewsShort) or me.info.viewsShort end
      if me.info.date and me.info.date ~= "" then meta[#meta + 1] = me.info.date end
      T.line(table.concat(meta, " · "), x + 16, y + 7, w - 32, 10, "medium", c.text)
      T.draw_block(b, x + 16, y + 21, c.secondary)
      T.print(me.expanded and I.t("common.less") or I.t("common.more"), x + 16, y + 21 + b.h + 1, 10, "medium", c.text)
      if focused then D.outline(x + 5, y + 2, w - 10, b.h + 30, c.white, 8, 2) end
    end,
    activate = function() me.expanded = not me.expanded; me.list:invalidate() end,
  }

  -- comments
  rows[#rows + 1] = {
    h = function(row, w) return (me.info and me.info.commentsToken) and 54 or 0 end,
    draw = function(row, x, y, w, focused)
      if not (me.info and me.info.commentsToken) then return end
      D.rect(x + 6, y + 3, w - 12, 48, c.surface, 8)
      T.print(I.t("video.comments"), x + 16, y + 7, 11, "bold", c.text)
      T.print(me.info.commentCount or "", x + 16 + T.width(I.t("video.comments"), 11, "bold") + 8, y + 8, 10, "regular", c.secondary)
      D.icon("chevron_right", x + w - 30, y + 6, 18, c.secondary)
      local cm = me.first_comment
      if cm then
        local img = Img.get(Img.avatar_url(cm.avatar, 48))
        D.avatar(img, x + 24, y + 36, 16)
        local b = T.layout(cm.text or "", w - 70, { size = 10, lines = 2, pitch = 12 })
        T.draw_block(b, x + 38, y + 24, c.secondary)
      end
      if focused then D.outline(x + 5, y + 2, w - 10, 50, c.white, 8, 2) end
    end,
    activate = function() me:open_comments() end,
  }

  -- up next + the autoplay switch
  rows[#rows + 1] = {
    h = 30,
    draw = function(row, x, y, w, focused)
      T.print(I.t("video.nextUp"), x + 12, y + 8, 12, "bold", c.text)
      local on = store.get("autoplay")
      local sx = x + w - 44
      T.print(I.t("video.autoplay"), sx - 8 - T.width(I.t("video.autoplay"), 10, "regular"), y + 9, 10, "regular", c.secondary)
      D.rect(sx, y + 8, 34, 16, on and c.red or c.surface_high, 8)
      D.circle(on and sx + 25 or sx + 9, y + 16, 6.5, c.white)
      if focused then D.outline(x + 5, y + 3, w - 10, 26, c.white, 8, 2) end
    end,
    activate = function() store.set("autoplay", not store.get("autoplay")); me.list:invalidate() end,
  }
  return rows
end

function Watch:open_comments()
  local info = self.info
  if not info or not info.commentsToken then return end
  App.push(require("screens.comments").new(info.commentsToken, info.commentSortTokens, info.commentCount, self.first_comment_page, self.video))
end

---------------------------------------------------------------------------------------------------------------------
-- menus
---------------------------------------------------------------------------------------------------------------------
local function quality_label(h) return h == 0 and I.t("player.auto") or (h .. "p") end

function Watch:show_settings()
  local items = {}
  local ch = Player.chapters
  if #ch >= 2 then
    local cur = chapters.current(ch, Player.position())
    items[#items + 1] = { label = I.t("player.chapters"), icon = "format_list_bulleted", sub = cur and cur.title or nil, on = function() self:show_chapters() end }
  end
  items[#items + 1] = { label = I.t("player.quality"), icon = "hd", sub = quality_label(Player.max_height), on = function() self:show_quality() end }
  items[#items + 1] = { label = I.t("player.speed"), icon = "speed", sub = Player.speed == 1 and I.t("player.normal") or (Player.speed .. "x"), on = function() self:show_speed() end }
  items[#items + 1] = { label = I.t("player.captions"), icon = "closed_caption",
    sub = Player.subs.current and Player.subs.current.name or I.t("player.captionsOff"), on = function() self:show_captions() end }
  local tracks = (Player.info and Player.info.audioTracks) or {}
  if #tracks > 1 then
    local pref = store.get("preferredAudio")
    local cur
    for _, t in ipairs(tracks) do if pref ~= "" and t.id:sub(1, #pref) == pref then cur = t end end
    items[#items + 1] = { label = I.t("player.audio"), icon = "audiotrack", sub = cur and cur.name or I.t("player.audioAuto"), on = function() self:show_audio(tracks) end }
  end
  items[#items + 1] = { label = I.t("player.loop"), icon = "repeat", checked = Player.loops, on = function() Player.loops = not Player.loops end }
  items[#items + 1] = { label = I.t("player.sleep"), icon = "timer", sub = (Player.sleep_ends_at > 0 or Player.sleep_at_end) and "●" or I.t("player.sleepOff"), on = function() self:show_sleep() end }
  items[#items + 1] = { label = I.t("player.stats"), icon = "analytics", checked = Player.shows_stats, on = function() Player.shows_stats = not Player.shows_stats end }
  App.open_sheet({ title = I.t("player.settings"), items = items })
end

function Watch:show_chapters()
  local now = chapters.current(Player.chapters, Player.position())
  local items = {}
  for _, ch in ipairs(Player.chapters) do
    items[#items + 1] = { label = ch.title, sub = U.clock(ch.start), checked = now and ch.start == now.start, on = function() Player.seek(ch.start) end }
  end
  App.open_sheet({ title = I.t("player.chapters"), items = items, width = 380 })
end

function Watch:show_quality()
  local items = {}
  for _, h in ipairs { 144, 240, 360, 480 } do
    items[#items + 1] = { label = quality_label(h), checked = Player.max_height == h, on = function() Player.set_max_height(h) end }
  end
  App.open_sheet({ title = I.t("player.quality"), items = items })
end

function Watch:show_speed()
  local items = {}
  for _, s in ipairs { 0.25, 0.5, 0.75, 1, 1.25, 1.5, 1.75, 2 } do
    items[#items + 1] = { label = s == 1 and I.t("player.normal") or (s .. "x"), checked = Player.speed == s, on = function() Player.set_speed(s) end }
  end
  App.open_sheet({ title = I.t("player.speed"), items = items })
end

function Watch:show_captions()
  local items = { { label = I.t("player.captionsOff"), checked = Player.subs.current == nil, on = function() Player.disable_captions() end } }
  for _, t in ipairs(Player.subs.tracks) do
    items[#items + 1] = { label = t.name, checked = Player.subs.current ~= nil and Player.subs.current.i == t.i, on = function() Player.select_caption(t) end }
  end
  App.open_sheet({ title = I.t("player.captions"), items = items })
end

function Watch:show_audio(tracks)
  local pref = store.get("preferredAudio")
  local items = { { label = I.t("player.audioAuto"), checked = pref == "", on = function() Player.select_audio("") end } }
  for _, t in ipairs(tracks) do
    items[#items + 1] = { label = t.name or t.id, checked = pref ~= "" and t.id:sub(1, #pref) == pref,
      on = function() Player.select_audio(t.isDefault and "original" or (t.id:match("^[^.]+") or t.id)) end }
  end
  App.open_sheet({ title = I.t("player.audio"), items = items })
end

function Watch:toggle_captions()
  if Player.subs.current then
    Player.disable_captions()
    App.toast(I.t("player.captionsOff"))
  else
    local t = Player.preferred_caption(Player.subs.tracks)
    if t then Player.select_caption(t); App.toast(t.name) else App.toast(I.t("player.captionsOff")) end
  end
end

function Watch:show_sleep()
  local items = { { label = I.t("player.sleepOff"), on = function() Player.set_sleep_timer(nil, false) end } }
  for _, m in ipairs { 10, 15, 30, 45, 60 } do
    items[#items + 1] = { label = I.t("player.sleepMinutes", tostring(m)), on = function() Player.set_sleep_timer(m, false) end }
  end
  items[#items + 1] = { label = I.t("player.sleepEnd"), on = function() Player.set_sleep_timer(nil, true) end }
  App.open_sheet({ title = I.t("player.sleep"), items = items })
end

function Watch:more_menu()
  local extra = {
    { label = I.t("player.settings"), icon = "settings", on = function() self:show_settings() end },
    { label = I.t("common.close"), icon = "close", danger = true, on = function() Player.stop(); App.pop() end },
  }
  nav.video_menu(self.video, extra)
end

---------------------------------------------------------------------------------------------------------------------
-- input
---------------------------------------------------------------------------------------------------------------------
function Watch:show_hud(secs)
  self.hud_until = love.timer.getTime() + (secs or 3.5)
  App.dirty = true
end

function Watch:set_mode(m)
  self.mode = m
  App.dirty = true
  if m == "full" then self:show_hud(3) end
end

function Watch:step_seek(act, kind)
  if kind == "press" then self.seek_count = 0 else self.seek_count = self.seek_count + 1 end
  local n = self.seek_count
  local step = n < 4 and 10 or (n < 14 and 30 or 60)
  Player.skip(act == "left" and -step or step)
end

function Watch:action(act, kind)
  if kind == "release" then return false end
  if self.mode == "full" then return self:action_full(act, kind) end
  return self:action_details(act, kind)
end

function Watch:action_full(act, kind)
  if act == "a" then
    if Player.state == "failed" then Player.retry() else Player.toggle() end
    self:show_hud(); return true
  elseif act == "left" or act == "right" then
    self:step_seek(act, kind); self:show_hud(); return true
  elseif act == "up" then
    self:show_hud(); return true
  elseif act == "down" or act == "b" or act == "start" then
    self:set_mode("details"); return true
  elseif act == "l" then Player.play_previous(); self:show_hud(); return true
  elseif act == "r" then Player.play_next(); self:show_hud(); return true
  elseif act == "x" then self:toggle_captions(); self:show_hud(); return true
  elseif act == "y" then self:show_settings(); return true
  elseif act == "l2" or act == "r2" then
    local ch = Player.chapters
    if #ch >= 2 then
      local pos = Player.position()
      local tgt
      if act == "r2" then for _, x in ipairs(ch) do if x.start > pos + 1 then tgt = x.start; break end end
      else for i = #ch, 1, -1 do if ch[i].start < pos - 3 then tgt = ch[i].start; break end end end
      if tgt then Player.seek(tgt) end
    else
      Player.skip(act == "l2" and -60 or 60)
    end
    self:show_hud(); return true
  elseif act == "select" then
    Player.shows_stats = not Player.shows_stats; return true
  end
  return false
end

function Watch:action_details(act, kind)
  if act == "b" then App.pop(); return true end
  if act == "start" then self:set_mode("full"); return true end
  if act == "y" then self:show_settings(); return true end
  if self.list:action(act, kind) then return true end
  if act == "left" or act == "right" then self:step_seek(act, kind); return true end
  if act == "l" then Player.play_previous(); return true end
  if act == "r" then Player.play_next(); return true end
  if act == "x" then self:more_menu(); return true end
  if act == "select" then Player.toggle(); return true end
  return true
end

---------------------------------------------------------------------------------------------------------------------
-- update / draw
---------------------------------------------------------------------------------------------------------------------
function Watch:update(dt)
  -- the player moved on by itself (autoplay / queue)
  local cur = Player.current
  if cur and self.video and cur.id ~= self.video.id then
    self:load_content(cur)
  end
  if self.mode == "details" then self.list:update(dt) end
  local now = love.timer.getTime()
  local want = (now < self.hud_until or Player.state == "paused" or Player.state == "ended" or Player.state == "failed") and 1 or 0
  if math.abs(self.hud_alpha - want) > 0.01 then
    self.hud_alpha = U.damp(self.hud_alpha, want, 12, dt)
    App.dirty = true
  else
    self.hud_alpha = want
  end
  if Player.state == "playing" or Player.state == "loading" or Player.state == "buffering" then App.dirty = true end
end

local function status_overlay(x, y, w, h)
  local st = Player.state
  if st == "loading" or st == "buffering" then
    D.spinner(x + w / 2, y + h / 2, math.min(14, h / 4), c.white)
  elseif st == "failed" then
    D.icon("cloud_off", x + w / 2 - 10, y + 12, 20, c.secondary)
    local b = T.layout(Player.error_message or "", w - 16, { size = 10, lines = 4, pitch = 12 })
    T.draw_block(b, x + (w - b.w) / 2, y + 36, c.text)
  elseif st == "ended" then
    D.icon("refresh", x + w / 2 - 14, y + h / 2 - 14, 28, c.white)
  end
end

function Watch:storyboard()
  local info = Player.info
  if not info or info.isLive or not info.storyboardSpec or info.storyboardSpec == "" then return nil end
  local d = Player.duration()
  if d <= 0 then return nil end
  local sc = self.sb_cache
  if sc and sc.id == info.videoId and sc.d == d then return sc.v end
  local sb = Storyboard.new(info.storyboardSpec, d)
  self.sb_cache = { id = info.videoId, d = d, v = sb }
  return sb
end

function Watch:hud_state()
  local pos = Player.position()
  local pend = Player.pending_seek()
  local preview
  if pend then
    local sb = self:storyboard()
    if sb then
      local lvl = sb:level(160)
      local cell = sb:cell_at(lvl, pend)
      preview = { img = Img.get(sb:sheet_url(lvl, cell.sheet)), lvl = lvl, cell = cell }
    end
  end
  local chap = chapters.current(Player.chapters, pend or pos)
  local hint
  if love.timer.getTime() < self.hint_until then
    hint = "Ⓐ " .. I.t("player.hintToggle") .. "   ◀ ▶ " .. I.t("player.hintSeek") .. "   Ⓧ CC   Ⓨ " .. I.t("player.settings") .. "   Ⓑ " .. I.t("player.hintBack")
  end
  return {
    title = self.video and self.video.title, position = pos, pending = pend, duration = Player.duration(), state = Player.state,
    chapters = Player.chapters, captions_on = Player.subs.current ~= nil, has_prev = Player.has_previous(), has_next = Player.has_next(),
    speed = Player.speed, alpha = self.hud_alpha, chapter = chap and chap.title, hint = hint, preview = preview,
    cue = Player.subs.current and Player.caption_at(pos) or nil,
  }
end

function Watch:draw_full()
  D.rect(0, 0, W, H, c.black)
  local drawn = Engine.draw(0, 0, W, H)
  if Player.state == "failed" then
    HUD.draw_error(Player.error_message or I.t("video.unavailable"), "Ⓐ " .. I.t("common.retry") .. "   Ⓑ " .. I.t("player.hintBack"))
  else
    if not drawn and Player.state ~= "failed" then
      local b = T.layout(self.video and self.video.title or "", 380, { size = 13, weight = "medium", lines = 2, pitch = 18 })
      T.draw_block(b, (W - b.w) / 2, H / 2 + 26, c.secondary)
    end
    HUD.draw(self:hud_state())
  end
  if Player.shows_stats then HUD.draw_stats(self:stats()) end
end

function Watch:stats()
  local s = Engine.stats() or {}
  s.speed = Player.speed
  s.fixes = Player.sync_fixes
  s.ui_fps = App.draw_fps or 0
  s.mem_mb = collectgarbage("count") / 1024
  return s
end

function Watch:draw_details()
  -- left pane: picture, progress, title, meta
  local vx, vy, vw, vh = 6, 6, LW - 8, math.floor((LW - 8) * 9 / 16)
  D.rect(vx, vy, vw, vh, c.black, 6)
  D.clip(vx, vy, vw, vh)
  Engine.draw(vx, vy, vw, vh)
  status_overlay(vx, vy, vw, vh)
  D.unclip()
  local pos, dur = Player.position(), Player.duration()
  D.progress(vx, vy + vh + 4, vw, 3, dur > 0 and pos / dur or 0, c.red, c.surface_high, 1)
  local icon = (Player.state == "playing" or Player.state == "buffering") and "pause" or "play_arrow"
  D.icon(icon, vx - 1, vy + vh + 10, 16, c.text)
  T.print(U.clock(pos) .. " / " .. U.clock(dur), vx + 17, vy + vh + 12, 10, "medium", c.text)
  local ty = vy + vh + 30
  local v = self.video
  if v then
    local tb = T.layout(v.title or "", LW - 14, { size = 13, weight = "medium", lines = 4, pitch = 17 })
    T.draw_block(tb, 8, ty, c.text)
    local meta = {}
    if v.channelName and v.channelName ~= "" then meta[#meta + 1] = v.channelName end
    local mb = T.layout(table.concat(meta, " · "), LW - 14, { size = 10, lines = 1, pitch = 13 })
    T.draw_block(mb, 8, ty + tb.h + 3, c.secondary)
    local m2 = {}
    local i = self.info
    if i then
      if i.viewsShort and i.viewsShort ~= "" then m2[#m2 + 1] = i.viewsShort end
      if i.date and i.date ~= "" then m2[#m2 + 1] = i.date end
    elseif v.views then
      if v.views ~= "" then m2[#m2 + 1] = v.views end
      if v.published and v.published ~= "" then m2[#m2 + 1] = v.published end
    end
    local mb2 = T.layout(table.concat(m2, " · "), LW - 14, { size = 10, lines = 1, pitch = 13 })
    T.draw_block(mb2, 8, ty + tb.h + 17, c.secondary)
  end
  D.rect(LW + 1, 0, 1, H, c.divider)
  -- right pane
  self.list:draw(LW + 3, 0, W - LW - 3, H, true)
  if Player.shows_stats then HUD.draw_stats(self:stats()) end
end

function Watch:draw()
  if self.mode == "full" then self:draw_full() else self:draw_details() end
end

return Watch
