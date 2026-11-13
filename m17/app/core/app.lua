-- App shell: the screen stack, the left navigation rail, toasts, the modal sheet, input dispatch and drawing order.
local theme = require("ui.theme")
local D = require("ui.draw")
local T = require("ui.text")
local Input = require("core.input")
local I = require("core.i18n")
local log = require("core.log")
local U = require("lib.util")
local Mini = require("ui.mini")
local Player = require("player.player")

local c = theme.c
local g = love.graphics

local App = {}
_G.App = App

App.dirty = true
App.stack = {}
App.roots = {}
App.tab = 1
App.focus = "content"       -- "content" | "rail"
App.rail_sel = 2
App.sheet = nil
App.toast_msg = nil
App.overlays = {}           -- draw-over callbacks (mini player ...)

-- the rail: search + the four tabs of the PWA's bottom bar
App.RAIL = {
  { id = "search", icon = "search", label = "search.placeholder" },
  { id = "home", icon = "home", label = "tab.home", tab = 1 },
  { id = "shorts", icon = "shorts", label = "tab.shorts", tab = 2 },
  { id = "subs", icon = "subscriptions", label = "tab.subs", tab = 3 },
  { id = "you", icon = "account_circle", label = "tab.you", tab = 4 },
}
App.ROOTS = { "screens.home", "screens.shorts", "screens.subs", "screens.you" }

