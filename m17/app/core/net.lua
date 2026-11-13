-- The PodTube API (api.cgi) over curl.  Requests run on worker threads (curl through the PC tunnel's proxy when
-- present); results come back through a channel and are handed to the callbacks from Net.update().
local json = require("lib.json")
local log = require("core.log")
local store = require("core.store")
local U = require("lib.util")

local Net = {}

local req_ch, res_ch
local callbacks = {}
local next_id = 1
local workers = {}
Net.token_provider = nil   -- function(cb(err, token)) set by the account module
Net.stats = { sent = 0, failed = 0, active = 0 }

local CHILD_ENV = "LD_PRELOAD= LD_LIBRARY_PATH=/usr/lib:/lib "
Net.CHILD_ENV = CHILD_ENV

local NETWORK_CODES = { [5] = true, [6] = true, [7] = true, [28] = true, [35] = true, [52] = true, [55] = true, [56] = true, [60] = true }

function Net.init(n)
  req_ch = love.thread.getChannel("net_req")
  res_ch = love.thread.getChannel("net_res")
  for i = 1, n or 3 do
    local t = love.thread.newThread("core/net_worker.lua")
    t:start()
    workers[i] = t
  end
end

function Net.shutdown()
  for _ = 1, #workers do req_ch:push("quit") end
end

function Net.configured()
  return store.server and store.server.base and store.server.base ~= "" and store.server.key and store.server.key ~= ""
end

function Net.base() return (store.server.base or ""):gsub("/+$", "") end

--- visitor id (kept 14 days like the PWA)
local VISITOR_TTL = 14 * 86400
local function visitor()
  local r = store.visitor_rec
  if r and r.v and os.time() - (r.t or 0) < VISITOR_TTL then return r.v end
  return nil
end
local function set_visitor(v)
  if v and v ~= "" then
    store.visitor_rec = { v = v, t = os.time() }
    store.save_now("visitor")
  end
end

function Net.url(route, params)
  return Net.base() .. "/api.cgi/" .. route .. U.query(params)
end

