-- Import of subscription files (PT.parseSubscriptions + importChannels in the PWA): Google Takeout CSV, NewPipe / Piped /
-- FreeTube JSON, OPML, or any text with channel ids (UC...).  The files are read from <app>/import/ (put them there from the PC).
local store = require("core.store")
local Net = require("core.net")
local json = require("lib.json")
local U = require("lib.util")
local I = require("core.i18n")
local log = require("core.log")

local M = {}

--- the first channel id (UC + 22 characters) in s
local function find_uc(s)
  if type(s) ~= "string" then return nil end
  for m in s:gmatch("UC[%w_%-]+") do
    if #m >= 24 then return m:sub(1, 24) end
  end
  return nil
end

function M.parse(text)
  local found, order = {}, {}
  local function add(id, name)
    if not found[id] then
      found[id] = { id = id, name = name or "", handle = "", avatar = "", subscribers = "", videoCount = "" }
      order[#order + 1] = id
    elseif found[id].name == "" and name and name ~= "" then
      found[id].name = name
    end
  end
  local trimmed = U.trim(text)
  local c1 = trimmed:sub(1, 1)
  if c1 == "{" or c1 == "[" then
    local ok, root = pcall(json.decode, trimmed)
    if ok and root then
      local function walk(node)
        if type(node) ~= "table" then return end
        local keys = {}
        for k in pairs(node) do keys[#keys + 1] = k end
        table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
        local sn = node.snippet
        local cands = { node.channelId, node.id, node.url, sn and sn.resourceId and sn.resourceId.channelId, node.xmlUrl }
        local id
        for _, cnd in ipairs(cands) do id = find_uc(cnd); if id then break end end
        if id then
          local name
          for _, n in ipairs { node.name, node.title, sn and sn.title } do if type(n) == "string" and n ~= "" then name = n; break end end
          add(id, name)
        end
        for _, k in ipairs(keys) do walk(node[k]) end
      end
      walk(root)
    end
  end
  if #order == 0 and trimmed:find(",", 1, true) then
    for line in trimmed:gmatch("[^\r\n]+") do
      local id = find_uc(line)
      if id then
        local cols, cur, q = {}, {}, false
        for ch in line:gmatch(".") do
          if ch == '"' then q = not q
          elseif ch == "," and not q then cols[#cols + 1] = table.concat(cur); cur = {}
          else cur[#cur + 1] = ch end
        end
        cols[#cols + 1] = table.concat(cur)
        add(id, #cols >= 3 and cols[3] or "")
      end
    end
  end
  if #order == 0 and trimmed:find("<outline", 1, true) then
    for tag in text:gmatch("<outline[^>]*>") do
      local id = find_uc(tag)
      if id then
        local nm = tag:match('text="([^"]*)"') or tag:match('title="([^"]*)"')
        if nm then nm = nm:gsub("&amp;", "&"):gsub("&quot;", '"') end
        add(id, nm)
      end
    end
  end
  if #order == 0 then
    for m in text:gmatch("UC[%w_%-]+") do
      if #m >= 24 then add(m:sub(1, 24), "") end
    end
  end
  local out = {}
  for _, id in ipairs(order) do out[#out + 1] = found[id] end
  return out
end

--- adds the channels to the local subscriptions and fills in names / avatars in the background (3 at a time)
local function add_channels(channels)
  local known, added = {}, {}
  for _, ch in ipairs(store.subscriptions()) do known[ch.id] = true end
  for _, ch in ipairs(channels) do
    if not known[ch.id] then known[ch.id] = true; added[#added + 1] = ch end
  end
  store.merge_subscriptions(added)
  local queue = {}
  for _, ch in ipairs(added) do queue[#queue + 1] = ch end
  local running = 0
  local function pump()
    while running < 3 and #queue > 0 do
      local ch = table.remove(queue, 1)
      running = running + 1
      Net.get("channelbasics", { id = ch.id }, function(err, info)
        running = running - 1
        if not err and info and info.name then
          local list = store.subscriptions()
          for i, x in ipairs(list) do
            if x.id == ch.id then
              list[i] = { id = info.id, name = info.name, handle = info.handle, avatar = info.avatar, subscribers = info.subscribers, videoCount = info.videoCount }
              store.notify()
              store.later("subs")
              break
            end
          end
        end
        pump()
      end)
    end
  end
  pump()
  return #added
end

--- reads every file in <app dir>/import/ ; returns how many channels were added (or nil, reason)
function M.run()
  local dir = love.filesystem.getSource() .. "/../import"
  local p = io.popen("ls -1 '" .. dir .. "' 2>/dev/null", "r")
  if not p then return nil, "no folder" end
  local all = {}
  for name in p:lines() do
    local text = U.read_file(dir .. "/" .. name)
    if text then
      for _, ch in ipairs(M.parse(text)) do all[#all + 1] = ch end
    end
  end
  p:close()
  if #all == 0 then return nil, "nothing found" end
  return add_channels(all)
end

M.dir_hint = "/mnt/sdcard/Ports/PodTube/import/"

return M
