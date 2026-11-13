-- FeedList: the scrolling list of a Feed (video / channel / playlist rows and shorts shelves) with gamepad focus.
-- Custom rows ("pre") can sit in front of the feed's rows (the watch page puts its actions, channel and comments there).
local theme = require("ui.theme")
local D = require("ui.draw")
local T = require("ui.text")
local Img = require("core.img")
local store = require("core.store")
local I = require("core.i18n")
local U = require("lib.util")

local c = theme.c
local FL = {}
FL.__index = FL

local STYLES = {
  normal = { row = 80, thumb_w = 128, thumb_h = 72, title = 13, sub = 11, title_pitch = 17, sub_pitch = 14, lines = 2 },
  compact = { row = 62, thumb_w = 96, thumb_h = 54, title = 12, sub = 10, title_pitch = 15, sub_pitch = 13, lines = 2 },
}
local ROW_CHANNEL, ROW_SHELF, ROW_TEXT = 58, 124, 36

function FL.new(feed, opts)
  local l = setmetatable({}, FL)
  l.feed = feed
  l.o = opts or {}
  l.sel = 1
  l.sub = 1                 -- selected card inside a shorts shelf
  l.scroll = 0
  l.target = 0
  l.rows = {}
  l.version = -1
  l.total = 0
  l.w = 0
  l.focused = true
  l.view_h = 200
  l.st = STYLES[l.o.style or "normal"]
  l.pre = {}                -- custom rows: {h=, draw=function(c, x, y, w, focused, list), action=function(act, kind), activate=function()}
  return l
end

--- sets the custom rows that come before the feed
function FL:set_pre(rows)
  self.pre = rows or {}
  self.version = -1
  App.dirty = true
end

--- call when a custom row changed its height or content
function FL:invalidate() self.version = -1; App.dirty = true end

local function row_height(self, it)
  local t = it.type
  if t == "custom" then return it.h end
  if t == "video" or t == "playlist" then return self.st.row end
  if t == "channel" then return ROW_CHANNEL end
  if t == "shorts" then return ROW_SHELF end
  return ROW_TEXT
end

