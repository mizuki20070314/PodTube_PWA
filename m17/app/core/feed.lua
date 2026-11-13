-- Feed: a paginated list of videos / channels / playlists / shorts shelves (the data side of the PWA's FeedView).
--   fetch_first(cb, user_refresh, feed)        cb(err, page)   page = {items=, continuation=, endpoint=}
--   fetch_more(token, endpoint, cb, feed)      (defaults to POST continuation)
local Net = require("core.net")
local log = require("core.log")

local Feed = {}
Feed.__index = Feed

function Feed.new(opts)
  local f = setmetatable({}, Feed)
  f.o = opts or {}
  f.items = {}
  f.seen = {}
  f.continuation = nil
  f.endpoint = f.o.endpoint or "browse"
  f.generation = 0
  f.loading_more = false
  f.state = "idle"        -- idle | loading | ready | error | empty
  f.error = nil
  f.version = 0           -- bumped on every change, so a list can rebuild its layout
  return f
end

local function bump(f) f.version = f.version + 1; if App then App.dirty = true end end

function Feed:clear()
  self.generation = self.generation + 1
  self.items, self.seen, self.continuation = {}, {}, nil
  self.loading_more = false
  self.state = "idle"
  self.error = nil
  bump(self)
end

--- appends a page; returns how many rows were added
function Feed:append(page)
  local added = 0
  for _, it in ipairs(page.items or {}) do
    local t = it.type
    if t == "video" and it.video then
      if not self.seen[it.video.id] then
        self.seen[it.video.id] = true
        self.items[#self.items + 1] = it
        added = added + 1
      end
    elseif t == "channel" and it.channel then
      local k = "c:" .. it.channel.id
      if not self.seen[k] then self.seen[k] = true; self.items[#self.items + 1] = it; added = added + 1 end
    elseif t == "playlist" and it.playlist then
      local k = "p:" .. it.playlist.id
      if not self.seen[k] then self.seen[k] = true; self.items[#self.items + 1] = it; added = added + 1 end
    elseif t == "shorts" and it.videos then
      local fresh = {}
      for _, v in ipairs(it.videos) do
        if not self.seen[v.id] then self.seen[v.id] = true; fresh[#fresh + 1] = v end
      end
      if #fresh > 0 then self.items[#self.items + 1] = { type = "shorts", videos = fresh }; added = added + 1 end
    elseif t == "comment" and it.comment then
      self.items[#self.items + 1] = it
      added = added + 1
    elseif t == "text" and it.text then
      self.items[#self.items + 1] = it
      added = added + 1
    end
  end
  self.continuation = page.continuation
  if page.endpoint then self.endpoint = page.endpoint end
  bump(self)
  return added
end

--- replace the content with an already available page (library screens)
function Feed:set_page(page)
  self.generation = self.generation + 1
  self.items, self.seen, self.continuation = {}, {}, nil
  self:append(page)
  self.state = (#self.items > 0) and "ready" or "empty"
  bump(self)
end

function Feed:reload(user_refresh)
  local gen = self.generation + 1
  self.generation = gen
  self.loading_more = false
  if #self.items == 0 then self.state = "loading" end
  self.error = nil
  bump(self)
  self.o.fetch_first(function(err, page)
    if gen ~= self.generation then return end
    if err then
      if #self.items == 0 then self.state = "error"; self.error = err end
      bump(self)
      return
    end
    self.items, self.seen, self.continuation = {}, {}, nil
    self:append(page)
    self.state = (#self.items > 0) and "ready" or "empty"
    if self.o.did_receive_first_page then self.o.did_receive_first_page(page, self) end
    bump(self)
  end, user_refresh, self)
end

function Feed:more()
  local token = self.continuation
  if not token or self.loading_more or self.state ~= "ready" then return end
  self.loading_more = true
  local gen = self.generation
  local function done(err, page)
    if gen ~= self.generation then return end
    self.loading_more = false
    if err then self.continuation = nil; bump(self); return end
    local before = #self.items
    self:append(page)
    if #self.items == before and page.continuation == token then self.continuation = nil end
    bump(self)
  end
  if self.o.fetch_more then
    self.o.fetch_more(token, self.endpoint, done, self)
  else
    Net.post("continuation", { token = token, endpoint = self.endpoint }, done, { auth = self.endpoint == "tv" })
  end
  bump(self)
end

function Feed:videos()
  local out = {}
  for _, it in ipairs(self.items) do
    if it.type == "video" then out[#out + 1] = it.video end
  end
  return out
end

return Feed
