-- A text prompt with the on-screen keyboard (naming a playlist, the access key ...)
local theme = require("ui.theme")
local D = require("ui.draw")
local T = require("ui.text")
local Keyboard = require("ui.keyboard")
local I = require("core.i18n")
local utf8 = require("utf8")

local c = theme.c
local W, H = theme.W, theme.H

local Osk = {}
Osk.__index = Osk

--- opts: title, text, mode ("hira" | "latin"), secret (show dots), submit_label, on_submit(text)
function Osk.new(opts)
  local self = setmetatable({ name = "osk", opts = opts, hide_mini = true }, Osk)
  self.kb = Keyboard.new({
    text = opts.text or "", mode = opts.mode or "hira", submit_label = opts.submit_label or I.t("kb.ok"),
    on_submit = function(t)
      App.pop()
      if opts.on_submit then opts.on_submit(t) end
    end,
    on_cancel = function() App.pop() end,
  })
  return self
end

function Osk.ask(opts)
  App.push(Osk.new(opts))
end

function Osk:type_text(s) self.kb:append(s) end

function Osk:action(act, kind)
  if kind == "release" then return false end
  if self.kb:action(act, kind) then return true end
  return false
end

function Osk:draw()
  D.rect(0, 0, W, H, c.bg)
  T.line(self.opts.title or "", 12, 8, W - 24, 14, "bold", c.text)
  D.rect(8, 34, W - 16, 32, c.surface, 8)
  local text = self.kb.text
  if self.opts.secret then text = string.rep("•", utf8.len(text) or #text) end
  local fw = W - 40
  local shown = text
  local tw = T.width(shown, 15, "medium")
  while tw > fw and #shown > 1 do shown = shown:sub(utf8.offset(shown, 2)); tw = T.width(shown, 15, "medium") end
  T.print(shown, 16, 40, 15, "medium", c.text)
  if math.floor(love.timer.getTime() * 2) % 2 == 0 then D.rect(17 + tw, 41, 2, 18, c.text) end
  App.dirty = true
  self.kb:draw(0, H - 160, W, 156, true)
end

return Osk