function FL:relayout(w)
  local feed = self.feed
  if feed.version == self.version and w == self.w then return end
  self.version, self.w = feed.version, w
  local y = 0
  local rows = {}
  for _, cr in ipairs(self.pre) do
    local h = type(cr.h) == "function" and cr.h(cr, w) or cr.h
    rows[#rows + 1] = { it = { type = "custom", c = cr }, y = y, h = h }
    y = y + h
  end
  for _, it in ipairs(feed.items) do
    local h = row_height(self, it)
    local row = { it = it, y = y, h = h }
    if it.type == "comment" then
      local cm = it.comment
      row.block = T.layout(cm.text or "", w - 58, { size = 11, lines = 6, pitch = 14 })
      row.head = T.layout((cm.author or "") .. ((cm.published and cm.published ~= "") and (" · " .. cm.published) or ""), w - 58, { size = 10, weight = "medium", lines = 1, pitch = 13 })
      row.h = 14 + row.block.h + 22 + ((cm.replyCount or 0) > 0 and 14 or 0)
    end
    rows[#rows + 1] = row
    y = y + row.h
  end
  self.rows = rows
  self.total = y
  if self.sel > #rows then self.sel = math.max(1, #rows) end
  -- never rest on a hidden (zero height) row
  local i = self.sel
  while rows[i] and rows[i].h == 0 do i = i + 1 end
  if not rows[i] then
    i = self.sel
    while rows[i] and rows[i].h == 0 do i = i - 1 end
  end
  if rows[i] then self.sel = i end
end

function FL:reset()
  self.sel, self.sub, self.scroll, self.target = 1, 1, 0, 0
  self.version = -1
end

function FL:selected()
  local r = self.rows[self.sel]
  if not r then return nil end
  local it = r.it
  if it.type == "shorts" then return it, it.videos[self.sub], self.sub end
  return it
end

local function ensure_visible(self)
  local r = self.rows[self.sel]
  if not r then return end
  local top, bot = r.y, r.y + r.h
  if top < self.target then self.target = top
  elseif bot > self.target + self.view_h then self.target = bot - self.view_h end
  local max = math.max(0, self.total - self.view_h)
  self.target = U.clamp(self.target, 0, max)
end

function FL:update(dt)
  self.scroll = U.damp(self.scroll, self.target, 16, dt)
  if math.abs(self.scroll - self.target) < 0.3 then self.scroll = self.target else App.dirty = true end
  local f = self.feed
  if f.state == "ready" and #self.rows - self.sel <= 4 then f:more() end
end

---------------------------------------------------------------------------------------------------------------------
-- input
---------------------------------------------------------------------------------------------------------------------
function FL:action(act, kind)
  if kind == "release" then return false end
  local f = self.feed
  if f.state == "error" and act == "a" and #self.rows == 0 then f:reload(true); return true end
  local n = #self.rows
  if n == 0 then return false end
  local r = self.rows[self.sel]
  local it = r.it
  if it.type == "custom" and it.c.action and it.c.action(act, kind) then App.dirty = true; return true end
  if act == "down" then
    local nx = self.sel + 1
    while self.rows[nx] and self.rows[nx].h == 0 do nx = nx + 1 end
    if self.rows[nx] then self.sel = nx; self.sub = 1; ensure_visible(self); App.dirty = true end
    return true
  elseif act == "up" then
    local nx = self.sel - 1
    while self.rows[nx] and self.rows[nx].h == 0 do nx = nx - 1 end
    if self.rows[nx] then self.sel = nx; self.sub = 1; ensure_visible(self); App.dirty = true; return true end
    return false
  elseif act == "left" or act == "right" then
    if it.type == "shorts" then
      local d = act == "left" and -1 or 1
      local ns = U.clamp(self.sub + d, 1, #it.videos)
      if ns ~= self.sub then self.sub = ns; App.dirty = true; return true end
      return act == "right"
    end
    return false
  elseif act == "r2" or (act == "r" and self.o.shoulder_page) then
    self.sel = math.min(n, self.sel + 3); self.sub = 1; ensure_visible(self); App.dirty = true
    return true
  elseif act == "l2" or (act == "l" and self.o.shoulder_page) then
    self.sel = math.max(1, self.sel - 3); self.sub = 1; ensure_visible(self); App.dirty = true
    return true
  elseif act == "a" then
    self:activate()
    return true
  elseif act == "x" then
    if it.type == "video" and self.o.on_more then self.o.on_more(it.video); return true end
    if it.type == "shorts" and self.o.on_more then self.o.on_more(it.videos[self.sub]); return true end
    return false
  end
  return false
end

function FL:activate()
  local r = self.rows[self.sel]
  if not r then return end
  local it, o = r.it, self.o
  if it.type == "custom" then
    if it.c.activate then it.c.activate() end
  elseif it.type == "video" and o.on_play then o.on_play(it.video, self)
  elseif it.type == "channel" and o.on_channel then o.on_channel(it.channel)
  elseif it.type == "playlist" and o.on_playlist then o.on_playlist(it.playlist)
  elseif it.type == "shorts" and o.on_shorts then o.on_shorts(it.videos, self.sub) end
end

---------------------------------------------------------------------------------------------------------------------
-- drawing
---------------------------------------------------------------------------------------------------------------------
local function badge(text, x, y, color, textcolor)
  local w = T.width(text, 10, "bold") + 8
  D.rect(x - w, y - 14, w, 13, color or c.badge, 3)
  T.print(text, x - w + 4, y - 14 + 0, 10, "bold", textcolor or c.white)
end

local function video_text_blocks(self, row, v, w)
  if row.tw == w and row.v == v then return end
  local st = self.st
  row.tw, row.v = w, v
  row.title = T.layout(v.title or "", w, { size = st.title, weight = "medium", lines = st.lines, pitch = st.title_pitch })
  row.sub1 = T.layout(v.channelName or "", w, { size = st.sub, lines = 1, pitch = st.sub_pitch })
  local meta = {}
  if v.views and v.views ~= "" then meta[#meta + 1] = v.views end
  if v.published and v.published ~= "" then meta[#meta + 1] = v.published end
  row.sub2 = T.layout(table.concat(meta, " · "), w, { size = st.sub, lines = 1, pitch = st.sub_pitch })
end

local function draw_video_row(self, row, x, y, w, focused)
  local v = row.it.video
  local st = self.st
  local tx = x + 8 + st.thumb_w + 9
  local tw = w - (tx - x) - 10
  video_text_blocks(self, row, v, tw)
  local img = Img.get(Img.thumb_url(v))
  local ty = y + (row.h - st.thumb_h) / 2
  if img then D.image(img, x + 8, ty, st.thumb_w, st.thumb_h, 6)
  else D.rect(x + 8, ty, st.thumb_w, st.thumb_h, c.thumb_ph, 6) end
  -- badge: duration / live / upcoming
  local btxt, bcolor = v.duration, nil
  if v.isLive then btxt, bcolor = I.t("video.live"), c.red
  elseif v.isUpcoming then btxt = I.t("video.upcoming") end
  if btxt and btxt ~= "" then badge(btxt, x + 8 + st.thumb_w - 4, ty + st.thumb_h - 3, bcolor) end
  local frac = store.progress(v.id)
  if frac and frac > 0.01 then
    D.rect(x + 8 + 4, ty + st.thumb_h - 3, (st.thumb_w - 8) * frac, 2, c.red)
  end
  local yy = ty + 1
  T.draw_block(row.title, tx, yy, c.text)
  yy = yy + row.title.h + 1
  T.draw_block(row.sub1, tx, yy, c.secondary)
  T.draw_block(row.sub2, tx, yy + st.sub_pitch, c.secondary)
end

local function draw_playlist_row(self, row, x, y, w)
  local p = row.it.playlist
  local st = self.st
  local tx = x + 8 + st.thumb_w + 9
  local tw = w - (tx - x) - 10
  if row.tw ~= tw then
    row.tw = tw
    row.title = T.layout(p.title or "", tw, { size = st.title, weight = "medium", lines = st.lines, pitch = st.title_pitch })
    local meta = {}
    if p.channelName and p.channelName ~= "" then meta[#meta + 1] = p.channelName end
    meta[#meta + 1] = I.t("video.playlists")
    row.sub1 = T.layout(table.concat(meta, " · "), tw, { size = st.sub, lines = 1, pitch = st.sub_pitch })
  end
  local ty = y + (row.h - st.thumb_h) / 2
  local img = Img.get(p.thumbnail)
  if img then D.image(img, x + 8, ty, st.thumb_w, st.thumb_h, 6) else D.rect(x + 8, ty, st.thumb_w, st.thumb_h, c.thumb_ph, 6) end
  D.rect(x + 8 + st.thumb_w - 36, ty + st.thumb_h - 20, 36, 20, { 0, 0, 0, 0.7 }, 0)
  D.icon("playlist_play", x + 8 + st.thumb_w - 34, ty + st.thumb_h - 19, 16, c.white)
  if p.videoCount and p.videoCount ~= "" then T.print(tostring(p.videoCount), x + 8 + st.thumb_w - 18, ty + st.thumb_h - 19, 10, "bold", c.white) end
  T.draw_block(row.title, tx, ty + 1, c.text)
  T.draw_block(row.sub1, tx, ty + 1 + row.title.h + 1, c.secondary)
end

local function draw_channel_row(self, row, x, y, w)
  local ch = row.it.channel
  local tx = x + 8 + 40 + 10
  local tw = w - (tx - x) - 10
  if row.tw ~= tw then
    row.tw = tw
    row.title = T.layout(ch.name or "", tw, { size = 13, weight = "medium", lines = 1, pitch = 17 })
    local sub = {}
    if ch.handle and ch.handle ~= "" then sub[#sub + 1] = ch.handle end
    if ch.subscribers and ch.subscribers ~= "" then sub[#sub + 1] = ch.subscribers end
    row.sub1 = T.layout(table.concat(sub, " · "), tw, { size = 11, lines = 1, pitch = 14 })
  end
  local img = Img.get(Img.avatar_url(ch.avatar, 96))
  D.avatar(img, x + 8 + 20, y + row.h / 2, 40)
  T.draw_block(row.title, tx, y + 10, c.text)
  T.draw_block(row.sub1, tx, y + 30, c.secondary)
  if store.is_subscribed(ch.id) then D.icon("check", x + w - 26, y + row.h / 2 - 8, 16, c.secondary) end
end

local SH_W, SH_H = 58, 100
local function draw_shelf_row(self, row, x, y, w, focused)
  local it = row.it
  D.icon("shorts", x + 8, y + 3, 16, c.red)
  T.print(I.t("shorts.title"), x + 28, y + 1, 12, "medium", c.text)
  -- cards: keep the selected one in view
  local sel = (self.rows[self.sel] == row) and self.sub or 1
  local first = math.max(1, sel - math.floor((w - 16) / (SH_W + 6)) + 1)
  if row.first == nil then row.first = 1 end
  row.first = U.damp(row.first, first, 14, love.timer.getDelta())
  local cx = x + 8 - (row.first - 1) * (SH_W + 6)
  D.clip(x, y, w, row.h)
  for i, v in ipairs(it.videos) do
    local px = cx + (i - 1) * (SH_W + 6)
    if px + SH_W > x - 4 and px < x + w + 4 then
      local img = Img.get(v.thumbnail or Img.thumb_url(v))
      if img then D.image_cover(img, px, y + 20, SH_W, SH_H) else D.rect(px, y + 20, SH_W, SH_H, c.thumb_ph, 6) end
      D.rect(px, y + 20 + SH_H - 22, SH_W, 22, { 0, 0, 0, 0.55 }, 0)
      row.blocks = row.blocks or {}
      local b = row.blocks[i]
      if not b then
        b = T.layout(v.title or "", SH_W - 6, { size = 9, weight = "medium", lines = 2, pitch = 10 })
        row.blocks[i] = b
      end
      T.draw_block(b, px + 3, y + 20 + SH_H - 21, c.white)
      if focused and i == sel then D.outline(px - 1, y + 19, SH_W + 2, SH_H + 2, c.white, 4, 2) end
    end
  end
  D.unclip()
end

local function draw_comment_row(self, row, x, y, w, focused)
  local cm = row.it.comment
  local img = Img.get(Img.avatar_url(cm.avatar, 64))
  D.avatar(img, x + 8 + 14, y + 8 + 14, 28)
  T.draw_block(row.head, x + 48, y + 6, cm.isOwner and c.white or c.secondary)
  T.draw_block(row.block, x + 48, y + 20, c.text)
  local fy = y + 20 + row.block.h + 3
  D.icon("thumb_up_outline", x + 48, fy, 13, c.secondary)
  T.print(tostring(cm.likes or ""), x + 66, fy, 10, "regular", c.secondary)
  if (cm.replyCount or 0) > 0 then
    T.print(I.t("comments.replies", tostring(cm.replyCount)), x + 48, fy + 14, 10, "medium", c.link)
  end
end

local function draw_state(self, x, y, w, h)
  local f = self.feed
  local cx, cy = x + w / 2, y + h / 2
  if f.state == "loading" or (f.state == "idle" and #self.rows == 0) then
    D.spinner(cx, cy - 6, 12)
    T.line(I.t("common.loading"), x, cy + 14, w, 12, "regular", c.secondary, "center")
  elseif f.state == "error" then
    D.icon("cloud_off", cx - 16, cy - 40, 32, c.secondary)
    local msg = f.error and f.error.message or I.t("common.error")
    if f.error and f.error.code == "network" then msg = I.t("net.error") end
    T.line(I.t("common.error"), x + 10, cy - 2, w - 20, 13, "medium", c.text, "center")
    T.line(msg, x + 10, cy + 18, w - 20, 11, "regular", c.secondary, "center")
    if f.error and f.error.code == "network" then
      local hb = T.layout(I.t("net.tunnelHint"), w - 40, { size = 10, lines = 3, pitch = 13 })
      T.draw_block(hb, x + (w - hb.w) / 2, cy + 36, c.secondary)
      T.line("Ⓐ " .. I.t("common.retry"), x + 10, cy + 36 + hb.h + 6, w - 20, 12, "medium", c.link, "center")
    else
      T.line("Ⓐ " .. I.t("common.retry"), x + 10, cy + 40, w - 20, 12, "medium", c.link, "center")
    end
  elseif f.state == "empty" then
    D.icon(self.o.empty_icon or "search", cx - 16, cy - 36, 32, c.secondary)
    T.line(self.o.empty_text or I.t("common.empty"), x + 10, cy + 6, w - 20, 13, "medium", c.secondary, "center")
    if self.o.empty_detail then
      local b = T.layout(self.o.empty_detail, w - 40, { size = 11, lines = 3, pitch = 15 })
      T.draw_block(b, x + (w - b.w) / 2, cy + 26, c.secondary)
    end
  end
end

function FL:draw(x, y, w, h, focused)
  self:relayout(w)
  self.view_h = h
  ensure_visible(self)
  D.clip(x, y, w, h)
  local f = self.feed
  if #self.rows == 0 or (self.total or 0) <= 0 then
    draw_state(self, x, y, w, h)
  else
    local top = self.scroll
    for i, row in ipairs(self.rows) do
      local ry = y + row.y - top
      if ry + row.h >= y and ry <= y + h then
        if not row.shown and self.o.on_display then
          row.shown = true
          if row.it.type == "video" then self.o.on_display(row.it.video) end
        end
        local isel = (i == self.sel)
        if isel and focused and row.it.type ~= "custom" then
          D.rect(x + 3, ry + 1, w - 6, row.h - 2, c.surface, 8, 0.9)
          if row.it.type ~= "shorts" then D.outline(x + 3, ry + 1, w - 6, row.h - 2, c.white, 8, 1.5, 0.9) end
        end
        local t = row.it.type
        if t == "custom" then row.it.c.draw(row.it.c, x, ry, w, isel and focused, self)
        elseif t == "video" then draw_video_row(self, row, x, ry, w, isel and focused)
        elseif t == "playlist" then draw_playlist_row(self, row, x, ry, w)
        elseif t == "channel" then draw_channel_row(self, row, x, ry, w)
        elseif t == "shorts" then draw_shelf_row(self, row, x, ry, w, isel and focused)
        elseif t == "comment" then draw_comment_row(self, row, x, ry, w, isel and focused)
        end
      end
    end
    if f.loading_more then
      local ry = y + self.total - top
      if ry < y + h then D.spinner(x + w / 2, ry + 14, 8) end
    end
    D.scrollbar(x + w - 3, y, h, self.scroll, self.total, h)
  end
  D.unclip()
end

return FL
