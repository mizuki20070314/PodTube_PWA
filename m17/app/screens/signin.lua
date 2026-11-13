-- Sign-in: the "limited input device" flow that YouTube on TV uses (S.signIn in the PWA).  The code is typed on another device.
local theme = require("ui.theme")
local D = require("ui.draw")
local T = require("ui.text")
local NavBar = require("ui.navbar")
local Net = require("core.net")
local account = require("core.account")
local I = require("core.i18n")
local U = require("lib.util")

local c = theme.c
local W, H = theme.W, theme.H

local SignIn = {}
SignIn.__index = SignIn

function SignIn.new()
  return setmetatable({ name = "signin", hide_mini = true, gen = 0, code = nil, status = "", busy = false, show_retry = false, interval = 5, finished = false, expires_at = 0, next_poll = 0 }, SignIn)
end

function SignIn:enter() self:start() end
function SignIn:leave() self.gen = self.gen + 1 end

function SignIn:set_status(text, busy, retry)
  self.status, self.busy, self.show_retry = text, busy, retry
  App.dirty = true
end

function SignIn:start()
  self.gen = self.gen + 1
  local g = self.gen
  self.code = nil
  self.next_poll = 0
  self:set_status(I.t("signin.getting"), true, false)
  Net.post("auth/device", {}, function(err, c_)
    if g ~= self.gen then return end
    if err then self:set_status(I.t("signin.failed") .. "\n" .. (err.message or ""), false, true); return end
    self.code = c_
    self.interval = math.max(c_.interval or 5, 3)
    self.expires_at = love.timer.getTime() + (c_.expiresIn or 1800)
    self.next_poll = love.timer.getTime() + self.interval
    self:set_status(I.t("signin.waiting"), true, false)
  end)
end

function SignIn:poll()
  local g = self.gen
  local code = self.code
  self.polling = true
  Net.post("auth/poll", { deviceCode = code.deviceCode }, function(err, r)
    self.polling = false
    if g ~= self.gen or self.finished then return end
    if err then
      -- transient problem (offline, 5xx): keep trying until the code expires
      self:set_status(I.t("signin.waiting") .. "\n" .. (err.message or ""), true, false)
      self.next_poll = love.timer.getTime() + self.interval
      return
    end
    local st = r.status
    if st == "ok" then
      self.finished = true
      self.gen = self.gen + 1
      self:set_status(I.t("signin.finishing"), true, false)
      account.adopt(r)
      account.did_sign_in()
      App.toast(I.t("signin.done"))
      self.close_at = love.timer.getTime() + 0.6
    elseif st == "pending" then self.next_poll = love.timer.getTime() + self.interval
    elseif st == "slow_down" then self.interval = self.interval + 5; self.next_poll = love.timer.getTime() + self.interval
    elseif st == "denied" then self.gen = self.gen + 1; self:set_status(I.t("signin.denied"), false, true)
    elseif st == "expired" then self:start()
    else self:set_status(I.t("signin.waiting") .. "\n" .. (r.message or ""), true, false); self.next_poll = love.timer.getTime() + self.interval end
  end)
end

function SignIn:update(dt)
  local now = love.timer.getTime()
  if self.close_at and now >= self.close_at then self.close_at = nil; App.pop(); return end
  if self.code and not self.finished and not self.polling and now >= self.next_poll and self.next_poll > 0 then
    if now > self.expires_at then self:start() else self:poll() end
  end
  if self.busy then App.dirty = true end
end

function SignIn:action(act, kind)
  if kind == "release" then return false end
  if act == "a" and (self.show_retry or self.code) then self.finished = false; self:start(); return true end
  return false
end

function SignIn:draw()
  NavBar.draw(I.t("signin.title"))
  local url = self.code and self.code.verificationURL and self.code.verificationURL:gsub("^https?://", "") or "google.com/device"
  T.line(I.t("signin.step1"), 16, 36, W - 32, 12, "regular", c.secondary)
  T.line(url, 16, 52, W - 32, 22, "bold", c.link)
  T.line(I.t("signin.step2"), 16, 90, W - 32, 12, "regular", c.secondary)
  local code = self.code and self.code.userCode or "···-···-····"
  D.rect(16, 108, W - 32, 52, c.surface, 10)
  local cw = T.width(code, 30, "bold")
  T.print(code, (W - cw) / 2, 114, 30, "bold", c.white)
  local sb = T.layout(self.status or "", W - 90, { size = 12, lines = 3, pitch = 16 })
  if self.busy then D.spinner(30, 186, 8, c.secondary) end
  T.draw_block(sb, 48, 178, c.text)
  local nb = T.layout(I.t("signin.note"), W - 32, { size = 10, lines = 4, pitch = 13 })
  T.draw_block(nb, 16, H - 8 - nb.h, c.secondary)
  T.line("Ⓐ " .. I.t("signin.newCode"), 16, 210, W - 32, 11, "medium", c.link)
end

return SignIn
