-- Thumbnails / avatars: memory cache (LRU) over a disk cache, loaded by worker threads, most recently shown first.
local log = require("core.log")
local store = require("core.store")

local Img = {}

local req_ch, res_ch
local workers = {}
local mem = {}          -- url -> {img=Image, use=tick}
local mem_n = 0
local MAX_MEM = 140
local failed = {}       -- url -> time of the failure
local inflight = {}     -- id -> url
local inflight_url = {}
local touch = {}        -- url -> {frame=, seq=}
local frame, seq, tick = 0, 0, 0
local next_id = 1
local cache_dir
local MAX_INFLIGHT = 3

function Img.init(n)
  req_ch = love.thread.getChannel("img_req")
  res_ch = love.thread.getChannel("img_res")
  love.filesystem.createDirectory("imgcache")
  cache_dir = store.dir .. "/imgcache"
  for i = 1, n or 3 do
    local t = love.thread.newThread("core/img_worker.lua")
    t:start()
    workers[i] = t
  end
  -- keep the cache at about 2500 pictures (a few tens of MB): the oldest go
  require("core.net").shell("cd '" .. cache_dir .. "' 2>/dev/null && ls -t | tail -n +2501 | xargs rm -f 2>/dev/null; echo ok", function() end)
end

function Img.shutdown()
  for _ = 1, #workers do req_ch:push("quit") end
end

--- Canonical URLs: small thumbnails by video id, avatars at a small size.
function Img.thumb_url(video)
  if video.id and #video.id == 11 then return "https://i.ytimg.com/vi/" .. video.id .. "/mqdefault.jpg" end
  return video.thumbnail
end

function Img.avatar_url(u, px)
  if not u or u == "" then return nil end
  px = px or 64
  local s, n = u:gsub("=s%d+[%-%w]*", "=s" .. px .. "-c-k-c0x00ffffff-no-rj", 1)
  if n == 0 and u:find("yt3.ggpht.com", 1, true) and not u:find("=", 1, true) then s = u .. "=s" .. px .. "-c-k-c0x00ffffff-no-rj" end
  return s
end

local function hash(url)
  local h = love.data.hash("md5", url)
  return (h:gsub(".", function(c) return string.format("%02x", c:byte()) end))
end

--- Returns the Image when it is ready (and keeps it loaded), otherwise nil and queues the download.
function Img.get(url)
  if not url or url == "" then return nil end
  local e = mem[url]
  tick = tick + 1
  if e then e.use = tick; return e.img end
  seq = seq + 1
  local t = touch[url]
  if not t then t = {}; touch[url] = t end
  t.frame, t.seq = frame, seq
  return nil
end

function Img.begin_frame()
  frame = frame + 1
  seq = 0
end

local function evict()
  while mem_n > MAX_MEM do
    local oldest_url, oldest = nil, math.huge
    for u, e in pairs(mem) do
      if e.use < oldest then oldest, oldest_url = e.use, u end
    end
    if not oldest_url then break end
    mem[oldest_url].img:release()
    mem[oldest_url] = nil
    mem_n = mem_n - 1
  end
end

local function start_next()
  local best_url, best_seq
  for u, t in pairs(touch) do
    if t.frame >= frame - 2 and not mem[u] and not inflight_url[u] and not failed[u] then
      if not best_seq or t.seq < best_seq then best_url, best_seq = u, t.seq end
    elseif t.frame < frame - 120 then
      touch[u] = nil
    end
  end
  if not best_url then return false end
  local id = next_id
  next_id = next_id + 1
  inflight[id] = best_url
  inflight_url[best_url] = true
  req_ch:push({ id = id, url = best_url, path = cache_dir .. "/" .. hash(best_url) .. ".jpg" })
  return true
end

function Img.update()
  if not res_ch then return end
  local got = 0
  while got < 2 do
    local r = res_ch:pop()
    if not r then break end
    local url = inflight[r.id]
    inflight[r.id] = nil
    if url then
      inflight_url[url] = nil
      if r.image then
        local ok, img = pcall(love.graphics.newImage, r.image)
        if ok then
          img:setFilter("linear", "linear")
          mem[url] = { img = img, use = tick }
          mem_n = mem_n + 1
          evict()
          got = got + 1
          if App then App.dirty = true end
        end
        r.image:release()
      else
        failed[url] = love.timer.getTime()
        log.warn("img:", r.err, url)
      end
    end
  end
  local n = 0
  for _ in pairs(inflight) do n = n + 1 end
  while n < MAX_INFLIGHT and start_next() do n = n + 1 end
  -- retry failures after a while
  local now = love.timer.getTime()
  for u, t in pairs(failed) do
    if now - t > 60 then failed[u] = nil end
  end
end

return Img
