-- Playback engine: ffmpeg decodes the HLS streams (software h264 + aac) into two pipes; threads feed ALSA (audio) and collect
-- frames (video); the main thread picks the frame that belongs to the audio clock and draws it through a YUV shader.
-- The command line (player/ffargs.lua) makes frame i of the picture pipe the picture of media time start + i/fps and sample n of
-- the audio pipe the sound of media time start + n/rate; the clock (player/clock.lua) is the media time that is audible now.
local ffi = require("ffi")
local Proc = require("core.proc")
local log = require("core.log")
local shared = require("player.shared")
local ffargs = require("player.ffargs")
local Clock = require("player.clock")
local syncmon = require("player.syncmon")

local E = { gen = 0 }

local g = love.graphics
local shader
local cur           -- the running playback: {spec, proc, state(ByteData), st(struct), channels..., images...}

local function get_shader()
  if not shader then
    shader = g.newShader [[
      uniform Image U;
      uniform Image V;
      vec4 effect(vec4 color, Image Y, vec2 uv, vec2 sc) {
        float y = (Texel(Y, uv).r - 0.0627) * 1.1644;
        float u = Texel(U, uv).r - 0.5;
        float v = Texel(V, uv).r - 0.5;
        vec3 rgb = vec3(y + 1.7927 * v, y - 0.2132 * u - 0.5329 * v, y + 2.1124 * u);
        return vec4(clamp(rgb, 0.0, 1.0), 1.0) * color;
      }
    ]]
  end
  return shader
end

--- spec = { vurl=, aurl= | single=, start=seconds, fps=, fps_arg=, w=, h=, speed=, av_offset=, latency=microseconds, threads= }
function E.start(spec)
  E.stop()
  E.gen = E.gen + 1
  local id = E.gen
  spec.speed = spec.speed or 1
  spec.rate = 44100
  local state = love.data.newByteData(ffi.sizeof("pt_audio_state"))
  local st = ffi.cast("pt_audio_state*", state:getFFIPointer())
  ffi.fill(state:getFFIPointer(), ffi.sizeof("pt_audio_state"), 0)

  local argv = ffargs.build(spec)
  local proc, err = Proc.spawn(argv, {
    pipes = { { fd = 3, size = 1048576 }, { fd = 4, size = 262144 } },
    log = "/tmp/pt_ffmpeg.log",
  })
  if not proc then
    log.err("engine: cannot start ffmpeg:", err)
    return nil, err
  end
  log.info("engine: ffmpeg pid", proc.pid, "start", spec.start, "speed", spec.speed, "latency", spec.latency or 120000)

  local vch, fch = "vframes" .. id, "vfree" .. id
  local vthread = love.thread.newThread("player/video_thread.lua")
  local athread = love.thread.newThread("player/audio_thread.lua")
  vthread:start({ fd = proc.fds[3], w = spec.w, h = spec.h, state = state, out = vch, free = fch, sets = spec.sets or 8 })
  athread:start({ fd = proc.fds[4], rate = spec.rate, channels = 2, state = state, latency = spec.latency or 120000 })

  local cw, ch = math.floor((spec.w + 1) / 2), math.floor((spec.h + 1) / 2)
  local function plane(w, h)
    local id = love.image.newImageData(w, h, "r8")
    local img = g.newImage(id)
    img:setFilter("linear", "linear")
    img:setWrap("clamp", "clamp")
    return img
  end
  cur = {
    spec = spec, proc = proc, state = state, st = st, vch = love.thread.getChannel(vch), fch = love.thread.getChannel(fch),
    vthread = vthread, athread = athread,
    Y = plane(spec.w, spec.h), U = plane(cw, ch), V = plane(cw, ch),
    shown = nil,            -- index of the frame on the textures
    shown_ft = nil,         -- the media time of that frame
    pending = nil,          -- a frame taken from the channel that is not due yet
    started = love.timer.getTime(),
    frames_in = 0, dropped = 0, displayed = 0,
    video_eof = false, total_frames = nil,
    paused = false, pause_clock = nil,
    last_clock = spec.start or 0,
    clk = Clock.new(spec.start or 0, spec.rate, spec.speed), clk_in = {},
    skew = nil,             -- smoothed (clock - picture time) of the pictures shown: the picture's lateness
    late = 0, late_for = 0, -- how overdue the next picture is / for how long it has been overdue by more than syncmon.LATE_S
    progress_time = love.timer.getTime(),
  }
  E.active = cur
  return cur
end

function E.is_active() return cur ~= nil end

--- stops everything (kills ffmpeg, tells the threads to leave)
function E.stop()
  if not cur then return end
  local c = cur
  cur = nil
  E.active = nil
  c.st.cmd = shared.CMD_STOP
  Proc.kill(c.proc, 9)
  -- the descriptors belong to the threads (they close them); reap ffmpeg now (it is dead after SIGKILL)
  for _ = 1, 20 do
    if Proc.reap(c.proc) then break end
    love.timer.sleep(0.005)
  end
  -- give the pool back so that the video thread can leave
  c.vch:clear()
  c.fch:clear()
  for _, img in ipairs { c.Y, c.U, c.V } do img:release() end
end

--- media time (seconds) of what is audible right now; nil until the first audio data.
function E.clock()
  local c = cur
  if not c then return nil end
  local st, i = c.st, c.clk_in
  i.started, i.seq, i.frames, i.delay, i.eof = st.state ~= shared.STATE_START, st.seq, st.frames, st.delay, st.state == shared.STATE_EOF
  local t = c.clk:get(love.timer.getTime(), i)
  if t and not c.paused then c.last_clock = t end
  return t
end

