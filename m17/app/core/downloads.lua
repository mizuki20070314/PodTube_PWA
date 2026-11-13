-- Downloads (11-downloads.js in the PWA): save the HLS streams of a video as an .mp4 on the SD card and play it offline.
-- ffmpeg copies the streams (no re-encoding); the progress comes back through a pipe.
local ffi = require("ffi")
local Proc = require("core.proc")
local Net = require("core.net")
local store = require("core.store")
local I = require("core.i18n")
local log = require("core.log")
local hls = require("player.hls")
local U = require("lib.util")
local json = require("lib.json")

ffi.cdef [[
int read(int fd, void *buf, unsigned int n);
int fcntl(int fd, int cmd, ...);
int close(int fd);
]]

local D = { supported = true }

local records = {}          -- persisted: {id, video, height, bytes, duration, file, date}
local queue = {}            -- waiting {video, height}
local active                -- {video, height, proc, tmp, final, fraction, duration, buf}
local dir, meta_path

local O_NONBLOCK, F_SETFL, F_GETFL = 0x800, 4, 3

local function persist()
  U.write_file(meta_path, json.encode(records))
end

function D.init()
  dir = store.dir .. "/downloads"
  love.filesystem.createDirectory("downloads")
  meta_path = store.dir .. "/downloads.json"
  local txt = U.read_file(meta_path)
  if txt and txt ~= "" then
    local ok, v = pcall(json.decode, txt)
    if ok and type(v) == "table" then records = v end
  end
  -- leftovers of an interrupted download
  os.execute("rm -f '" .. dir .. "'/*.part.mp4 2>/dev/null")
end

function D.records() return records end
function D.record(id)
  for _, r in ipairs(records) do if r.id == id then return r end end
  return nil
end

function D.is_downloading(id)
  if active and active.video.id == id then return true end
  for _, q in ipairs(queue) do if q.video.id == id then return true end end
  return false
end

function D.fraction(id)
  if active and active.video.id == id then return active.fraction or 0 end
  return 0
end

function D.pending_count()
  return #queue + (active and 1 or 0)
end

function D.total_bytes()
  local n = 0
  for _, r in ipairs(records) do n = n + (r.bytes or 0) end
  return n
end

local function changed() store.notify() end

function D.remove(id)
  for i, r in ipairs(records) do
    if r.id == id then
      os.remove(r.file)
      table.remove(records, i)
      persist(); changed()
      return
    end
  end
end

function D.cancel(id)
  for i, q in ipairs(queue) do
    if q.video.id == id then table.remove(queue, i); changed(); return end
  end
  if active and active.video.id == id then
    Proc.kill(active.proc, 9)
    active.cancelled = true
  end
end

local function finish(ok, msg)
  local a = active
  active = nil
  if a.proc then Proc.close_fds(a.proc) end
  if ok then
    os.remove(a.final)
    os.rename(a.tmp, a.final)
    local f = io.open(a.final, "rb")
    local size = 0
    if f then size = f:seek("end"); f:close() end
    for i, r in ipairs(records) do if r.id == a.video.id then table.remove(records, i); break end end
    table.insert(records, 1, { id = a.video.id, video = store.slim(a.video), height = a.height, w = a.w, h = a.h, fps = a.fps, bytes = size, duration = a.duration, file = a.final, date = os.time() })
    persist()
    App.toast(I.t("downloads.done"))
  else
    os.remove(a.tmp)
    if not a.cancelled then App.toast(I.t("downloads.failed") .. (msg and (" (" .. msg .. ")") or "")) end
  end
  changed()
  D.pump()
end

local function spawn(a, master_text, info)
  local variants, audio = hls.parse_master(master_text)
  local v = hls.choose_variant(variants, a.height)
  local au
  if v then au = audio[v.audio or ""] end
  if not au then for _, x in pairs(audio) do au = x; break end end
  if not v or not au then finish(false, "no stream"); return end
  local origin = Net.base():match("^(https?://[^/]+)") or ""
  a.height = math.min(v.w, v.h)
  a.w, a.h, a.fps = v.w, v.h, v.fps
  a.tmp = dir .. "/" .. a.video.id .. ".part.mp4"
  a.final = dir .. "/" .. a.video.id .. ".mp4"
  local argv = require("player.ffargs").download_argv(origin .. v.uri, origin .. au.uri, a.tmp, true)
  local proc, err = Proc.spawn(argv, { pipes = { { fd = 3 } }, log = "/tmp/pt_download.log" })
  if not proc then finish(false, err); return end
  a.proc = proc
  a.buf = ""
  local fd = proc.fds[3]
  local fl = ffi.C.fcntl(fd, F_GETFL)
  ffi.C.fcntl(fd, F_SETFL, ffi.cast("int", bit.bor(fl, O_NONBLOCK)))
  a.fd = fd
  a.chunk = ffi.new("uint8_t[?]", 2048)
  log.info("downloads: started", a.video.id, "height", a.height)
end

function D.pump()
  if active or #queue == 0 then return end
  local job = table.remove(queue, 1)
  active = { video = job.video, height = job.height, fraction = 0, duration = 0 }
  local a = active
  changed()
  Net.get("play", { v = job.video.id }, function(err, info)
    if active ~= a then return end
    if err or info.isLive then finish(false, err and err.message or "live"); return end
    a.duration = info.duration or 0
    local url = Net.base() .. "/api.cgi/hls/" .. info.sid .. "/master.m3u8?maxh=" .. job.height .. "&hl=" .. store.hl()
    Net.get_text(url, function(err2, text)
      if active ~= a then return end
      if err2 then finish(false, err2.message); return end
      spawn(a, text, info)
    end)
  end)
end

--- queue a download of `video` at (at most) `height` pixels
function D.start(video, height)
  if D.record(video.id) or D.is_downloading(video.id) then App.toast(I.t("downloads.already")); return end
  if video.isLive or video.isUpcoming then App.toast(I.t("downloads.unavailable")); return end
  queue[#queue + 1] = { video = video, height = height or store.get("maxQuality") or 360 }
  App.toast(I.t("downloads.started"))
  changed()
  D.pump()
end

--- reads the progress lines of the running ffmpeg and notices its end
function D.update(dt)
  local a = active
  if not a or not a.proc then return end
  while true do
    local n = ffi.C.read(a.fd, a.chunk, 2048)
    if n <= 0 then break end
    a.buf = a.buf .. ffi.string(a.chunk, n)
  end
  for line in a.buf:gmatch("[^\n]+\n") do
    local us = line:match("^out_time_us=(%d+)") or line:match("^out_time_ms=(%d+)")
    if us and a.duration > 0 then
      a.fraction = math.min(1, tonumber(us) / 1e6 / a.duration)
      App.dirty = true
    end
  end
  a.buf = a.buf:match("[^\n]*$") or ""
  if Proc.reap(a.proc) then
    local f = io.open(a.tmp or "", "rb")
    local ok = false
    if f then
      local size = f:seek("end")
      f:close()
      ok = size > 20000 and not a.cancelled
    end
    finish(ok, (not ok) and "ffmpeg" or nil)
  end
end

return D
