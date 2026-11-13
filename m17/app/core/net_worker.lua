-- Network worker thread: runs shell commands (curl) and sends back what they print.
--   in : channel "net_req"  {id=, cmd=, out_path=}          (or "quit")
--   out: channel "net_res"  {id=, out=<stdout>, code=<exit code>}
require("love.timer")
local req = love.thread.getChannel("net_req")
local res = love.thread.getChannel("net_res")

while true do
  local job = req:demand()
  if job == "quit" then break end
  local p = io.popen(job.cmd .. " 2>/dev/null", "r")
  local out = ""
  local code = -1
  if p then
    out = p:read("*a") or ""
    local ok, how, c = p:close()
    code = c or (ok and 0 or 1)
  end
  res:push({ id = job.id, out = out, code = code })
end
