-- small helpers shared by everything
local utf8 = require("utf8")
local U = {}

function U.clamp(v, lo, hi) if v < lo then return lo elseif v > hi then return hi end return v end
function U.lerp(a, b, t) return a + (b - a) * t end
function U.round(v) return math.floor(v + 0.5) end
function U.sign(v) if v > 0 then return 1 elseif v < 0 then return -1 end return 0 end

--- exponential smoothing that is independent of the frame rate: moves `cur` toward `target`
function U.damp(cur, target, rate, dt)
  local k = 1 - math.exp(-rate * dt)
  return cur + (target - cur) * k
end

function U.trim(s) return (s:gsub("^%s+", ""):gsub("%s+$", "")) end

function U.split(s, sep)
  local out = {}
  for part in (s .. sep):gmatch("(.-)" .. sep:gsub("%p", "%%%0")) do out[#out + 1] = part end
  return out
end

function U.urlencode(s)
  return (tostring(s):gsub("[^%w%-_%.~]", function(c) return string.format("%%%02X", c:byte()) end))
end

function U.query(params)
  if not params then return "" end
  local keys = {}
  for k, v in pairs(params) do
    if v ~= nil and v ~= "" and v ~= false then keys[#keys + 1] = k end
  end
  table.sort(keys)
  local parts = {}
  for _, k in ipairs(keys) do
    local v = params[k]
    if v == true then v = 1 end
    parts[#parts + 1] = U.urlencode(k) .. "=" .. U.urlencode(v)
  end
  if #parts == 0 then return "" end
  return "?" .. table.concat(parts, "&")
end

--- shell-quote for sh -c (single quotes)
function U.shq(s)
  return "'" .. tostring(s):gsub("'", "'\\''") .. "'"
end

function U.copy(t)
  local o = {}
  for k, v in pairs(t) do o[k] = v end
  return o
end

function U.index_of(list, pred)
  for i = 1, #list do
    if pred(list[i], i) then return i end
  end
  return nil
end

function U.map(list, fn)
  local out = {}
  for i = 1, #list do out[i] = fn(list[i], i) end
  return out
end

function U.append(dst, src)
  for i = 1, #src do dst[#dst + 1] = src[i] end
  return dst
end

--- 0:00 / 1:23 / 1:02:03 from seconds
function U.clock(sec)
  sec = math.max(0, math.floor((sec or 0) + 0.5))
  local h = math.floor(sec / 3600)
  local m = math.floor(sec / 60) % 60
  local s = sec % 60
  if h > 0 then return string.format("%d:%02d:%02d", h, m, s) end
  return string.format("%d:%02d", m, s)
end

--- "12:34" / "1:02:03" -> seconds
function U.parse_clock(str)
  if not str or str == "" then return 0 end
  local parts = {}
  for n in tostring(str):gmatch("%d+") do parts[#parts + 1] = tonumber(n) end
  local s = 0
  for _, n in ipairs(parts) do s = s * 60 + n end
  return s
end

--- number of UTF-8 characters
function U.ulen(s)
  local ok, n = pcall(utf8.len, s)
  if ok and n then return n end
  return #s
end

--- cut a UTF-8 string to at most n characters
function U.usub_head(s, n)
  if n <= 0 then return "" end
  local ok, off = pcall(utf8.offset, s, n + 1)
  if ok and off then return s:sub(1, off - 1) end
  return s
end

--- remove the last UTF-8 character
function U.ubackspace(s)
  if s == "" then return s end
  local off = utf8.offset(s, -1)
  if not off then return "" end
  return s:sub(1, off - 1)
end

function U.is_http_url(s) return type(s) == "string" and s:match("^https?://") ~= nil end

--- file helpers on absolute paths (outside love.filesystem)
function U.read_file(path)
  local f = io.open(path, "rb")
  if not f then return nil end
  local d = f:read("*a")
  f:close()
  return d
end

function U.write_file(path, data)
  local f = io.open(path, "wb")
  if not f then return false end
  f:write(data)
  f:close()
  return true
end

function U.file_exists(path)
  local f = io.open(path, "rb")
  if f then f:close() return true end
  return false
end

return U
