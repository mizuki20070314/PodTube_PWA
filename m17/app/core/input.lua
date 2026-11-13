-- Input: reads /dev/input/event* directly (evdev through FFI) and turns raw events into logical buttons.
--
-- logical buttons: up down left right a b x y l r l2 r2 start select menu volup voldown
-- A "source" is a raw input: "k:<code>" for a key, "a:<code>:-" / "a:<code>:+" for an axis pushed one way.
-- Several sources can feed one button (the D-pad of this machine reports both keys and axes); the button is down while
-- any of its sources is down.
local ffi = require("ffi")
local log = require("core.log")

ffi.cdef [[
int open(const char *path, int flags);
int close(int fd);
int read(int fd, void *buf, unsigned int count);
int ioctl(int fd, unsigned long request, ...);
typedef struct { long tv_sec; long tv_usec; uint16_t type; uint16_t code; int32_t value; } pt_input_event;
typedef struct { int32_t value, minimum, maximum, fuzz, flat, resolution; } pt_absinfo;
]]

local O_RDONLY, O_NONBLOCK, O_CLOEXEC = 0, 0x800, 0x80000
local EV_KEY, EV_ABS = 1, 3

local Input = {}

Input.ACTIONS = { "up", "down", "left", "right", "a", "b", "x", "y", "l", "r", "l2", "r2", "start", "select", "menu" }
Input.REPEATING = { up = true, down = true, left = true, right = true }

-- defaults: the Linux key codes this machine reports (see /proc/bus/input/devices); the real layout is set in
-- Settings > Buttons because the codes do not say which key is printed A or B.
Input.DEFAULT_MAP = {
  up = { "k:103", "a:0gpio-keys:1:-" }, down = { "k:108", "a:0gpio-keys:1:+" },
  left = { "k:105", "a:0gpio-keys:0:-" }, right = { "k:106", "a:0gpio-keys:0:+" },
  a = { "k:30" }, b = { "k:48" }, x = { "k:45" }, y = { "k:21" },
  l = { "k:38" }, r = { "k:19" }, l2 = { "k:44" }, r2 = { "k:46" },
  start = { "k:28", "k:315" }, select = { "k:54", "k:314" }, menu = { "k:107" },
  volup = { "k:115" }, voldown = { "k:114" },
}

local devices = {}
local bind = {}            -- source -> action
local srcdown = {}         -- source -> true
local actdown = {}         -- action -> count of sources down
local held = {}            -- action -> seconds held (for repeat)
local nextrep = {}         -- action -> time of the next repeat
local queue = {}           -- pending events {action, kind}
local capture              -- function(source) when the mapper wants the raw input
local ev = ffi.new("pt_input_event[16]")
local absinfo = ffi.new("pt_absinfo[1]")
local clock = 0

Input.REPEAT_DELAY = 0.34
Input.REPEAT_RATE = 0.075

local function push(action, kind)
  queue[#queue + 1] = { action = action, kind = kind }
end

function Input.set_map(map)
  bind = {}
  for action, sources in pairs(map or Input.DEFAULT_MAP) do
    for _, s in ipairs(sources) do bind[s] = action end
  end
  Input.map = map or Input.DEFAULT_MAP
end

function Input.open_all()
  for i = 0, 9 do
    local path = "/dev/input/event" .. i
    local fd = ffi.C.open(path, O_RDONLY + O_NONBLOCK + O_CLOEXEC)
    if fd >= 0 then
      local d = { path = path, fd = fd, axes = {}, name = "dev" .. i }
      local nbuf = ffi.new("char[64]")
      -- EVIOCGNAME(63) = _IOR('E', 0x06, char[63])
      if ffi.C.ioctl(fd, 0x803f4506, nbuf) > 0 then d.name = ffi.string(nbuf) end
      devices[#devices + 1] = d
    end
  end
  log.info("input: opened", #devices, "evdev devices")
end

function Input.device_names()
  local t = {}
  for _, d in ipairs(devices) do t[#t + 1] = d.path:sub(-6) .. '=' .. d.name end
  return table.concat(t, ', ')
end

function Input.close_all()
  for _, d in ipairs(devices) do ffi.C.close(d.fd) end
  devices = {}
end

local function axis_range(d, code)
  local r = d.axes[code]
  if r then return r end
  -- EVIOCGABS(code) = _IOR('E', 0x40 + code, struct input_absinfo)
  local req = 0x80184540 + code
  if ffi.C.ioctl(d.fd, req, absinfo) == 0 then
    r = { min = absinfo[0].minimum, max = absinfo[0].maximum }
  else
    r = { min = -1, max = 1 }
  end
  d.axes[code] = r
  return r
end

local function source_changed(src, down)
  if down then
    if srcdown[src] then return end
    srcdown[src] = true
  else
    if not srcdown[src] then return end
    srcdown[src] = nil
  end
  if down and capture then
    local cb = capture
    capture = nil
    cb(src)
    return
  end
  local action = bind[src]
  if not action then return end
  if down then
    actdown[action] = (actdown[action] or 0) + 1
    if actdown[action] == 1 then
      held[action] = 0
      nextrep[action] = Input.REPEAT_DELAY
      push(action, "press")
    end
  else
    actdown[action] = (actdown[action] or 1) - 1
    if actdown[action] <= 0 then
      actdown[action] = nil
      held[action] = nil
      nextrep[action] = nil
      push(action, "release")
    end
  end
end

local function handle(d, type_, code, value)
  if type_ == EV_KEY then
    if value == 2 then return end -- the kernel's own auto-repeat: we do our own
    source_changed("k:" .. code, value ~= 0)
  elseif type_ == EV_ABS then
    local r = axis_range(d, code)
    local mid = (r.min + r.max) / 2
    local span = (r.max - r.min) / 2
    if span <= 0 then return end
    local rel = (value - mid) / span
    local neg, pos = "a:" .. d.name .. ":" .. code .. ":-", "a:" .. d.name .. ":" .. code .. ":+"
    source_changed(neg, rel < -0.5)
    source_changed(pos, rel > 0.5)
  end
end

--- Reads everything that is pending and returns the events (press / repeat / release).
function Input.poll(dt)
  clock = clock + dt
  for _, d in ipairs(devices) do
    while true do
      local n = ffi.C.read(d.fd, ev, ffi.sizeof(ev))
      if n <= 0 then break end
      for i = 0, n / 16 - 1 do
        local e = ev[i]
        handle(d, e.type, e.code, e.value)
      end
    end
  end
  for action, t in pairs(held) do
    t = t + dt
    held[action] = t
    if Input.REPEATING[action] and nextrep[action] and t >= nextrep[action] then
      nextrep[action] = nextrep[action] + Input.REPEAT_RATE
      push(action, "repeat")
    end
  end
  local out = queue
  queue = {}
  return out
end

--- Injects a logical button (debug channel / self tests)
function Input.inject(action, kind)
  if kind == "tap" or kind == nil then
    push(action, "press")
    push(action, "release")
  else
    push(action, kind)
  end
end

function Input.is_down(action) return actdown[action] ~= nil end

--- The next raw source is handed to `cb` instead of being turned into a button (button mapping screen).
function Input.capture_next(cb) capture = cb end
function Input.cancel_capture() capture = nil end
function Input.capturing() return capture ~= nil end

function Input.source_label(src)
  local code = src:match("^k:(%d+)$")
  if code then return "KEY " .. code end
  local name, acode, dir = src:match("^a:(.-):(%d+):([+-])$")
  if name then return "AXIS " .. name .. " " .. acode .. dir end
  return src
end

Input.set_map(nil)

return Input
