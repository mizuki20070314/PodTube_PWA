-- Settings (S.settings in the PWA) plus what only this device has: the buttons, the server, the picture size
local theme = require("ui.theme")
local D = require("ui.draw")
local T = require("ui.text")
local NavBar = require("ui.navbar")
local MenuList = require("ui.menulist")
local store = require("core.store")
local account = require("core.account")
local Player = require("player.player")
local I = require("core.i18n")
local U = require("lib.util")
local Net = require("core.net")

local W, H = theme.W, theme.H

local Settings = {}
Settings.__index = Settings

local VERSION = "1.0 (M17)"

local function pick(title, options, current, on_pick)
  local items = {}
  for _, o in ipairs(options) do
    items[#items + 1] = { label = o.label, checked = o.value == current, on = function() on_pick(o.value) end }
  end
  App.open_sheet({ title = title, items = items })
end

function Settings.new()
  local self = setmetatable({ name = "settings" }, Settings)
  self.menu = MenuList.new({})
  self.cb = store.on_change(function() self:rebuild() end)
  self:rebuild()
  return self
end

function Settings:leave() store.off_change(self.cb) end

local function quality_text(x) return x == 0 and I.t("player.auto") or (x .. "p") end

function Settings:rebuild()
  local me = self
  local function rb() me:rebuild() end
  local items = {}
  local function add(it) items[#items + 1] = it end

  add({ kind = "section", label = I.t("settings.account") })
  if account.signed_in() then
    local p = account.profile()
    add({ kind = "info", label = (p and p.name) or I.t("account.signedIn"), value = (p and p.handle) or "" })
    add({ kind = "button", label = I.t("account.signOut"), danger = true, on = function() account.sign_out(); rb() end })
    add({ kind = "note", text = I.t("account.signedInNote") })
  else
    add({ kind = "button", label = I.t("account.signIn"), on = function() App.push(require("screens.signin").new()) end })
    add({ kind = "note", text = I.t("account.signedOutNote") })
  end

  add({ kind = "section", label = I.t("settings.general") })
  local lang = store.get("uiLanguage")
  add({ kind = "choice", label = I.t("settings.language"), value = lang == "ja" and "日本語" or lang == "en" and "English" or I.t("settings.languageAuto"),
    on = function()
      pick(I.t("settings.language"), { { label = I.t("settings.languageAuto"), value = "auto" }, { label = "日本語", value = "ja" }, { label = "English", value = "en" } },
        lang, function(v) store.set("uiLanguage", v); App.roots = {}; App.pop_to_root(); App.goto_tab(App.tab); App.push(Settings.new()) end)
    end })
  local region, rname = store.region(), store.region()
  for _, r in ipairs(store.REGIONS) do if r[1] == region then rname = r[2] end end
  add({ kind = "choice", label = I.t("settings.region"), value = rname, on = function()
    local opts = {}
    for _, r in ipairs(store.REGIONS) do opts[#opts + 1] = { label = r[2], value = r[1] } end
    pick(I.t("settings.region"), opts, region, function(v) store.set("contentRegion", v); rb() end)
  end })

  add({ kind = "section", label = I.t("settings.playback") })
  add({ kind = "toggle", label = I.t("settings.autoplay"), get = function() return store.get("autoplay") end, set = function(v) store.set("autoplay", v) end })
  add({ kind = "toggle", label = I.t("settings.captionsAlways"), get = function() return store.get("captionsAlways") end, set = function(v) store.set("captionsAlways", v) end })
  add({ kind = "choice", label = I.t("settings.defaultQuality"), value = quality_text(store.get("maxQuality")), on = function()
    local opts = {}
    for _, q in ipairs { 144, 240, 360, 480 } do opts[#opts + 1] = { label = quality_text(q), value = q } end
    pick(I.t("settings.defaultQuality"), opts, store.get("maxQuality"), function(v) store.set("maxQuality", v); Player.max_height = v; rb() end)
  end })
  local sp = store.get("playbackSpeed")
  add({ kind = "choice", label = I.t("settings.defaultSpeed"), value = sp == 1 and I.t("player.normal") or (sp .. "x"), on = function()
    local opts = {}
    for _, s in ipairs { 0.5, 0.75, 1, 1.25, 1.5, 2 } do opts[#opts + 1] = { label = s == 1 and I.t("player.normal") or (s .. "x"), value = s } end
    pick(I.t("settings.defaultSpeed"), opts, sp, function(v) store.set("playbackSpeed", v); Player.speed = v; rb() end)
  end })
  add({ kind = "choice", label = I.t("settings.fps"), value = tostring(store.get("videoFps")) .. " fps", on = function()
    pick(I.t("settings.fps"), { { label = "24 fps", value = 24 }, { label = "30 fps", value = 30 } }, store.get("videoFps"), function(v) store.set("videoFps", v); rb() end)
  end })

  add({ kind = "toggle", label = I.t("settings.autoSync"), get = function() return store.get("autoSync") ~= false end, set = function(v) store.set("autoSync", v) end })
  local off = store.get("avOffsetMs") or 0
  add({ kind = "choice", label = I.t("settings.avOffset"), value = string.format("%+d ms", off), on = function()
    local opts = {}
    for _, v in ipairs { -100, -60, -40, -20, 0, 20, 40, 60, 100 } do opts[#opts + 1] = { label = string.format("%+d ms", v), value = v } end
    pick(I.t("settings.avOffset"), opts, off, function(v) store.set("avOffsetMs", v); rb() end)
  end })

  add({ kind = "section", label = I.t("settings.privacy") })
  add({ kind = "toggle", label = I.t("settings.pauseHistory"), get = function() return store.get("pauseHistory") end, set = function(v) store.set("pauseHistory", v) end })
  add({ kind = "button", label = I.t("settings.clearHistory"), danger = true, on = function()
    require("screens.library").confirm(I.t("library.confirmClear"), I.t("common.delete"), function() store.clear_history() end)
  end })
  add({ kind = "button", label = I.t("settings.clearSearch"), on = function() store.clear_searches(); App.toast(I.t("settings.clearSearch")) end })
  add({ kind = "button", label = I.t("settings.clearCache"), on = function()
    os.execute("rm -f '" .. store.dir .. "/imgcache/'* 2>/dev/null")
    App.toast(I.t("settings.clearCache"))
  end })

  add({ kind = "section", label = I.t("settings.device") })
  add({ kind = "choice", label = I.t("settings.buttons"), value = "", on = function() App.push(require("screens.buttons").new()) end })
  add({ kind = "choice", label = I.t("settings.server"), value = (store.server.base or ""):gsub("^https?://", ""), on = function()
    App.push(require("screens.gate").new(true))
  end })

  add({ kind = "section", label = I.t("settings.about") })
  add({ kind = "info", label = I.t("settings.version"), value = VERSION })
  add({ kind = "button", label = I.t("diag.title"), on = function() App.push(require("screens.diag").new()) end })
  add({ kind = "note", text = I.t("settings.disclaimer") })
  add({ kind = "button", label = I.t("settings.quit"), danger = true, on = function() love.event.quit() end })
  local sel = self.menu.sel
  self.menu:set_items(items)
  if sel and items[sel] then self.menu.sel = sel; self.menu:fix_sel(1) end
end

function Settings:action(act, kind)
  if kind == "release" then return false end
  return self.menu:action(act, kind)
end

function Settings:resume() self:rebuild(); App.dirty = true end
function Settings:update(dt) self.menu:update(dt) end
function Settings:draw()
  NavBar.draw(I.t("settings.title"))
  self.menu:draw(0, NavBar.H, W, H - NavBar.H - App.bottom_inset())
end

return Settings
