-- Button setup: press the button you want for each function (the codes of this machine's keys are not printed on them)
local theme = require("ui.theme")
local D = require("ui.draw")
local T = require("ui.text")
local NavBar = require("ui.navbar")
local Input = require("core.input")
local store = require("core.store")
local I = require("core.i18n")

local c = theme.c
local W, H = theme.W, theme.H

local Buttons = {}
Buttons.__index = Buttons

local STEPS = {
  { a = "up", key = "btn.up" }, { a = "down", key = "btn.down" }, { a = "left", key = "btn.left" }, { a = "right", key = "btn.right" },
  { a = "a", key = "btn.a" }, { a = "b", key = "btn.b" }, { a = "x", key = "btn.x" }, { a = "y", key = "btn.y" },
  { a = "l", key = "btn.l", opt = true }, { a = "r", key = "btn.r", opt = true },
  { a = "l2", key = "btn.l2", opt = true }, { a = "r2", key = "btn.r2", opt = true },
  { a = "start", key = "btn.start", opt = true }, { a = "select", key = "btn.select", opt = true },
}

function Buttons.new(first_run)
  return setmetatable({ name = "buttons", first_run = first_run, hide_mini = true, i = 0, map = {}, taken = {}, deadline = 0, message = "" }, Buttons)
end

function Buttons:enter() self:next_step() end

function Buttons:leave() Input.cancel_capture() end

function Buttons:next_step()
  self.i = self.i + 1
  if self.i > #STEPS then self:finish(); return end
  local step = STEPS[self.i]
  self.deadline = love.timer.getTime() + (step.opt and 6 or 12)
  self:arm()
  App.dirty = true
end

--- waits for the next raw press for the current step
function Buttons:arm()
  local idx = self.i
  local step = STEPS[idx]
  Input.capture_next(function(src)
    if self.i ~= idx or self.done then return end
    if self.taken[src] then
      self.message = I.t("btn.taken", I.t(STEPS[self.taken[src]].key))
      self:arm()
      return
    end
    self.taken[src] = idx
    self.map[step.a] = self.map[step.a] or {}
    table.insert(self.map[step.a], src)
    self.message = Input.source_label(src)
    self:next_step()
  end)
end

function Buttons:finish()
  -- keep the volume keys and the defaults of what the wizard did not ask for
  for a, srcs in pairs(Input.DEFAULT_MAP) do
    if (a == "volup" or a == "voldown" or a == "menu") and not self.map[a] then self.map[a] = srcs end
  end
  Input.set_map(self.map)
  store.input_map = self.map
  store.save_now("inputmap")
  self.done = true
  self.done_at = love.timer.getTime() + 1.2
  App.toast(I.t("btn.saved"))
end

function Buttons:update(dt)
  local now = love.timer.getTime()
  if self.done then
    if now >= self.done_at then App.pop() end
    return
  end
  local step = STEPS[self.i]
  if step and now > self.deadline then
    Input.cancel_capture()
    if step.opt then
      self:next_step()
    else
      -- nothing was pressed: keep the default layout (and do not ask again at every start)
      if self.first_run and not store.input_map then
        store.input_map = Input.DEFAULT_MAP
        store.save_now("inputmap")
        App.toast(I.t("btn.firstRunSkipped"), 4)
      else
        App.toast(I.t("btn.cancelled"))
      end
      App.pop()
    end
  end
  App.dirty = true
end

function Buttons:action() return true end

function Buttons:draw()
  NavBar.draw(I.t("settings.buttons"))
  local step = STEPS[self.i]
  if self.done then
    T.line(I.t("btn.saved"), 0, H / 2 - 10, W, 16, "bold", c.text, "center")
    return
  end
  if not step then return end
  if self.first_run then T.line(I.t("btn.firstRun"), 10, 32, W - 20, 11, "medium", c.link, "center") end
  T.line(string.format("%d / %d", self.i, #STEPS), 0, 48, W, 12, "regular", c.secondary, "center")
  T.line(I.t("btn.press"), 10, 72, W - 20, 13, "regular", c.secondary, "center")
  T.line(I.t(step.key), 10, 96, W - 20, 30, "bold", c.white, "center")
  local left = math.max(0, self.deadline - love.timer.getTime())
  D.progress(60, 150, W - 120, 4, left / (step.opt and 6 or 12), c.red, c.surface_high, 2)
  if step.opt then T.line(I.t("btn.skipHint"), 10, 164, W - 20, 11, "regular", c.secondary, "center") end
  if self.message ~= "" then T.line(self.message, 10, 200, W - 20, 12, "medium", c.link, "center") end
end

return Buttons
