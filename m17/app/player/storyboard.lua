-- Storyboards: the small preview pictures YouTube keeps for every video, as sheets of frames (PT.Storyboard in the PWA).
-- spec = baseURL|w#h#count#columns#rows#intervalMs#name#sigh|...
local M = {}
M.__index = M

local function split(s, sep)
  local out = {}
  for part in (s .. sep):gmatch("(.-)" .. sep:gsub("%p", "%%%0")) do out[#out + 1] = part end
  return out
end

function M.new(spec, duration)
  local parts = split(tostring(spec or ""), "|")
  if #parts < 2 or not (duration and duration > 0) or not (parts[1]:find("$L", 1, true) or parts[1]:find("$N", 1, true)) then return nil end
  local levels = {}
  for i = 2, #parts do
    local f = split(parts[i], "#")
    if #f == 8 then
      local w, h, n, c, r, iv = tonumber(f[1]), tonumber(f[2]), tonumber(f[3]), tonumber(f[4]), tonumber(f[5]), tonumber(f[6])
      if w and h and n and c and r and iv and w > 0 and h > 0 and n > 0 and c > 0 and r > 0 then
        levels[#levels + 1] = { w = w, h = h, count = n, cols = c, rows = r, interval = iv, name = f[7], sigh = f[8] }
      end
    end
  end
  if #levels == 0 then return nil end
  table.sort(levels, function(a, b) if a.w ~= b.w then return a.w < b.w end return a.h < b.h end)
  for i, l in ipairs(levels) do
    l.index = i - 1
    l.per_sheet = math.max(1, l.cols * l.rows)
  end
  return setmetatable({ base = parts[1], levels = levels, duration = duration }, M)
end

--- the first level at least `min_width` wide (the widest when none is)
function M:level(min_width)
  for _, l in ipairs(self.levels) do if l.w >= min_width then return l end end
  return self.levels[#self.levels]
end

function M:spacing(l)
  if l.interval > 0 then return l.interval / 1000 end
  return self.duration / math.max(1, l.count)
end

function M:frame_index(l, t)
  local i = math.floor(math.max(0, t) / self:spacing(l))
  return math.min(math.max(i, 0), l.count - 1)
end

--- {sheet, col, row} (all 0-based) of the frame showing time t
function M:cell_at(l, t)
  local f = self:frame_index(l, t)
  local sheet = math.floor(f / l.per_sheet)
  local j = f % l.per_sheet
  return { sheet = sheet, col = j % l.cols, row = math.floor(j / l.cols) }
end

function M:sheet_url(l, sheet)
  local name = l.name:gsub("%$M", function() return tostring(sheet) end)
  local url = self.base:gsub("%$L", function() return tostring(l.index) end):gsub("%$N", function() return name end)
  return url .. "&sigh=" .. l.sigh
end

return M
