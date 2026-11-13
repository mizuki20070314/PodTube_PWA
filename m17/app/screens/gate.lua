-- Server settings: the address of the PodTube server and its access key (the PWA's key gate)
local theme = require("ui.theme")
local D = require("ui.draw")
local T = require("ui.text")
local NavBar = require("ui.navbar")
local MenuList = require("ui.menulist")
local Net = require("core.net")
local store = require("core.store")
local I = require("core.i18n")
local U = require("lib.util")

local c = theme.c
local W, H = theme.W, theme.H

local Gate = {}
Gate.__index = Gate

function Gate.new(from_settings)
  local self = setmetatable({ name = "gate", hide_mini = true, base = store.server.base or "https://my-dev.sakura.ne.jp/podtube", key = store.server.key or "",
    from_settings = from_settings, message = "" }, Gate)
  self.menu = MenuList.new({})
  self:rebuild()
  return self
end

function Gate:rebuild()
  local me = self
  local masked = self.key ~= "" and string.rep("•", math.min(12, #self.key)) or ""
  self.menu:set_items({
    { kind = "note", text = I.t("gate.intro") },
    { kind = "choice", label = I.t("server.url"), value = self.base:gsub("^https?://", ""), on = function()
      require("screens.osk").ask({ title = I.t("server.url"), text = me.base, mode = "latin", on_submit = function(t)
        t = U.trim(t)
        if t ~= "" and not t:match("^https?://") then t = "https://" .. t end
        me.base = t:gsub("/+$", ""); me:rebuild()
      end })
    end },
    { kind = "choice", label = I.t("gate.placeholder"), value = masked, on = function()
      require("screens.osk").ask({ title = I.t("gate.placeholder"), text = me.key, mode = "latin", secret = true, on_submit = function(t)
        me.key = U.trim(t); me:rebuild()
      end })
    end },
    { kind = "button", label = I.t("gate.submit"), on = function() me:try() end },
    { kind = "note", text = me.message ~= "" and me.message or I.t("gate.note") },
  })
  self.menu:fix_sel(1)
end

function Gate:try()
  local old = { base = store.server.base, key = store.server.key }
  store.server.base, store.server.key = self.base, self.key
  self.message = I.t("common.loading")
  self:rebuild()
  Net.get("init", nil, function(err, r)
    if err then
      store.server.base, store.server.key = old.base, old.key
      self.message = err.code == "locked" and I.t("gate.wrong") or (I.t("net.error") .. " (" .. tostring(err.message) .. ")")
      self:rebuild()
      return
    end
    store.server.base, store.server.key = self.base, self.key
    store.save_now("server")
    App.toast(I.t("signin.done"))
    App.roots = {}
    App.pop_to_root()
    App.goto_tab(1)
  end)
end

function Gate:action(act, kind)
  if kind == "release" then return false end
  if act == "b" and not self.from_settings and not Net.configured() then return true end
  return self.menu:action(act, kind)
end

function Gate:update(dt) self.menu:update(dt) end

function Gate:draw()
  NavBar.draw(I.t("settings.server"))
  self.menu:draw(0, NavBar.H, W, H - NavBar.H)
end

return Gate
