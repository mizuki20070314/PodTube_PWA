-- PodTube for M17 (LÖVE 11.4 on RK3126C).  A client of the PodTube PWA's server (api.cgi).
local log = require("core.log")
local store = require("core.store")
local Input = require("core.input")
local Net = require("core.net")
local Img = require("core.img")
local DebugCtl = require("core.debugctl")
local App = require("core.app")


function love.load(args)
  log.info("PodTube starting; save dir =", love.filesystem.getSaveDirectory())
  love.keyboard.setKeyRepeat(false)
  love.keyboard.setTextInput(false)
  love.mouse.setVisible(false)
  store.init()
  require("player.player").reload_settings()
  Input.open_all()
  if store.input_map then Input.set_map(store.input_map) end
  Net.init(3)
  Img.init(3)
  require("core.account").init()
  require("core.downloads").init()
  DebugCtl.init({ App = App, store = store, Net = Net, Img = Img, Input = Input, log = log, U = require("lib.util"),
    json = require("lib.json"), theme = require("ui.theme") })
  App.goto_tab(1)
  if not Net.configured() then App.push(require("screens.gate").new(false)) end
  -- the first time: which key is which is not printed on this machine, so ask (not on the development machine)
  if not store.input_map and not DebugCtl.enabled then App.push(require("screens.buttons").new(true)) end
end

-- The buttons are read straight from evdev (core/input.lua).  SDL reads the same devices as keyboards, so its key and text
-- events are ignored: they would arrive a second time.
function love.keypressed(k)
  if k == "r" and love.keyboard.isDown("lctrl") then love.event.quit("restart") end
end

-- A screen that throws must not take the whole app down (the device has no way to show a console): log it, close that
-- screen and go on.  Only a storm of errors falls through to the fatal error screen.
local function guarded(what, fn, ...)
  local ok, err = xpcall(fn, debug.traceback, ...)
  if ok then return true end
  log.err(what .. " error: " .. tostring(err))
  local now = love.timer.getTime()
  App.err_times = App.err_times or {}
  table.insert(App.err_times, now)
  while #App.err_times > 0 and now - App.err_times[1] > 4 do table.remove(App.err_times, 1) end
  if #App.err_times > 6 then error(err, 0) end
  love.graphics.setScissor(); love.graphics.setShader(); love.graphics.origin(); love.graphics.setColor(1, 1, 1, 1)
  local first_line = tostring(err):match("^[^\n]*") or ""
  App.toast(first_line:sub(1, 90), 4)
  if #App.stack > 1 then App.pop() else App.roots = {}; pcall(App.goto_tab, 1) end
  App.dirty = true
  return false
end

function love.update(dt)
  local events = Input.poll(dt)
  for _, e in ipairs(events) do guarded("input", App.action, e.action, e.kind) end
  DebugCtl.update()
  Net.update()
  Img.update()
  store.update()
  guarded("player", require("player.player").update, dt)
  require("core.mixer").update(dt, require("player.player").state == "playing")
  require("core.downloads").update(dt)
  guarded("update", App.update, dt)
end

function love.draw()
  guarded("draw", App.draw)
end

function love.threaderror(thread, errorstr)
  log.err("thread error: " .. tostring(errorstr))
end

function love.quit()
  log.info("PodTube leaving")
  pcall(function() require("player.engine").stop() end)
  store.flush()
  Net.shutdown()
  Img.shutdown()
  Input.close_all()
  return false
end

-- Main loop: redraws only when something changed (the panel is 73 Hz; idle screens should cost nothing).
function love.run()
  if love.load then love.load(love.arg.parseGameArguments(arg), arg) end
  love.timer.step()
  local dt = 0
  return function()
    love.event.pump()
    for name, a, b, c, d, e, f in love.event.poll() do
      if name == "quit" then
        if not love.quit or not love.quit() then return a or 0 end
      end
      love.handlers[name](a, b, c, d, e, f)
    end
    dt = love.timer.step()
    love.update(dt)
    if App.dirty and love.graphics.isActive() then
      App.dirty = false
      love.graphics.origin()
      love.graphics.clear(love.graphics.getBackgroundColor())
      love.draw()
      love.graphics.present()
      App.fcount = (App.fcount or 0) + 1
      local nowt = love.timer.getTime()
      if not App.fcount_t then App.fcount_t = nowt end
      if nowt - App.fcount_t >= 1 then App.draw_fps = App.fcount / (nowt - App.fcount_t); App.fcount, App.fcount_t = 0, nowt end
      love.timer.sleep(0.001)
    else
      love.timer.sleep(0.010)
    end
  end
end

-- Errors: log the traceback, show it, and leave on any button (there is no keyboard to press a key on).
function love.errorhandler(msg)
  local trace = debug.traceback(tostring(msg), 2)
  log.err("FATAL", trace)
  pcall(function() store.flush() end)
  pcall(function() require("player.engine").stop() end)
  local lines = {}
  for l in trace:gmatch("[^\n]+") do lines[#lines + 1] = l end
  local t0 = love.timer.getTime()
  local font = love.graphics.newFont(10)
  return function()
    love.event.pump()
    for name in love.event.poll() do
      if name == "quit" then return 1 end
    end
    local ev = Input.poll(0.016)
    for _, e in ipairs(ev) do if e.kind == "press" then return 1 end end
    love.graphics.origin()
    love.graphics.clear(0.35, 0.05, 0.05)
    love.graphics.setFont(font)
    love.graphics.setColor(1, 1, 1)
    love.graphics.print("PodTube: error (press any button to quit)", 6, 4)
    love.graphics.printf(table.concat(lines, "\n"), 6, 20, 468)
    love.graphics.present()
    if love.timer.getTime() - t0 > 120 then return 1 end
    love.timer.sleep(0.05)
  end
end
