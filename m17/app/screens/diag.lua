-- Diagnostics: runs the whole playback chain once and prints what worked (S.diagnostics in the PWA) plus this device's checks
local theme = require("ui.theme")
local D = require("ui.draw")
local T = require("ui.text")
local NavBar = require("ui.navbar")
local Net = require("core.net")
local store = require("core.store")
local I = require("core.i18n")
local U = require("lib.util")

local c = theme.c
local W, H = theme.W, theme.H

local Diag = {}
Diag.__index = Diag

local function sh(cmd)
  local p = io.popen(cmd .. " 2>&1", "r")
  if not p then return "" end
  local out = p:read("*a") or ""
  p:close()
  return (out:gsub("%s+$", ""))
end

function Diag.new()
  local self = setmetatable({ name = "diag", hide_mini = true, lines = {}, scroll = 0, running = false }, Diag)
  return self
end

function Diag:add(s) self.lines[#self.lines + 1] = s; self.stick = true; App.dirty = true end
function Diag:report(label, ok, ms, detail) self:add((ok and "OK  " or "NG  ") .. label .. " " .. ms .. "ms " .. (detail or "")) end

function Diag:enter()
  self:add("PodTube M17 1.0")
  self:add(sh("uname -r") .. "  " .. (jit and jit.version or "?"))
  self:add("hl=" .. store.hl() .. " gl=" .. store.gl())
  self:add("")
  self:run()
end

function Diag:run()
  if self.running then return end
  self.running = true
  self:add("--- " .. os.date("%H:%M:%S"))
  local mem = sh("grep -E 'MemAvailable' /proc/meminfo"):match("(%d+)")
  self:add("memory available: " .. math.floor((tonumber(mem) or 0) / 1024) .. " MB")
  self:add("ffmpeg: " .. sh("ffmpeg -version | head -1"):sub(1, 60))
  self:add("proxy: " .. (os.getenv("https_proxy") or os.getenv("HTTPS_PROXY") or "(none)"))
  self:add("clock: " .. os.date("%Y-%m-%d %H:%M:%S"))
  local t0 = love.timer.getTime()
  Net.get("diag", nil, function(err, r)
    self.running = false
    if err then self:add("NG  server: " .. (err.message or "")); return end
    self:add("-- server " .. (r.version or ""))
    for _, l in ipairs(r.lines or {}) do self:report(l.label, l.ok, l.ms, l.detail) end
    self:add("round trip " .. math.floor((love.timer.getTime() - t0) * 1000) .. "ms")
    self:add("")
  end, { auth = require("core.account").signed_in(), timeout = 90 })
  self:add("(running the server's check ...)")
end

function Diag:action(act, kind)
  if kind == "release" then return false end
  if act == "down" then self.scroll = self.scroll + 24; self.stick = false; App.dirty = true; return true
  elseif act == "up" then self.scroll = math.max(0, self.scroll - 24); self.stick = false; App.dirty = true; return true
  elseif act == "a" then self:run(); return true end
  return false
end

function Diag:update(dt) if self.running then App.dirty = true end end

function Diag:draw()
  NavBar.draw(I.t("diag.title"), "Ⓐ " .. I.t("diag.run"))
  local vh = H - NavBar.H - 6
  local lh = 13
  local total = #self.lines * lh
  if self.stick then self.scroll = math.max(0, total - vh) end
  D.clip(0, NavBar.H, W, vh)
  for i, l in ipairs(self.lines) do
    local y = NavBar.H + 4 + (i - 1) * lh - self.scroll
    if y > NavBar.H - lh and y < H then
      local col = l:sub(1, 2) == "NG" and c.red or (l:sub(1, 2) == "OK" and c.text or c.secondary)
      T.print(l, 8, y, 10, "regular", col)
    end
  end
  D.unclip()
  if self.running then D.spinner(W - 20, H - 20, 8, c.secondary) end
end

return Diag