local function build_cmd(id, method, route, opts, token)
  local args = { CHILD_ENV .. "curl", "-sS", "--compressed", "-m", tostring(opts.timeout or 60), "--connect-timeout", "20",
    "-w", U.shq("\n%{http_code}") }
  local function h(k, v) args[#args + 1] = "-H"; args[#args + 1] = U.shq(k .. ": " .. v) end
  h("X-PT-Key", store.server.key or "")
  h("X-PT-Hl", store.hl())
  h("X-PT-Gl", store.gl())
  local v = visitor()
  if v then h("X-PT-Visitor", v) end
  if token then h("X-PT-Token", token) end
  local tmp
  if method == "POST" then
    tmp = "/tmp/pt_req_" .. id .. ".json"
    U.write_file(tmp, json.encode(opts.body or {}))
    h("Content-Type", "application/json")
    args[#args + 1] = "--data-binary"
    args[#args + 1] = "@" .. tmp
  end
  args[#args + 1] = U.shq(Net.url(route, opts.params))
  local cmd = table.concat(args, " ")
  if tmp then cmd = cmd .. "; rm -f " .. tmp end
  return cmd
end

local function dispatch(id, method, route, opts, token, cb, tries)
  local cmd = build_cmd(id, method, route, opts, token)
  callbacks[id] = { cb = cb, method = method, route = route, opts = opts, token = token, tries = tries or 0 }
  Net.stats.sent = Net.stats.sent + 1
  Net.stats.active = Net.stats.active + 1
  req_ch:push({ id = id, cmd = cmd })
end

--- Net.request("GET"|"POST", route, {params=, body=, auth=, timeout=}, cb(err, data))
--- err = {code=, message=, status=}; the id can be passed to Net.cancel
function Net.request(method, route, opts, cb)
  opts = opts or {}
  if not Net.configured() then
    cb({ code = "locked", message = "no server configured", status = 0 }, nil)
    return nil
  end
  local id = next_id
  next_id = next_id + 1
  if opts.auth then
    if not Net.token_provider then
      cb({ code = "auth", message = "sign in required", status = 401 }, nil)
      return nil
    end
    callbacks[id] = { cb = cb, pending_token = true }
    Net.token_provider(function(err, token)
      local c = callbacks[id]
      if not c then return end           -- cancelled
      if err then callbacks[id] = nil; cb(err, nil); return end
      dispatch(id, method, route, opts, token, cb, 0)
    end)
    return id
  end
  dispatch(id, method, route, opts, nil, cb, 0)
  return id
end

function Net.get(route, params, cb, opts)
  opts = opts or {}
  opts.params = params
  return Net.request("GET", route, opts, cb)
end

function Net.post(route, body, cb, opts)
  opts = opts or {}
  opts.body = body or {}
  return Net.request("POST", route, opts, cb)
end

--- plain text of an absolute URL (HLS playlists; no API headers).  cb(err, text)
function Net.get_text(url, cb, timeout)
  local id = next_id
  next_id = next_id + 1
  local cmd = CHILD_ENV .. "curl -sS -L --compressed -m " .. tostring(timeout or 30) .. " --connect-timeout 15 -w "
    .. U.shq("\n%{http_code}") .. " " .. U.shq(url)
  callbacks[id] = { text = true, cb = cb, method = "GET", route = url }
  Net.stats.sent = Net.stats.sent + 1
  Net.stats.active = Net.stats.active + 1
  req_ch:push({ id = id, cmd = cmd })
  return id
end

--- runs a shell command on a worker thread; cb(stdout) (the command's own stderr is dropped)
function Net.shell(cmd, cb)
  local id = next_id
  next_id = next_id + 1
  callbacks[id] = { shell = true, cb = cb, method = "SHELL", route = "shell" }
  req_ch:push({ id = id, cmd = cmd })
  return id
end

function Net.cancel(id)
  if id then callbacks[id] = nil end
end

local function finish(r)
  local c = callbacks[r.id]
  Net.stats.active = math.max(0, Net.stats.active - 1)
  if not c then return end
  callbacks[r.id] = nil
  if c.shell then c.cb(r.out or ""); return end
  local out = r.out or ""
  local body, code = out:match("^(.*)\n(%d+)$")
  if body and tonumber(code) == 0 then body = nil end      -- curl's "000": no HTTP answer at all
  if not body then
    -- curl failed before it got an answer
    Net.stats.failed = Net.stats.failed + 1
    if NETWORK_CODES[r.code or 0] and c.method == "GET" and c.tries < 1 then
      log.warn("net: retry", c.route, "curl exit", r.code)
      dispatch(r.id, c.method, c.route, c.opts, c.token, c.cb, c.tries + 1)
      return
    end
    log.warn("net: failed", c.route, "curl exit", r.code)
    c.cb({ code = "network", message = "network", status = 0, curl = r.code }, nil)
    return
  end
  code = tonumber(code)
  if c.text then
    if code and code >= 200 and code < 300 then c.cb(nil, body) else
      Net.stats.failed = Net.stats.failed + 1
      c.cb({ code = "http", message = "HTTP " .. tostring(code), status = code or 0 }, nil)
    end
    return
  end
  local ok, data = pcall(json.decode, body)
  if not ok then data = nil end
  if code and code >= 200 and code < 300 and type(data) == "table" then
    if data._visitor then set_visitor(data._visitor); data._visitor = nil end
    c.cb(nil, data)
    return
  end
  local e = data and data.error
  local err = { code = e and e.code or "http", message = e and e.message or ("HTTP " .. tostring(code)), status = code or 0 }
  if code == 401 and err.code == "auth" and c.opts and c.opts.auth and c.tries < 1 and Net.refresh_token then
    Net.refresh_token(function(rerr, token)
      if rerr then c.cb(rerr, nil); return end
      dispatch(r.id, c.method, c.route, c.opts, token, c.cb, c.tries + 1)
    end)
    return
  end
  Net.stats.failed = Net.stats.failed + 1
  c.cb(err, nil)
end

function Net.update()
  if not res_ch then return end
  for _ = 1, 8 do
    local r = res_ch:pop()
    if not r then break end
    local ok, e = pcall(finish, r)
    if not ok then log.err("net callback:", e) end
    if App then App.dirty = true end
  end
end

return Net