function E.set_paused(on)
  if not cur then return end
  if on == cur.paused then return end
  if on then
    cur.pause_clock = E.clock()
    cur.st.cmd = shared.CMD_PAUSE
    cur.clk:pause()
  else
    cur.st.cmd = shared.CMD_RUN
    cur.pause_clock = nil
    cur.clk:resume()
    cur.late_for = 0
    cur.progress_time = love.timer.getTime()
  end
  cur.paused = on
end

--- current position for the UI (keeps the last value while paused / waiting)
function E.position()
  local c = cur
  if not c then return 0 end
  if c.paused and c.pause_clock then return c.pause_clock end
  return E.clock() or c.last_clock
end

local function release_set(c, set)
  c.fch:push(set)
end

--- Called every frame: returns true when a new picture was put on the textures.
function E.update(dt)
  local c = cur
  if not c then return false end
  local spec = c.spec
  local st = c.st
  local changed = false
  local now = love.timer.getTime()
  local clk = (not c.paused) and E.clock() or nil
  local fps = spec.fps or 30
  local period = 1 / fps
  local t0 = (spec.start or 0) + (spec.av_offset or 0)
  local best -- the newest frame that is due
  local limit = 6
  while limit > 0 do
    limit = limit - 1
    if not c.pending then
      c.pending = c.vch:pop()
      if not c.pending then break end
      if c.pending.eof then
        c.video_eof = true
        c.total_frames = c.pending.frames
        c.pending = nil
        break
      end
      c.frames_in = c.frames_in + 1
      c.pending.ft = t0 + c.pending.index / fps        -- the media time of this picture
    end
    local f = c.pending
    local due
    if c.shown == nil and (clk == nil or c.paused) then
      due = true                                       -- the first picture comes up as soon as it exists
    elseif clk == nil then
      due = false
    else
      due = f.ft <= clk + period * 0.5
    end
    if not due then break end
    if best then release_set(c, best.set); c.dropped = c.dropped + 1 end
    best = f
    c.pending = nil
    if c.shown == nil and not clk then break end       -- only the first one
  end
  if best then
    c.Y:replacePixels(best.set[1])
    c.U:replacePixels(best.set[2])
    c.V:replacePixels(best.set[3])
    release_set(c, best.set)
    c.shown, c.shown_ft = best.index, best.ft
    c.displayed = c.displayed + 1
    if clk then
      local sk = clk - best.ft
      c.skew = c.skew and (c.skew * 0.9 + sk * 0.1) or sk
    end
    c.first_pic_time = c.first_pic_time or now
    changed = true
  end

  -- how far behind the sound is the picture?  (the next picture is due at shown_ft + period)
  if clk and c.shown_ft and not c.video_eof and st.state == shared.STATE_PLAY then
    local late = clk - (c.shown_ft + period)
    c.late = late > 0 and late or 0
    -- the first seconds are the decoder catching up with the sound that started before the first picture
    if late > syncmon.LATE_S and now - c.first_pic_time > 4.0 then c.late_for = c.late_for + (dt or 0) else c.late_for = 0 end
  else
    c.late, c.late_for = 0, 0
  end
  if c.p_seq ~= st.seq or c.p_frames ~= c.frames_in then
    c.p_seq, c.p_frames, c.progress_time = st.seq, c.frames_in, now
  end
  return changed
end

--- 'starting' | 'playing' | 'paused' | 'buffering' | 'ended' | 'error'
function E.status()
  local c = cur
  if not c then return "idle" end
  local st = c.st
  if st.state == shared.STATE_ERROR then return "error" end
  if c.paused then return "paused" end
  if st.state == shared.STATE_START then
    if Proc.reap(c.proc) and c.frames_in == 0 then return "error" end
    return "starting"
  end
  if st.state == shared.STATE_EOF and c.video_eof and not c.pending then
    return "ended"
  end
  -- audio is flowing but nothing new for a while: waiting for data
  local seq = st.seq
  local now = love.timer.getTime()
  if c.last_seq ~= seq then c.last_seq, c.last_seq_time = seq, now end
  if st.state == shared.STATE_PLAY and now - (c.last_seq_time or now) > 0.6 and not (st.state == shared.STATE_EOF) then return "buffering" end
  return "playing"
end

function E.has_picture() return cur ~= nil and cur.shown ~= nil end

--- numbers for syncmon.step()
function E.health()
  local c = cur
  if not c then return nil end
  local now = love.timer.getTime()
  local live = (not c.paused) and c.st.state == shared.STATE_PLAY
  return { late = c.late, late_for = c.late_for, skew = c.skew, xruns = c.st.xruns, stalled_for = live and (now - c.progress_time) or 0 }
end

function E.stats()
  local c = cur
  if not c then return nil end
  return { frames = c.frames_in, displayed = c.displayed, dropped = c.dropped, xruns = c.st.xruns,
    delay_ms = c.st.delay * 1000 / c.spec.rate, w = c.spec.w, h = c.spec.h, fps = c.spec.fps, clock = c.last_clock,
    skew_ms = (c.skew or 0) * 1000, late_ms = c.late * 1000, latency_ms = (c.spec.latency or 120000) / 1000 }
end

--- draws the picture inside x,y,w,h (aspect ratio kept); returns the rectangle used
function E.draw(x, y, w, h, alpha)
  local c = cur
  if not c or not c.shown then return nil end
  local vw, vh = c.spec.w, c.spec.h
  local s = math.min(w / vw, h / vh)
  local dw, dh = vw * s, vh * s
  local dx, dy = x + (w - dw) / 2, y + (h - dh) / 2
  local sh = get_shader()
  g.setShader(sh)
  sh:send("U", c.U)
  sh:send("V", c.V)
  g.setColor(1, 1, 1, alpha or 1)
  g.draw(c.Y, dx, dy, 0, dw / vw, dh / vh)
  g.setShader()
  return dx, dy, dw, dh
end

return E
