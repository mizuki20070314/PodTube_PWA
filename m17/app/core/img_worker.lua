-- Image worker thread: downloads (curl) into the disk cache and decodes.
--   in : channel "img_req"  {id=, url=, path=}            (or "quit")
--   out: channel "img_res"  {id=, image=<ImageData>} or {id=, err=}
require("love.image")
require("love.data")
require("love.filesystem")
local req = love.thread.getChannel("img_req")
local res = love.thread.getChannel("img_res")

local function shq(s) return "'" .. tostring(s):gsub("'", "'\\''") .. "'" end

local function exists(p)
  local f = io.open(p, "rb")
  if f then f:close() return true end
  return false
end

while true do
  local job = req:demand()
  if job == "quit" then break end
  local ok_file = exists(job.path)
  if not ok_file then
    local tmp = job.path .. ".part" .. job.id
    local p = io.popen("LD_PRELOAD= LD_LIBRARY_PATH=/usr/lib:/lib curl -sS -f -L -m 30 --connect-timeout 15 -o " .. shq(tmp) .. " " .. shq(job.url) .. " 2>&1; echo $?", "r")
    local out = p and p:read("*a") or ""
    if p then p:close() end
    local rc = tonumber(out:match("(%d+)%s*$")) or 1
    if rc == 0 and exists(tmp) then
      os.remove(job.path)
      os.rename(tmp, job.path)
      ok_file = true
    else
      os.remove(tmp)
      res:push({ id = job.id, err = "download failed (" .. rc .. ")" })
    end
  end
  if ok_file then
    local f = io.open(job.path, "rb")
    local data = f and f:read("*a")
    if f then f:close() end
    if data and #data > 100 then
      local ok, img = pcall(function()
        return love.image.newImageData(love.filesystem.newFileData(data, "i.jpg"))
      end)
      if ok and img then
        res:push({ id = job.id, image = img })
      else
        os.remove(job.path)
        res:push({ id = job.id, err = "decode failed" })
      end
    else
      os.remove(job.path)
      res:push({ id = job.id, err = "empty file" })
    end
  end
end
