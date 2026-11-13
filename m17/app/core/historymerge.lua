-- HistoryMerge (09a-screens.js): when signed in, the history shows the account's list with this device's plays among it.
--
-- The account's list says in which ORDER things were watched, not when; the plays of this app know their time.  A video that is
-- in both lists ties the two together (an "anchor").  Between the anchors the account's entries get a time in proportion to
-- their place, and a play that the account does not list goes where its time falls.  The pages are merged one after the other,
-- each against everything loaded before it, so a play older than what is loaded appears when the list reaches its time (and at
-- the very end when the account never had it).
local store = require("core.store")

local M = { days = 30, limit = 40, fresh_ms = 2 * 3600 * 1000 }

local function now_ms() return os.time() * 1000 end

--- plays of this app, newest first: {video=, t=ms}
function M.entries()
  local out = {}
  for _, e in ipairs(store.history()) do out[#out + 1] = { video = e.video, t = e.watchedAt } end
  return out
end

function M.videos_of(it)
  if it.type == "video" then return { it.video } end
  if it.type == "shorts" then return it.videos end
  return {}
end

--- a time for every video of the account's list (`ids`, in its order), from the ones this app played; nil when none was
function M.estimate(ids, by_id, now)
  local anchors = {}
  local n = #ids
  for i = 1, n do
    local e = by_id[ids[i]]
    if e then anchors[#anchors + 1] = { i = i, t = e.t } end
  end
  if #anchors == 0 then return nil end
  for i = #anchors - 1, 1, -1 do
    if anchors[i].t < anchors[i + 1].t then anchors[i].t = anchors[i + 1].t end
  end
  for i = 1, #anchors do
    if anchors[i].t > now then anchors[i].t = now end
  end
  local ctrl = { { i = 0, t = now } }
  for _, a in ipairs(anchors) do ctrl[#ctrl + 1] = a end
  local last = ctrl[#ctrl]
  local pace = math.max(60000, (now - last.t) / last.i)
  local est = {}
  local c = 1
  for i = 1, n do
    while c + 1 <= #ctrl and ctrl[c + 1].i <= i do c = c + 1 end
    local lo, hi = ctrl[c], ctrl[c + 1]
    if hi then est[i] = lo.t + (hi.t - lo.t) * (i - lo.i) / (hi.i - lo.i)
    else est[i] = lo.t - pace * (i - lo.i) end
  end
  return est
end

--- one merge per list; session.page(items, last) takes the account's items of the next page and returns them with this
--- app's plays in their places
function M.session(o)
  o = o or {}
  local now = o.now or now_ms()
  local entries = o.entries or M.entries()
  local by_id = {}
  for _, e in ipairs(entries) do
    if e.t and e.t > 0 and not by_id[e.video.id] then by_id[e.video.id] = e end
  end
  local cutoff = now - M.days * 86400000
  local pending = {}
  for _, e in ipairs(entries) do
    if e.t >= cutoff and by_id[e.video.id] == e then pending[#pending + 1] = e end
  end
  local ids, listed, pages = {}, {}, 0
  local s = { inserted = {} }

  local function as_item(e)
    s.inserted[e.video.id] = true
    return { type = "video", video = e.video }
  end

  function s.page(items, last)
    local first = pages == 0
    pages = pages + 1
    local starts = {}
    for j, it in ipairs(items) do
      local vs = M.videos_of(it)
      starts[j] = (#vs > 0) and (#ids + 1) or -1
      for _, v in ipairs(vs) do ids[#ids + 1] = v.id; listed[v.id] = true end
    end
    local still = {}
    for _, e in ipairs(pending) do if not listed[e.video.id] then still[#still + 1] = e end end
    pending = still
    if #pending == 0 then return items end
    local est = M.estimate(ids, by_id, now)
    local before, keep, tail = {}, {}, {}
    for j = 1, #items do before[j] = {} end
    for _, e in ipairs(pending) do
      local k = -1
      if est then
        for j = 1, #items do
          if starts[j] >= 0 and est[starts[j]] < e.t then k = j; break end
        end
        -- directly after the video that is newer: in front of the headers that lead to the older one, never above the first header
        local m = k
        while m > 1 and starts[m - 1] < 0 do m = m - 1 end
        if k > 1 and m > 1 then k = m end
      elseif first and e.t >= now - M.fresh_ms and #items > 0 then
        k = 1
      end
      if k >= 1 then before[k][#before[k] + 1] = e else keep[#keep + 1] = e end
    end
    if last then tail = keep; keep = {} end
    pending = keep
    local out = {}
    for j, it in ipairs(items) do
      for _, e in ipairs(before[j]) do out[#out + 1] = as_item(e) end
      out[#out + 1] = it
    end
    for _, e in ipairs(tail) do out[#out + 1] = as_item(e) end
    return out
  end
  return s
end

--- the videos for a short shelf: the account's, with this app's plays among them
function M.shelf(account_videos, limit)
  local s = M.session()
  local items = {}
  for _, v in ipairs(account_videos) do items[#items + 1] = { type = "video", video = v } end
  local out = s.page(items, false)
  local vids = {}
  for i = 1, math.min(limit, #out) do vids[i] = out[i].video end
  return vids
end

return M
