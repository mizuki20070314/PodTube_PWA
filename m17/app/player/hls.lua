-- HLS helpers: the server's master playlist (variants + audio renditions) and the choice of a variant.
local M = {}

local function attr(line, name)
  local q = line:match(name .. '="([^"]*)"')
  if q then return q end
  return line:match(name .. "=([^,]*)")
end

--- the variants and audio renditions of the server's master playlist
function M.parse_master(text)
  local audio, variants = {}, {}
  local pending
  for line in text:gmatch("[^\r\n]+") do
    if line:sub(1, 13) == "#EXT-X-MEDIA:" and attr(line, "TYPE") == "AUDIO" then
      audio[attr(line, "GROUP-ID") or ""] = { uri = attr(line, "URI"), name = attr(line, "NAME"), lang = attr(line, "LANGUAGE") }
    elseif line:sub(1, 18) == "#EXT-X-STREAM-INF:" then
      local res = attr(line, "RESOLUTION") or ""
      local w, h = res:match("^(%d+)x(%d+)$")
      pending = {
        w = tonumber(w) or 0, h = tonumber(h) or 0, bandwidth = tonumber(attr(line, "BANDWIDTH")) or 0,
        fps = tonumber(attr(line, "FRAME-RATE")) or 30, audio = attr(line, "AUDIO"),
      }
    elseif pending and line:sub(1, 1) ~= "#" then
      pending.uri = line
      variants[#variants + 1] = pending
      pending = nil
    end
  end
  return variants, audio
end

function M.choose_variant(variants, cap)
  local best, smallest
  for _, v in ipairs(variants) do
    local short = math.min(v.w, v.h)
    if not smallest or short < math.min(smallest.w, smallest.h) or (short == math.min(smallest.w, smallest.h) and v.bandwidth < smallest.bandwidth) then smallest = v end
    if short <= cap then
      local bshort = best and math.min(best.w, best.h) or -1
      if short > bshort or (short == bshort and v.bandwidth > best.bandwidth) then best = v end
    end
  end
  return best or smallest
end


return M
