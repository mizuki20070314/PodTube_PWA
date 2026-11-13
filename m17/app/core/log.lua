-- logging: stdout (-> logs/podtube.log, flushed) plus a small ring buffer that the debug overlay can show
local L = { lines = {}, max = 60 }

local function stamp()
  local t = love and love.timer and love.timer.getTime() or os.clock()
  return string.format("%8.3f", t)
end

local function emit(level, ...)
  local parts = {}
  for i = 1, select("#", ...) do parts[i] = tostring((select(i, ...))) end
  local msg = table.concat(parts, " ")
  local line = stamp() .. " " .. level .. " " .. msg
  io.stdout:write(line, "\n")
  io.stdout:flush()
  local ls = L.lines
  ls[#ls + 1] = msg
  if #ls > L.max then table.remove(ls, 1) end
end

function L.info(...) emit("I", ...) end
function L.warn(...) emit("W", ...) end
function L.err(...) emit("E", ...) end

return L
