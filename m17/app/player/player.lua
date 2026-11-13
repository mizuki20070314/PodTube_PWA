-- The player: what is playing, the queue, quality / speed / captions / sleep timer, history and resume positions.
-- (PlayerManager, Subtitles, PlayHistory of the PWA's 07-player.js on top of the ffmpeg engine.)
local Engine = require("player.engine")
local Net = require("core.net")
local store = require("core.store")
local I = require("core.i18n")
local log = require("core.log")
local U = require("lib.util")

local P = {
  state = "idle",           -- idle | loading | playing | paused | buffering | ended | failed
  current = nil, info = nil, error_message = nil,
  queue = {}, queue_index = -1, playlist_id = nil, up_next = {}, chapters = {},
  loops = false, speed = 1, max_height = 360,
  shows_stats = false, sleep_ends_at = 0, sleep_at_end = false,
  subs = { tracks = {}, current = nil, cues = {}, loading = false, translate_to = nil },
}

local gen = 0                 -- bumped on every play(): late answers of an older one are ignored
local want_play = true
local started_at = 0          -- media position the engine was started at
local logged = false          -- the history entry of this play was written
local last_save = 0
local master_text, master_sid
local pending_seek
local seek_timer
local reporter = { failures = 0, last_failure = 0, current = nil }

-- keeping the picture in step with the sound (player/syncmon.lua decides, repair() acts)
local syncmon = require("player.syncmon")
local monitor = syncmon.new()     -- per video: what the monitor has done so far
local auto                        -- repairs in force for this video: { cap = max height, fps = frame rate cap, latency = tier }
local LATENCY_TIERS = { 120000, 250000, 500000 }    -- the device buffer (microseconds): a bigger one rides out under-runs
local function reset_auto() auto = { cap = nil, fps = nil, latency = 1 } end
reset_auto()
P.sync_fixes = 0                -- repairs made for the video that is playing

--- (re)reads the saved settings: called once the store is loaded
function P.reload_settings()
  P.speed = store.get("playbackSpeed") or 1
  P.max_height = store.get("maxQuality")
  if not P.max_height or P.max_height == 0 then P.max_height = 360 end
end
P.reload_settings()

---------------------------------------------------------------------------------------------------------------------
-- account history (acct/track/start + end), best effort
---------------------------------------------------------------------------------------------------------------------
local function newcpn()
  local chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
  local t = {}
  for i = 1, 16 do local k = math.random(1, #chars); t[i] = chars:sub(k, k) end
  return table.concat(t)
end

function reporter.started(video_id, position, reports_watch_time)
  local account = require("core.account")
  if not account.signed_in() then return end
  if reporter.failures >= 3 then
    if os.time() - reporter.last_failure < 600 then return end
    reporter.failures = 0
  end
  local c = reporter.current
  if c and c.video_id == video_id and c.stop == nil then return end
  local s = { video_id = video_id, cpn = newcpn(), start = math.max(0, position or 0), reports = reports_watch_time ~= false }
  reporter.current = s
  Net.post("acct/track/start", { v = video_id, cpn = s.cpn, position = s.start }, function(err, r)
    if err then
      if err.code ~= "network" then reporter.failures = reporter.failures + 1; reporter.last_failure = os.time() end
      return
    end
    reporter.failures = 0
    s.tracking = r
    if s.stop ~= nil then reporter.send_watched(s) end
  end, { auth = true })
end

function reporter.finished(position)
  local s = reporter.current
  if not s or s.stop ~= nil then return end
  s.stop = math.max(0, position or 0)
  reporter.current = nil
  if s.tracking then reporter.send_watched(s) end
end

function reporter.send_watched(s)
  if not s.reports or not s.tracking or s.stop - s.start < 5 then return end
  Net.post("acct/track/end", { wt = s.tracking.watchtimeURL, cpn = s.cpn, from = s.start, to = s.stop }, function() end, { auth = true })
end

---------------------------------------------------------------------------------------------------------------------
-- helpers
---------------------------------------------------------------------------------------------------------------------
local function set_state(s)
  if P.state == s then return end
  P.state = s
  App.dirty = true
  if P.on_state then P.on_state(s) end
end

local function indexOfId(list, id)
  for i, v in ipairs(list) do if v.id == id then return i end end
  return -1
end

local function fail(msg)
  P.error_message = msg
  Engine.stop()
  set_state("failed")
end

local function origin()
  return Net.base():match("^(https?://[^/]+)") or ""
end

local hls = require("player.hls")
local Downloads = require("core.downloads")
local parse_master, choose_variant = hls.parse_master, hls.choose_variant

--- The picture is delivered at a constant integer rate (ffmpeg `-r`): frame i of the pipe is shown at start + i / fps, so the
--- mapping is exact whatever the source rate is (a 29.97 source gets one repeated frame about every 33 s).
local function output_fps(src)
  local cap = math.min(store.get("videoFps") or 30, auto.fps or 99)
  local f = math.floor((src or 30) + 0.5)
  if f < 1 then f = 30 end
  while f > cap do f = math.floor(f / 2 + 0.5) end
  P.out_fps = f
  return f, tostring(f)
end

---------------------------------------------------------------------------------------------------------------------
-- opening a video
---------------------------------------------------------------------------------------------------------------------
local function start_engine(g, start)
  if g ~= gen then return end
  syncmon.new_run(monitor)
  if P.offline then
    local rec = P.offline
    local fps, fps_arg = output_fps(rec.fps or 30)
    local spec = { single = rec.file, start = start or 0, fps = fps, fps_arg = fps_arg, w = rec.w, h = rec.h, speed = P.speed,
      av_offset = (store.get("avOffsetMs") or 0) / 1000, latency = LATENCY_TIERS[auto.latency] }
    started_at = spec.start
    local ok, err = Engine.start(spec)
    if P.t then P.t.engine = love.timer.getTime() end
    if not ok then fail(err or "engine"); return end
    logged = false
    set_state("loading")
    if not want_play then Engine.set_paused(true) end
    return
  end
  if not master_text then return end
  local variants, audio = parse_master(master_text)
  local cap = P.max_height > 0 and P.max_height or 360
  if auto.cap and auto.cap < cap then cap = auto.cap end
  local v = choose_variant(variants, cap)
  if not v then fail(I.t("video.unavailable")); return end
  local a = audio[v.audio or ""]
  if not a then for _, x in pairs(audio) do a = x; break end end
  if not a then fail(I.t("video.unavailable")); return end
  local fps, fps_arg = output_fps(v.fps)
  local spec = {
    vurl = origin() .. v.uri, aurl = origin() .. a.uri, start = start or 0, fps = fps, fps_arg = fps_arg,
    w = v.w, h = v.h, speed = P.speed, av_offset = (store.get("avOffsetMs") or 0) / 1000, latency = LATENCY_TIERS[auto.latency],
  }
  P.variant = v
  started_at = spec.start
  local ok, err = Engine.start(spec)
  if P.t then P.t.engine = love.timer.getTime() end
  if not ok then fail(err or "engine"); return end
  logged = false
  set_state("loading")
  if not want_play then Engine.set_paused(true) end
end

local function load_master(g, start)
  local cap = P.max_height > 0 and P.max_height or 360
  local url = Net.base() .. "/api.cgi/hls/" .. P.info.sid .. "/master.m3u8?maxh=" .. cap .. "&hl=" .. store.hl()
  local pref = store.get("preferredAudio")
  if pref and pref ~= "" then url = url .. "&audio=" .. U.urlencode(pref) end
  Net.get_text(url, function(err, text)
    if g ~= gen then return end
    if err then fail(err.status == 410 and I.t("video.unavailable") or I.t("net.error")); return end
    master_text, master_sid = text, P.info.sid
    if P.t then P.t.master = love.timer.getTime() end
    start_engine(g, start)
  end)
end

function P.play(video, queue, playlist_id)
  reporter.finished(P.position())
  if queue then
    P.queue = queue
    P.queue_index = indexOfId(queue, video.id)
  elseif not P.current or P.current.id ~= video.id then
    local idx = indexOfId(P.queue, video.id)
    if idx >= 0 then P.queue_index = idx else P.queue, P.queue_index = {}, -1 end
  end
  if playlist_id then P.playlist_id = playlist_id elseif queue then P.playlist_id = nil end

  gen = gen + 1
  local g = gen
  Engine.stop()
  monitor = syncmon.new()
  reset_auto()
  P.sync_fixes = 0
  if not P.current or P.current.id ~= video.id then P.chapters = {} end
  P.current, P.info, P.error_message = video, nil, nil
  P.subs = { tracks = {}, current = nil, cues = {}, loading = false, translate_to = nil }
  want_play = true
  master_text = nil
  pending_seek = nil
  logged = false
  last_save = 0
  P.t = { play = love.timer.getTime() }
  P.retries = 0
  set_state("loading")
  if P.on_item then P.on_item() end

  P.offline = nil
  local rec = Downloads.record(video.id)
  if rec and U.file_exists(rec.file) then
    -- saved on this device: no network needed
    P.offline = rec
    P.info = { videoId = video.id, title = video.title, duration = rec.duration or 0, sid = "", captions = {}, audioTracks = {}, offline = true,
      heights = {}, storyboardSpec = "" }
    P.subs.tracks = {}
    if P.on_item then P.on_item() end
    local start = (not P.no_history) and store.resume_position(video.id) or 0
    start_engine(g, start)
    return
  end
  Net.get("play", { v = video.id }, function(err, info)
    if g ~= gen then return end
    if err then
      if err.code == "botcheck" then fail(I.t("video.botCheck"))
      elseif err.code == "network" then fail(I.t("net.error"))
      else fail(err.message ~= "" and err.message or I.t("video.unavailable")) end
      return
    end
    if info.isLive then fail(I.t("video.unavailable")); return end
    P.t.info = love.timer.getTime()
    P.info = info
    P.subs.tracks = info.captions or {}
    if store.get("captionsAlways") then
      local t = P.preferred_caption(P.subs.tracks)
      if t then P.select_caption(t) end
    end
    if P.on_item then P.on_item() end
    local start = (not P.no_history) and store.resume_position(video.id) or 0
    P.pending_resume = start
    load_master(g, start)
  end)
end

---------------------------------------------------------------------------------------------------------------------
-- transport
---------------------------------------------------------------------------------------------------------------------
function P.position()
  if Engine.is_active() then return Engine.position() end
  return pending_seek or started_at or 0
end

function P.duration()
  if P.info and P.info.duration and P.info.duration > 0 then return P.info.duration end
  return 0
end

function P.resume()
  want_play = true
  if P.state == "ended" then P.seek(0) return end
  Engine.set_paused(false)
  if P.state == "paused" then set_state("playing") end
end

function P.pause()
  want_play = false
  Engine.set_paused(true)
  if P.state == "playing" or P.state == "buffering" then set_state("paused") end
end

function P.toggle()
  if P.state == "playing" or P.state == "buffering" or (P.state == "loading" and want_play) then P.pause() else P.resume() end
end

local function restart_at(t)
  if not P.info or (not master_text and not P.offline) then return end
  local g = gen
  pending_seek = nil
  local d = P.duration()
  if d > 0 then t = math.min(t, math.max(0, d - 1)) end
  t = math.max(0, t)
  Engine.stop()
  started_at = t
  set_state(want_play and "loading" or "paused")
  start_engine(g, t)
end

--- the height of the next lighter picture than the one that is playing (nil when this is the lightest)
local function lighter_height()
  if not master_text or not P.variant then return nil end
  local variants = parse_master(master_text)
  local now_short = math.min(P.variant.w, P.variant.h)
  local best
  for _, v in ipairs(variants) do
    local short = math.min(v.w, v.h)
    if short < now_short and (not best or short > best) then best = short end
  end
  return best
end

--- the sync monitor found the picture out of step with the sound: start again from where the sound is now, with a lighter
--- picture / a bigger device buffer when the trouble came back soon
local function repair(act)
  local pos = Engine.position()
  P.sync_fixes = P.sync_fixes + 1
  local note
  if act.latency and auto.latency < #LATENCY_TIERS then auto.latency = auto.latency + 1 end
  if act.kind == "degrade" then
    local h = (not P.offline) and lighter_height() or nil
    local fps = P.out_fps or 30
    if h then
      auto.cap = h
      note = I.t("sync.lighter", h .. "p")
    elseif fps > 15 then
      auto.fps = fps > 24 and 24 or 15
      note = I.t("sync.lighterFps", auto.fps)
    end
  end
  log.warn(string.format("sync: %s (%s) at %.1fs - restarting; cap %s fps %s latency %d", act.kind, act.reason, pos, tostring(auto.cap),
    tostring(auto.fps), LATENCY_TIERS[auto.latency]))
  App.toast(note or I.t("sync.resync"))
  restart_at(pos)
end

--- jump to t (the engine restarts at that position)
function P.seek(t)
  if not P.info then return end
  restart_at(t)
end

--- accumulates quick successive seeks and restarts the engine once (a held D-pad)
function P.seek_soon(t)
  pending_seek = math.max(0, t)
  seek_timer = love.timer.getTime() + 0.35
  App.dirty = true
end

function P.pending_seek() return pending_seek end

function P.skip(d)
  local base = pending_seek or P.position()
  local t = base + d
  local dur = P.duration()
  if dur > 0 then t = math.min(t, dur - 1) end
  P.seek_soon(math.max(0, t))
end

function P.stop()
  reporter.finished(P.position())
  gen = gen + 1
  Engine.stop()
  P.current, P.info, P.queue, P.queue_index = nil, nil, {}, -1
  P.chapters, P.up_next = {}, {}
  P.subs = { tracks = {}, current = nil, cues = {}, loading = false, translate_to = nil }
  pending_seek = nil
  set_state("idle")
  if P.on_item then P.on_item() end
end

function P.retry()
  if P.current then P.play(P.current, #P.queue > 0 and P.queue or nil, P.playlist_id) end
end

---------------------------------------------------------------------------------------------------------------------
-- queue
---------------------------------------------------------------------------------------------------------------------
function P.next_candidate()
  if P.queue_index >= 0 and P.queue_index + 1 <= #P.queue then
    if P.queue[P.queue_index + 1] then return P.queue[P.queue_index + 1] end
  end
  if P.queue_index < 0 or #P.queue == 0 then
    for _, v in ipairs(P.up_next) do
      if not P.current or v.id ~= P.current.id then return v end
    end
  end
  return nil
end

function P.has_next() return P.next_candidate() ~= nil end
function P.has_previous() return P.queue_index > 1 end

function P.adopt_queue(list, current_id, playlist_id)
  local idx = indexOfId(list, current_id)
  if idx < 0 then return end
  P.queue, P.queue_index = list, idx
  if playlist_id then P.playlist_id = playlist_id end
end

function P.play_next()
  local nxt = P.next_candidate()
  if not nxt then return end
  if P.queue_index >= 0 and P.queue_index + 1 <= #P.queue then P.play(nxt, P.queue, P.playlist_id) else P.play(nxt) end
end

function P.play_previous()
  if P.position() > 5 then P.seek(0); return end
  if P.queue_index > 1 then P.play(P.queue[P.queue_index - 1], P.queue, P.playlist_id) else P.seek(0) end
end

function P.update_metadata(v)
  if P.current and P.current.id == v.id then P.current = v end
end

---------------------------------------------------------------------------------------------------------------------
-- quality / speed / sleep timer
---------------------------------------------------------------------------------------------------------------------
function P.set_max_height(h)
  P.max_height = h
  auto.cap = nil                     -- the user's choice replaces what the sync monitor lowered
  if P.info and master_text and not P.offline then
    -- the master is limited on the server by maxh=: ask for it again, then restart where we are
    local pos = P.position()
    local g = gen
    local url = Net.base() .. "/api.cgi/hls/" .. P.info.sid .. "/master.m3u8?maxh=" .. (h > 0 and h or 360) .. "&hl=" .. store.hl()
    Net.get_text(url, function(err, text)
      if g ~= gen or err then return end
      master_text = text
      restart_at(pos)
    end)
  end
end

--- "", "original" or a language tag: reloads the master with that audio choice and goes on from here
function P.select_audio(pref)
  store.set("preferredAudio", pref)
  if not P.info or P.offline then return end
  local pos = P.position()
  local g = gen
  local url = Net.base() .. "/api.cgi/hls/" .. P.info.sid .. "/master.m3u8?maxh=" .. (P.max_height > 0 and P.max_height or 360) .. "&hl=" .. store.hl()
  if pref ~= "" then url = url .. "&audio=" .. U.urlencode(pref) end
  Net.get_text(url, function(err, text)
    if g ~= gen or err then return end
    master_text = text
    restart_at(pos)
  end)
end

function P.set_speed(s)
  P.speed = s
  if P.info and (master_text or P.offline) then restart_at(P.position()) end
end

function P.set_sleep_timer(minutes, at_end)
  P.sleep_ends_at = 0
  P.sleep_at_end = at_end and true or false
  if minutes then P.sleep_ends_at = os.time() + minutes * 60 end
end

---------------------------------------------------------------------------------------------------------------------
-- captions
---------------------------------------------------------------------------------------------------------------------
function P.preferred_caption(list)
  local lang = store.hl()
  for _, t in ipairs(list) do if t.languageCode:sub(1, #lang) == lang and not t.isAuto then return t end end
  for _, t in ipairs(list) do if t.languageCode:sub(1, #lang) == lang then return t end end
  for _, t in ipairs(list) do if not t.isAuto then return t end end
  return list[1]
end

function P.select_caption(track, tlang)
  local s = P.subs
  s.current, s.translate_to, s.cues, s.loading = track, tlang, {}, true
  local sid = P.info and P.info.sid
  local g = gen
  Net.get("captions", { sid = sid, i = track.i, tlang = tlang }, function(err, r)
    if g ~= gen or P.subs.current ~= track then return end
    P.subs.loading = false
    if not err then P.subs.cues = r.cues or {} end
    App.dirty = true
  end)
end

function P.disable_captions()
  P.subs.current, P.subs.translate_to, P.subs.cues, P.subs.loading = nil, nil, {}, false
end

function P.caption_at(t)
  local cues = P.subs.cues
  if #cues == 0 then return nil end
  local lo, hi, found = 1, #cues, 0
  while lo <= hi do
    local mid = math.floor((lo + hi) / 2)
    if cues[mid][1] <= t then found = mid; lo = mid + 1 else hi = mid - 1 end
  end
  if found == 0 then return nil end
  for i = found, math.max(1, found - 2), -1 do
    if t >= cues[i][1] and t <= cues[i][2] then return cues[i][3] end
  end
  return nil
end

---------------------------------------------------------------------------------------------------------------------
-- frame loop
---------------------------------------------------------------------------------------------------------------------
local function item_ended(g)
  if g ~= gen or not P.current then return end
  store.update_progress(P.current.id, 0, P.duration())
  if P.loops then P.seek(0); return end
  reporter.finished(P.duration())
  set_state("ended")
  if P.sleep_at_end then P.sleep_at_end = false; return end
  if store.get("autoplay") then P.play_next() end
end

function P.update(dt)
  local now = love.timer.getTime()
  if pending_seek and now >= (seek_timer or 0) and Engine.is_active() then
    local t = pending_seek
    restart_at(t)
  elseif pending_seek and P.state == "ended" then
    restart_at(pending_seek)
  end
  if Engine.is_active() then
    if Engine.update(dt) then App.dirty = true end
    if store.get("autoSync") ~= false and (P.state == "playing" or P.state == "buffering") and not pending_seek then
      local h = Engine.health()
      local act = h and syncmon.step(monitor, now, h)
      if act then repair(act) end
    end
    local es = Engine.status()
    if es == "error" and P.state ~= "failed" then
      local m = U.read_file("/tmp/pt_ffmpeg.log") or ""
      log.warn("engine error; ffmpeg said:", (m:gsub("%s+$", "")):sub(-400))
      fail(I.t("video.unavailable"))
    elseif es == "ended" then
      local pos, dur = P.position(), P.duration()
      Engine.stop()
      if dur > 0 and pos < dur - 6 and (P.retries or 0) < 3 then
        -- the stream stopped before the end (the connection dropped): carry on from where it was
        P.retries = (P.retries or 0) + 1
        log.warn("player: stream ended early at", pos, "of", dur, "- reconnecting", P.retries)
        want_play = true
        restart_at(pos)
        set_state("buffering")
      elseif dur > 0 and pos < dur - 6 then
        fail(I.t("net.error"))
      else
        item_ended(gen)
      end
    elseif es == "playing" and Engine.has_picture() then
      if P.state == "loading" or P.state == "buffering" then set_state(want_play and "playing" or "paused") end
      if not logged and P.current then
        logged = true
        if P.t and P.t.engine then
          local now2 = love.timer.getTime()
          log.info(string.format("player: first picture %.2fs after play() (info %.2f, master %.2f, engine start %.2f, decode+network %.2f)",
            now2 - P.t.play, (P.t.info or 0) - P.t.play, (P.t.master or 0) - (P.t.info or 0), P.t.engine - (P.t.master or 0), now2 - P.t.engine))
        end
        if not P.no_history then
          local pos = P.position()
          store.add_history(P.current, pos, P.duration())
          if not store.get("pauseHistory") then reporter.started(P.current.id, pos, true) end
        end
      end
    elseif es == "buffering" then
      if P.state == "playing" then set_state("buffering") end
    elseif es == "paused" then
      if P.state == "playing" or P.state == "buffering" then set_state("paused") end
    end
    if (P.state == "playing" or P.state == "paused") and P.current and not P.no_history and now - last_save > 5 then
      last_save = now
      store.update_progress(P.current.id, P.position(), P.duration())
    end
  end
  if P.sleep_ends_at > 0 and os.time() >= P.sleep_ends_at then
    P.sleep_ends_at = 0
    P.pause()
  end
end

return P
