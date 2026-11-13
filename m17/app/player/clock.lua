-- The playback clock: the media time (seconds) of what is audible right now.
--
-- The audio thread publishes the position in steps of one ALSA write (about 25 ms), and the device's own delay is only known to a
-- period (30 ms): used raw, the picture would stutter.  A software clock runs with the wall clock and is pulled toward the
-- published position (a small phase-locked loop).  It never runs past the end of the audio that has been handed to the device:
-- when the sound stops (the pipe from ffmpeg is empty, the stream is buffering) the clock stops with it, so the picture waits for
-- the sound instead of running ahead of it - and does not have to be pulled back when the sound resumes.
--
-- Pure code (no LÖVE): tools/test_sync.py runs it with simulated time.
local Clock = {}
Clock.__index = Clock

local SNAP = 0.25            -- seconds: a bigger error than this is not smoothed (a jump)
local GAIN = 5               -- 1/s: how fast the software clock is pulled toward the published position

--- start: media time of audio sample 0; rate: samples per second; speed: playback speed (media seconds per audio second)
function Clock.new(start, rate, speed)
  return setmetatable({ start = start or 0, rate = rate or 44100, speed = speed or 1, paused = false }, Clock)
end

--- now: seconds (monotonic); st = { started = audio data has been written, seq = update counter, frames = samples written to the
--- device, delay = samples still queued in the device, eof = the audio stream has ended }.  Returns nil until the audio has started.
function Clock:get(now, st)
  if not st.started then return nil end
  local speed = self.speed
  if self.seq ~= st.seq then
    local played = st.frames - st.delay
    if played < 0 then played = 0 end
    self.m_ref = self.start + played / self.rate * speed
    self.m_wall = now
    self.seq = st.seq
  end
  if self.paused then return self.m_ref end
  -- the end of the audio handed to the device (not after the audio has ended for good: a picture that outlasts the sound plays on)
  local limit = st.eof and math.huge or (self.start + st.frames / self.rate * speed)
  local est = self.m_ref + (now - self.m_wall) * speed            -- the published position, carried forward to now
  local frozen = est >= limit
  if frozen then est = limit end
  if frozen or not self.sc then
    self.sc = est
  else
    local dt = now - self.sc_wall
    self.sc = self.sc + dt * speed
    local err = est - self.sc
    if math.abs(err) > SNAP then self.sc = est else self.sc = self.sc + err * math.min(1, dt * GAIN) end
  end
  self.sc_wall = now
  self.frozen = frozen
  return self.sc
end

function Clock:pause() self.paused = true end

--- the software clock starts again from the device's position
function Clock:resume()
  self.paused = false
  self.sc, self.seq = nil, nil
end

return Clock
