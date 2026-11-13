-- The codec's Master volume: MinUI's volume keys (keymon.elf) write only the left channel, which leaves the right one at 0.
-- After every volume key and now and then, the right channel is set to the left one's level.
local Net = require("core.net")
local I = require("core.i18n")

local M = { next_check = 0, busy = false }

local CMD = [[sh -c 'l=$(amixer -c 0 sget Master 2>/dev/null | sed -n "s/.*Front Left: Playback \([0-9]*\) \[\([0-9]*\)%\].*/\1 \2/p" | head -1); r=$(amixer -c 0 sget Master 2>/dev/null | sed -n "s/.*Front Right: Playback \([0-9]*\) .*/\1/p" | head -1); v=${l%% *}; if [ -n "$v" ] && [ "$v" != "$r" ]; then amixer -c 0 sset Master "$v" >/dev/null 2>&1; fi; echo "$l"']]

--- balance the channels; with `show` the level is shown as a toast
function M.balance(show)
  if M.busy then return end
  M.busy = true
  Net.shell(CMD, function(out)
    M.busy = false
    local v, pct = out:match("(%d+)%s+(%d+)")
    if show and pct then App.toast(string.format("%s %s%%", I.t("player.volume"), pct), 1.2) end
  end)
end

--- after a volume key: balance and show the level in ~0.25 s
function M.schedule_show() M.show_at = love.timer.getTime() + 0.25 end

function M.update(dt, playing)
  if M.show_at and love.timer.getTime() >= M.show_at then M.show_at = nil; M.balance(true) end
  local now = love.timer.getTime()
  if now >= M.next_check then
    M.next_check = now + (playing and 4 or 15)
    M.balance(false)
  end
end

return M
