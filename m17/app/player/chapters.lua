-- Chapters: timestamps in the description ("0:00 Intro").  They count only when the list starts at 0:00, has at least two
-- entries and is ascending (same rule as the PWA's PT.chapters).
local U = require("lib.util")

local M = {}

local STRIP_LEAD = { " ", "\t", "-", ":", "|", ".", ")", "(", "\u{2013}", "\u{2014}", "\u{30fb}" }

local function strip(s)
  local changed = true
  while changed do
    changed = false
    for _, p in ipairs(STRIP_LEAD) do
      if s:sub(1, #p) == p then s = s:sub(#p + 1); changed = true end
      if #s >= #p and s:sub(-#p) == p then s = s:sub(1, #s - #p); changed = true end
    end
  end
  return s
end

local function leading_timestamp(line)
  local s = line
  local c = s:sub(1, 1)
  if c == "[" or c == "(" then s = s:sub(2) end
  local token = s:match("^[%d:]+")
  if not token or not token:find(":", 1, true) or #token > 8 then return nil end
  local secs = 0
  for part in token:gmatch("[^:]+") do secs = secs * 60 + tonumber(part) end
  local rest = s:sub(#token + 1)
  local c2 = rest:sub(1, 1)
  if c2 == "]" or c2 == ")" then rest = rest:sub(2) end
  return secs, rest
end

function M.parse(description)
  local out = {}
  for raw in tostring(description or ""):gmatch("[^\r\n]+") do
    local line = U.trim(raw)
    if line ~= "" then
      local secs, rest = leading_timestamp(line)
      if secs then
        local title = strip(rest)
        out[#out + 1] = { start = secs, title = title ~= "" and title or U.clock(secs) }
      end
    end
  end
  if #out < 2 or out[1].start ~= 0 then return {} end
  for i = 2, #out do
    if out[i].start <= out[i - 1].start then return {} end
  end
  return out
end

function M.current(list, t)
  local cur
  for _, ch in ipairs(list) do
    if ch.start <= t then cur = ch else break end
  end
  return cur
end

return M
