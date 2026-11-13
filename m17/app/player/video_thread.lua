-- Video thread: raw yuv420p frames from the ffmpeg pipe -> ImageData planes (Y, U, V) -> channel.
-- A fixed pool of frame sets limits how far ffmpeg can run ahead: when every set is queued the thread stops reading, the pipe
-- fills up and ffmpeg waits.  The main thread hands used sets back through the "free" channel.
require("love.timer")
require("love.image")
require("love.filesystem")
local ffi = require("ffi")
local args = ...
local shared = require("player.shared")

ffi.cdef [[
int read(int fd, void *buf, unsigned int n);
int close(int fd);
]]
local C = ffi.C

local st = ffi.cast("pt_audio_state*", args.state:getFFIPointer())
local out = love.thread.getChannel(args.out)
local free = love.thread.getChannel(args.free)
local fd, w, h = args.fd, args.w, args.h
local cw, ch = math.floor((w + 1) / 2), math.floor((h + 1) / 2)
local MAX_SETS = args.sets or 8

local function read_full(ptr, n)
  local got = 0
  while got < n do
    local r = C.read(fd, ptr + got, n - got)
    if r <= 0 then return false end
    got = got + r
  end
  return true
end

local allocated = 0
local function new_set()
  allocated = allocated + 1
  return {
    love.image.newImageData(w, h, "r8"),
    love.image.newImageData(cw, ch, "r8"),
    love.image.newImageData(cw, ch, "r8"),
  }
end

local index = 0
while true do
  if st.cmd == shared.CMD_STOP then break end
  local set = free:pop()
  if not set and allocated < MAX_SETS then set = new_set() end
  if not set then
    love.timer.sleep(0.004)
  else
    local ok = read_full(ffi.cast("uint8_t*", set[1]:getFFIPointer()), w * h)
      and read_full(ffi.cast("uint8_t*", set[2]:getFFIPointer()), cw * ch)
      and read_full(ffi.cast("uint8_t*", set[3]:getFFIPointer()), cw * ch)
    if not ok then break end
    out:push({ set = set, index = index })
    index = index + 1
  end
end
out:push({ eof = true, frames = index })
C.close(fd)
