-- Comments panel (CommentsPanel in the PWA): the comments of a video with the sort choice and paging
local theme = require("ui.theme")
local D = require("ui.draw")
local T = require("ui.text")
local Feed = require("core.feed")
local FeedList = require("ui.feedlist")
local Net = require("core.net")
local I = require("core.i18n")

local c = theme.c
local W, H = theme.W, theme.H
local BAR = 26

local Comments = {}
Comments.__index = Comments

local function to_page(page)
  local items = {}
  for _, cm in ipairs(page.comments or {}) do items[#items + 1] = { type = "comment", comment = cm } end
  return { items = items, continuation = page.continuation }
end

function Comments.new(token, sort_tokens, count_text, first_page, video)
  local self = setmetatable({ name = "comments", token = token, sort_tokens = sort_tokens or {}, sort = 1, count = count_text or "" }, Comments)
  local me = self
  self.feed = Feed.new({
    endpoint = "comments",
    fetch_first = function(cb)
      local t = me.token
      if me.sort_tokens[me.sort] and me.sort > 1 then t = me.sort_tokens[me.sort].token end
      Net.post("comments", { token = t }, function(err, page) if err then cb(err) else cb(nil, to_page(page)) end end)
    end,
    fetch_more = function(tok, endpoint, cb)
      Net.post("comments", { token = tok }, function(err, page) if err then cb(err) else cb(nil, to_page(page)) end end)
    end,
  })
  self.list = FeedList.new(self.feed, { shoulder_page = true, empty_text = I.t("comments.empty") })
  if first_page and first_page.comments and #first_page.comments > 0 then
    self.feed:set_page(to_page(first_page))
  else
    self.feed:reload()
  end
  return self
end

function Comments:show_sort()
  local items = {}
  for i, s in ipairs(self.sort_tokens) do
    items[#items + 1] = { label = s.title, checked = i == self.sort, on = function()
      self.sort = i
      self.feed:clear(); self.list:reset(); self.feed:reload()
    end }
  end
  if #items > 0 then App.open_sheet({ title = I.t("comments.title"), items = items }) end
end

function Comments:action(act, kind)
  if kind == "release" then return false end
  if self.list:action(act, kind) then return true end
  if act == "x" and #self.sort_tokens > 1 then self:show_sort(); return true end
  return false
end

function Comments:update(dt) self.list:update(dt) end
function Comments:resume() App.dirty = true end

function Comments:draw()
  D.rect(0, 0, W, BAR, c.bg)
  D.rect(0, BAR - 1, W, 1, c.divider)
  D.icon("arrow_back", 5, 3, 20, c.text)
  local title = I.t("comments.title")
  T.print(title, 32, 5, 14, "bold", c.text)
  T.print(self.count, 32 + T.width(title, 14, "bold") + 8, 8, 11, "regular", c.secondary)
  if #self.sort_tokens > 1 then
    D.icon("swap_vert", W - 30, 3, 20, c.text)
    T.print("Ⓧ", W - 52, 7, 12, "bold", c.secondary)
  end
  self.list:draw(0, BAR, W, H - BAR - App.bottom_inset(), true)
end

return Comments
