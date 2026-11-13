-- Minimal JSON for LuaJIT: decode(str) / encode(value).  UTF-8 only.
local M = {}

local null = setmetatable({}, { __tostring = function() return "null" end })
M.null = null

---------------------------------------------------------------------------------------------------------------------
-- encode
---------------------------------------------------------------------------------------------------------------------
local escmap = { ['"'] = '\\"', ['\\'] = '\\\\', ['\b'] = '\\b', ['\f'] = '\\f', ['\n'] = '\\n', ['\r'] = '\\r', ['\t'] = '\\t' }

local function esc(s)
  return (s:gsub('[%c"\\]', function(c) return escmap[c] or string.format("\\u%04x", c:byte()) end))
end

local function is_array(t)
  local n = 0
  for k in pairs(t) do
    if type(k) ~= "number" or k < 1 or k % 1 ~= 0 then return false end
    if k > n then n = k end
  end
  return n == #t
end

local function enc(v, out, depth)
  local tv = type(v)
  if v == null or v == nil then out[#out + 1] = "null"
  elseif tv == "boolean" then out[#out + 1] = v and "true" or "false"
  elseif tv == "number" then
    if v ~= v or v == math.huge or v == -math.huge then out[#out + 1] = "null"
    elseif v % 1 == 0 and v > -1e15 and v < 1e15 then out[#out + 1] = string.format("%d", v)
    else out[#out + 1] = string.format("%.14g", v) end
  elseif tv == "string" then out[#out + 1] = '"' .. esc(v) .. '"'
  elseif tv == "table" then
    if depth > 40 then error("json: too deep") end
    if is_array(v) then
      out[#out + 1] = "["
      for i = 1, #v do
        if i > 1 then out[#out + 1] = "," end
        enc(v[i], out, depth + 1)
      end
      out[#out + 1] = "]"
    else
      out[#out + 1] = "{"
      local first = true
      local keys = {}
      for k in pairs(v) do if type(k) == "string" then keys[#keys + 1] = k end end
      table.sort(keys)
      for _, k in ipairs(keys) do
        if not first then out[#out + 1] = "," end
        first = false
        out[#out + 1] = '"' .. esc(k) .. '":'
        enc(v[k], out, depth + 1)
      end
      out[#out + 1] = "}"
    end
  else
    out[#out + 1] = "null"
  end
end

function M.encode(v)
  local out = {}
  enc(v, out, 0)
  return table.concat(out)
end

---------------------------------------------------------------------------------------------------------------------
-- decode
---------------------------------------------------------------------------------------------------------------------
local byte, find, sub, char = string.byte, string.find, string.sub, string.char
local concat = table.concat

local function utf8_char(cp)
  if cp < 0x80 then return char(cp)
  elseif cp < 0x800 then return char(0xC0 + math.floor(cp / 64), 0x80 + cp % 64)
  elseif cp < 0x10000 then return char(0xE0 + math.floor(cp / 4096), 0x80 + math.floor(cp / 64) % 64, 0x80 + cp % 64)
  else return char(0xF0 + math.floor(cp / 262144), 0x80 + math.floor(cp / 4096) % 64, 0x80 + math.floor(cp / 64) % 64, 0x80 + cp % 64) end
end

local simple_esc = { [34] = '"', [92] = "\\", [47] = "/", [98] = "\b", [102] = "\f", [110] = "\n", [114] = "\r", [116] = "\t" }

function M.decode(str)
  local pos = 1
  local len = #str

  local function fail(msg)
    error(("json: %s at %d"):format(msg, pos), 0)
  end

  local function skip()
    pos = find(str, "[^ \t\r\n]", pos) or len + 1
  end

  local parse

  local function parse_string()
    -- str[pos] == '"'
    local i = pos + 1
    local start = i
    local parts
    while true do
      local j = find(str, '["\\]', i)
      if not j then pos = i; fail("unterminated string") end
      if byte(str, j) == 34 then
        local s = sub(str, start, j - 1)
        pos = j + 1
        if parts then parts[#parts + 1] = s; return concat(parts) end
        return s
      end
      -- backslash
      parts = parts or {}
      parts[#parts + 1] = sub(str, start, j - 1)
      local e = byte(str, j + 1)
      if e == 117 then -- \uXXXX
        local hex = sub(str, j + 2, j + 5)
        local cp = tonumber(hex, 16)
        if not cp or #hex < 4 then pos = j; fail("bad \\u escape") end
        i = j + 6
        if cp >= 0xD800 and cp <= 0xDBFF then
          local hex2 = sub(str, i, i + 5)
          local lo = hex2:match("^\\u(%x%x%x%x)$")
          lo = lo and tonumber(lo, 16)
          if lo and lo >= 0xDC00 and lo <= 0xDFFF then
            cp = 0x10000 + (cp - 0xD800) * 1024 + (lo - 0xDC00)
            i = i + 6
          else
            cp = 0xFFFD
          end
        elseif cp >= 0xDC00 and cp <= 0xDFFF then
          cp = 0xFFFD
        end
        parts[#parts + 1] = utf8_char(cp)
      else
        local c = simple_esc[e]
        if not c then pos = j; fail("bad escape") end
        parts[#parts + 1] = c
        i = j + 2
      end
      start = i
    end
  end

  local function parse_number()
    local s, e = find(str, "^-?%d+%.?%d*[eE]?[+-]?%d*", pos)
    if not s then fail("bad number") end
    local n = tonumber(sub(str, s, e))
    if not n then fail("bad number") end
    pos = e + 1
    return n
  end

  local function parse_array()
    pos = pos + 1
    local arr, n = {}, 0
    skip()
    if byte(str, pos) == 93 then pos = pos + 1; return arr end
    while true do
      skip()
      n = n + 1
      arr[n] = parse()
      skip()
      local c = byte(str, pos)
      pos = pos + 1
      if c == 93 then return arr end
      if c ~= 44 then pos = pos - 1; fail("expected , or ]") end
    end
  end

  local function parse_object()
    pos = pos + 1
    local obj = {}
    skip()
    if byte(str, pos) == 125 then pos = pos + 1; return obj end
    while true do
      skip()
      if byte(str, pos) ~= 34 then fail("expected string key") end
      local k = parse_string()
      skip()
      if byte(str, pos) ~= 58 then fail("expected :") end
      pos = pos + 1
      skip()
      obj[k] = parse()
      skip()
      local c = byte(str, pos)
      pos = pos + 1
      if c == 125 then return obj end
      if c ~= 44 then pos = pos - 1; fail("expected , or }") end
    end
  end

  function parse()
    local c = byte(str, pos)
    if c == 34 then return parse_string()
    elseif c == 123 then return parse_object()
    elseif c == 91 then return parse_array()
    elseif c == 116 then
      if sub(str, pos, pos + 3) == "true" then pos = pos + 4; return true end
    elseif c == 102 then
      if sub(str, pos, pos + 4) == "false" then pos = pos + 5; return false end
    elseif c == 110 then
      if sub(str, pos, pos + 3) == "null" then pos = pos + 4; return nil end
    elseif c and (c == 45 or (c >= 48 and c <= 57)) then return parse_number()
    end
    fail("unexpected character")
  end

  skip()
  local v = parse()
  return v
end

return M
