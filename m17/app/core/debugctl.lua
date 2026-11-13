-- Debug control channel (development only).  Listens on 127.0.0.1:7777 when the file <app dir>/debug.flag exists or
-- PODTUBE_DEBUG is set; the PC reaches it with `adb forward tcp:7777 tcp:7777` (tools/ctl.py).
--
--   key <button> [press|release|tap]   inject a logical button
--   text <utf-8>                       type text into the focused text field
--   eval <lua>                         run Lua inside the app, reply with the result
--   state                              JSON summary (screen, fps, memory ...)
--   reload                             restart the Lua side (love.event.quit("restart"))
--   quit                               leave the app
local log = require("core.log")
local json = require("lib.json")

local D = { enabled = false }

local server
local env

local function show(v)
  local t = type(v)
  if t == "table" then
    local ok, s = pcall(json.encode, v)
    if ok then return s end
  end
  return tostring(v)
end

local function run_eval(code)
  local fn, err = loadstring("return " .. code, "=eval")
  if not fn then fn, err = loadstring(code, "=eval") end
  if not fn then return "ERR " .. tostring(err) end
  setfenv(fn, env)
  local res = { pcall(fn) }
  if not res[1] then return "ERR " .. tostring(res[2]) end
  local out = {}
  for i = 2, #res do out[#out + 1] = show(res[i]) end
  return table.concat(out, "\t")
end

local function handle(line)
  local cmd, rest = line:match("^(%S+)%s*(.*)$")
  if not cmd then return "ERR empty" end
  if cmd == "key" then
    local action, kind = rest:match("^(%S+)%s*(%S*)$")
    if not action then return "ERR usage: key <button> [press|release|tap]" end
    require("core.input").inject(action, kind ~= "" and kind or "tap")
    App.dirty = true
    return "ok"
  elseif cmd == "text" then
    if App.type_text then App.type_text(rest) end
    App.dirty = true
    return "ok"
  elseif cmd == "eval" then
    local r = run_eval(rest)
    App.dirty = true
    return r
  elseif cmd == "state" then
    local top = App.top and App.top()
    return json.encode({
      screen = top and top.name or "?",
      depth = App.stack and #App.stack or 0,
      fps = love.timer.getFPS(), draw_fps = App.draw_fps and math.floor(App.draw_fps * 10) / 10 or 0,
      mem_kb = math.floor(collectgarbage("count")),
      tex_mb = math.floor(((love.graphics.getStats().texturememory) or 0) / 1048576 * 10) / 10,
      time = os.time(),
    })
  elseif cmd == "reload" then
    love.event.quit("restart")
    return "ok"
  elseif cmd == "quit" then
    love.event.quit()
    return "ok"
  elseif cmd == "ping" then
    return "pong"
  end
  return "ERR unknown command " .. cmd
end

function D.init(environment)
  env = setmetatable(environment or {}, { __index = _G })
  local flag = love.filesystem.getSource() .. "/../debug.flag"
  local f = io.open(flag, "rb")
  local enabled = f ~= nil or os.getenv("PODTUBE_DEBUG") ~= nil
  if f then f:close() end
  if not enabled then return end
  local ok, socket = pcall(require, "socket")
  if not ok then log.warn("debugctl: no socket library"); return end
  server = socket.bind("127.0.0.1", 7777)
  if not server then log.warn("debugctl: cannot bind 7777"); return end
  server:settimeout(0)
  D.enabled = true
  log.info("debugctl: listening on 127.0.0.1:7777")
end

function D.update()
  if not server then return end
  for _ = 1, 4 do
    local c = server:accept()
    if not c then return end
    c:settimeout(0.4)
    local line = c:receive("*l")
    if line then
      local ok, reply = pcall(handle, line)
      if not ok then reply = "ERR " .. tostring(reply) end
      reply = tostring(reply):gsub("\r", ""):gsub("\n", "\\n")
      c:send(reply .. "\n")
    end
    c:close()
  end
end

return D