---------------------------------------------------------------------------------------------------------------------
-- stack
---------------------------------------------------------------------------------------------------------------------
function App.top() return App.stack[#App.stack] end

--- height taken at the bottom by the mini player
function App.bottom_inset() return Mini.inset() end

function App.content_rect()
  if #App.stack <= 1 then return theme.RAIL_W, theme.W - theme.RAIL_W end
  return 0, theme.W
end

local function root_screen(i)
  local r = App.roots[i]
  if not r then
    r = require(App.ROOTS[i]).new()
    App.roots[i] = r
  end
  return r
end

function App.goto_tab(i)
  local old = App.top()
  if old and old.leave_view then old:leave_view() end
  App.tab = i
  App.stack = { root_screen(i) }
  local s = App.top()
  if s.resume then s:resume() end
  App.focus = "content"
  App.dirty = true
end

function App.push(screen)
  local old = App.top()
  if old and old.suspend then old:suspend() end
  App.stack[#App.stack + 1] = screen
  if screen.enter then screen:enter() end
  App.focus = "content"
  App.dirty = true
  return screen
end

function App.pop()
  if #App.stack <= 1 then return false end
  local s = table.remove(App.stack)
  if s.leave then s:leave() end
  local t = App.top()
  if t and t.resume then t:resume() end
  App.dirty = true
  return true
end

function App.replace(screen)
  local old = table.remove(App.stack)
  if old and old.leave then old:leave() end
  App.stack[#App.stack + 1] = screen
  if screen.enter then screen:enter() end
  App.dirty = true
  return screen
end

--- pops back to the root screen
function App.pop_to_root()
  while #App.stack > 1 do
    local s = table.remove(App.stack)
    if s.leave then s:leave() end
  end
  local t = App.top()
  if t and t.resume then t:resume() end
  App.dirty = true
end

---------------------------------------------------------------------------------------------------------------------
-- sheet / toast
---------------------------------------------------------------------------------------------------------------------
function App.open_sheet(opts)
  local Sheet = require("ui.sheet")
  App.sheet = Sheet.new(opts)
  App.dirty = true
  return App.sheet
end

function App.close_sheet()
  App.sheet = nil
  App.dirty = true
end

function App.toast(msg, secs)
  App.toast_msg = tostring(msg)
  App.toast_until = love.timer.getTime() + (secs or 2.2)
  App.toast_block = nil
  App.dirty = true
end

---------------------------------------------------------------------------------------------------------------------
-- input
---------------------------------------------------------------------------------------------------------------------
local chord_quit = 0

function App.action(act, kind)
  App.dirty = true
  if act == "volup" or act == "voldown" then
    if kind == "press" then
      -- keymon applies the new level a moment after the key: look at it a little later
      require("core.mixer").schedule_show()
    end
    return
  end
  if App.sheet then App.sheet:action(act, kind); return end
  -- START + SELECT held together for a second leaves the app
  if (act == "start" or act == "select") and kind == "press" then
    if Input.is_down("start") and Input.is_down("select") then chord_quit = love.timer.getTime() end
  end
  local top = App.top()
  if App.focus == "rail" and #App.stack == 1 then
    if kind == "release" then return end
    local n = #App.RAIL
    if act == "up" then App.rail_sel = (App.rail_sel - 2) % n + 1
    elseif act == "down" then App.rail_sel = App.rail_sel % n + 1
    elseif act == "right" or act == "b" then App.focus = "content"
    elseif act == "a" then
      local it = App.RAIL[App.rail_sel]
      if it.id == "search" then
        App.focus = "content"
        App.open_search()
      else
        if it.tab == App.tab then
          App.focus = "content"
          local t = App.top()
          if t and t.scroll_top then t:scroll_top() end
        else
          App.goto_tab(it.tab)
        end
      end
    end
    return
  end
  if top and top.action then
    local handled = top:action(act, kind)
    if handled then return end
  end
  if kind == "release" then return end
  -- defaults
  if act == "b" then
    if #App.stack > 1 then App.pop()
    else
      local now = love.timer.getTime()
      if App.quit_at and now < App.quit_at then love.event.quit()
      else App.quit_at = now + 2.2; App.toast(I.t("app.quitHint")) end
    end
  elseif act == "left" and #App.stack == 1 then
    App.focus = "rail"
    App.rail_sel = App.tab + 1
  elseif act == "y" and App.open_search then
    App.open_search()
  elseif act == "select" and Player.current and not (top and top.name == "watch") then
    App.push(require("screens.watch").new(Player.current, { resume = true }))
  elseif (act == "l" or act == "r") and #App.stack == 1 and not (top and top.captures_shoulders) then
    local d = act == "l" and -1 or 1
    App.goto_tab((App.tab - 1 + d) % #App.ROOTS + 1)
  end
end

function App.open_search()
  local top = App.top()
  if top and top.name == "search" then return end
  App.push(require("screens.search").new())
end

function App.type_text(s)
  local top = App.top()
  if App.sheet then return end
  if top and top.type_text then top:type_text(s) end
end

---------------------------------------------------------------------------------------------------------------------
-- update / draw
---------------------------------------------------------------------------------------------------------------------
function App.update(dt)
  local top = App.top()
  for i = #App.stack, 1, -1 do
    local s = App.stack[i]
    if s.update_always or s == top then if s.update then s:update(dt) end end
  end
  if App.sheet and App.sheet.update then App.sheet:update(dt) end
  if App.toast_msg and love.timer.getTime() > App.toast_until then App.toast_msg = nil; App.dirty = true end
  if chord_quit > 0 then
    if Input.is_down("start") and Input.is_down("select") then
      if love.timer.getTime() - chord_quit > 1.0 then love.event.quit() end
    else
      chord_quit = 0
    end
  end
end

local function draw_rail()
  D.rect(0, 0, theme.RAIL_W, theme.H, c.bg)
  D.rect(theme.RAIL_W - 1, 0, 1, theme.H, c.divider)
  local n = #App.RAIL
  local pitch = theme.H / n
  for i, it in ipairs(App.RAIL) do
    local cy = (i - 0.5) * pitch
    local active = it.tab == App.tab
    local focused = App.focus == "rail" and App.rail_sel == i
    if focused then
      D.rect(4, cy - 20, theme.RAIL_W - 9, 40, c.surface, 8)
      D.outline(4, cy - 20, theme.RAIL_W - 9, 40, c.white, 8, 1.5)
    end
    local col = (active or focused) and c.white or c.secondary
    D.icon(it.icon, (theme.RAIL_W - 1 - 22) / 2, cy - 11 - (active and 0 or 0), 22, col)
    if active then D.rect(1, cy - 10, 3, 20, c.red, 1) end
  end
end

local function draw_toast()
  if not App.toast_msg then return end
  local b = App.toast_block
  if not b then
    b = T.layout(App.toast_msg, 320, { size = 12, weight = "medium", lines = 2, pitch = 16 })
    App.toast_block = b
  end
  local w = math.max(60, b.w + 28)
  local h = b.h + 14
  local x = (theme.W - w) / 2
  local y = theme.H - h - 18
  D.rect(x, y, w, h, { 0.95, 0.95, 0.95, 0.96 }, h / 2 > 14 and 12 or h / 2)
  T.draw_block(b, x + 14, y + 7, { 0.06, 0.06, 0.06, 1 })
end

function App.draw()
  require("core.img").begin_frame()
  g.setColor(1, 1, 1, 1)
  g.clear(c.bg[1], c.bg[2], c.bg[3], 1)
  local top = App.top()
  if top and top.draw then top:draw() end
  if #App.stack == 1 then draw_rail() end
  Mini.draw()
  for _, f in ipairs(App.overlays) do f() end
  if App.sheet then App.sheet:draw() end
  draw_toast()
end

return App
