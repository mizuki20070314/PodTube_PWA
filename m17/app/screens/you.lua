-- "You" tab: the account and the library (S.library in the PWA)
local theme = require("ui.theme")
local D = require("ui.draw")
local T = require("ui.text")
local MenuList = require("ui.menulist")
local store = require("core.store")
local account = require("core.account")
local I = require("core.i18n")

local c = theme.c
local W, H = theme.W, theme.H

local You = {}
You.__index = You

local function count(n) return n > 0 and tostring(n) or "" end

function You.new()
  local self = setmetatable({ name = "you" }, You)
  self.menu = MenuList.new({})
  self.cb = store.on_change(function() self:rebuild() end)
  self:rebuild()
  account.on_change = account.on_change   -- keep whatever the home screen set
  return self
end

function You:rebuild()
  local signed = account.signed_in()
  local lib = require("screens.library")
  local function push(f) return function() App.push(f()) end end
  local items = {}
  local Downloads = require("core.downloads")
  local dcount = #Downloads.records() + Downloads.pending_count()
  local p = account.profile()
  if signed then
    items[#items + 1] = { kind = "item", avatar = (p and p.avatar) or "", label = (p and p.name) or I.t("account.signedIn"), sub = (p and p.handle) or "",
      on = function()
        App.open_sheet({ title = (p and p.name) or I.t("account.signedIn"), items = {
          { label = I.t("account.signOut"), icon = "logout", danger = true, on = function() account.sign_out() end } } })
      end }
    items[#items + 1] = { kind = "item", icon = "history", label = I.t("library.history"), on = push(function() return lib.account("history") end) }
    items[#items + 1] = { kind = "item", icon = "file_download", label = I.t("library.downloads"), count = count(dcount), on = function() App.push(require("screens.downloads").new()) end }
    items[#items + 1] = { kind = "item", icon = "playlist_play", label = I.t("library.playlists"), on = push(function() return lib.account("playlists") end) }
    items[#items + 1] = { kind = "item", icon = "watch_later", label = I.t("library.watchLater"), on = push(function() return lib.account("watchLater") end) }
    items[#items + 1] = { kind = "item", icon = "thumb_up_outline", label = I.t("library.liked"), on = push(function() return lib.account("liked") end) }
  else
    items[#items + 1] = { kind = "item", icon = "account_circle_outline", label = I.t("account.signIn"), sub = I.t("account.signInHint"),
      on = function() App.push(require("screens.signin").new()) end }
    items[#items + 1] = { kind = "item", icon = "history", label = I.t("library.history"), count = count(#store.history()), on = push(function() return lib.stored("history") end) }
    items[#items + 1] = { kind = "item", icon = "file_download", label = I.t("library.downloads"), count = count(dcount), on = function() App.push(require("screens.downloads").new()) end }
    items[#items + 1] = { kind = "item", icon = "playlist_play", label = I.t("library.playlists"), count = count(#store.playlists()), on = push(function() return lib.user_playlists() end) }
    items[#items + 1] = { kind = "item", icon = "watch_later", label = I.t("library.watchLater"), count = count(#store.watch_later()), on = push(function() return lib.stored("watchLater") end) }
    items[#items + 1] = { kind = "item", icon = "thumb_up_outline", label = I.t("library.liked"), count = count(#store.liked()), on = push(function() return lib.stored("liked") end) }
  end
  items[#items + 1] = { kind = "item", icon = "settings_outline", label = I.t("library.settings"), on = function() App.push(require("screens.settings").new()) end }
  self.menu:set_items(items)
end

function You:scroll_top() self.menu.sel = 1; self.menu.target = 0 end
function You:resume() self:rebuild(); App.dirty = true end

function You:action(act, kind)
  if kind == "release" then return false end
  return self.menu:action(act, kind)
end

function You:update(dt) self.menu:update(dt) end

function You:draw()
  local x, w = App.content_rect()
  T.print(I.t("tab.you"), x + 14, 3, 18, "bold", c.text)
  D.rect(x, 26, w, 1, c.divider)
  self.menu:draw(x, 28, w, H - 28 - App.bottom_inset())
end

return You
