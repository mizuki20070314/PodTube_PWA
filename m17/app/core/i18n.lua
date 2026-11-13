-- UI strings (ja / en) taken from the PWA
local strings = require("data.strings")
for k, v in pairs(require("data.strings_m17")) do strings[k] = v end
local store = require("core.store")

local I = {}

--- t("key") or t("key", arg) where the string contains %@
function I.t(key, arg)
  local pair = strings[key]
  if not pair then return key end
  local s = store.is_japanese() and pair[1] or pair[2]
  if arg ~= nil then
    s = s:gsub("%%@", function() return tostring(arg) end)
  end
  return s
end

function I.has(key) return strings[key] ~= nil end

return I
