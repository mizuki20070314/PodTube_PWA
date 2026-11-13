-- Audio thread: PCM (s16le, 2 channels) from the ffmpeg pipe -> ALSA.  ALSA's blocking write paces the thread; the position of
-- what is audible (frames written - frames still queued) is published in the shared state block for the A/V clock.
require("love.timer")
require("love.filesystem")
local ffi = require("ffi")
local args = ...
local shared = require("player.shared")

ffi.cdef [[
typedef struct _snd_pcm snd_pcm_t;
int snd_pcm_open(snd_pcm_t **pcm, const char *name, int stream, int mode);
int snd_pcm_close(snd_pcm_t *pcm);
int snd_pcm_set_params(snd_pcm_t *pcm, int format, int access, unsigned int channels, unsigned int rate, int soft_resample, unsigned int latency);
long snd_pcm_writei(snd_pcm_t *pcm, const void *buffer, unsigned long size);
int snd_pcm_recover(snd_pcm_t *pcm, int err, int silent);
int snd_pcm_delay(snd_pcm_t *pcm, long *delayp);
int snd_pcm_drop(snd_pcm_t *pcm);
int snd_pcm_drain(snd_pcm_t *pcm);
int snd_pcm_prepare(snd_pcm_t *pcm);
int read(int fd, void *buf, unsigned int n);
int close(int fd);
]]

local C = ffi.C
local st = ffi.cast("pt_audio_state*", args.state:getFFIPointer())
local fd, rate, channels = args.fd, args.rate or 44100, args.channels or 2
local frame_bytes = 2 * channels
st.rate = rate

local function finish(state, err)
  st.state = state
  st.err = err or 0
  st.seq = st.seq + 1
  C.close(fd)
end

local alsa = ffi.load("asound")
local h = ffi.new("snd_pcm_t*[1]")
local opened = false
for _ = 1, 40 do                                  -- the previous playback may still hold the device for a moment
  if st.cmd == shared.CMD_STOP then return finish(shared.STATE_EOF) end
  local rc = alsa.snd_pcm_open(h, "default", 0, 0)
  if rc == 0 then opened = true; break end
  love.timer.sleep(0.05)
end
if not opened then return finish(shared.STATE_ERROR, 1) end
local pcm = h[0]
if alsa.snd_pcm_set_params(pcm, 2, 3, channels, rate, 1, args.latency or 120000) ~= 0 then
  alsa.snd_pcm_close(pcm)
  return finish(shared.STATE_ERROR, 2)
end

local CHUNK = 4096
local buf = ffi.new("uint8_t[?]", CHUNK)
local carry = 0                                   -- bytes of an incomplete frame kept from the last read
local dl = ffi.new("long[1]")
local paused = false

local function publish(frames_added)
  st.frames = st.frames + frames_added
  if alsa.snd_pcm_delay(pcm, dl) == 0 then
    local d = tonumber(dl[0])
    if d < 0 then d = 0 end
    st.delay = d
  end
  st.seq = st.seq + 1
end

while true do
  local cmd = st.cmd
  if cmd == shared.CMD_STOP then break end
  if cmd == shared.CMD_PAUSE then
    if not paused then
      paused = true
      alsa.snd_pcm_drop(pcm)                       -- what is queued in the device is dropped: the pause is immediate
      st.delay = 0
      st.state = shared.STATE_PAUSED
      st.seq = st.seq + 1
    end
    love.timer.sleep(0.02)
  else
    if paused then
      paused = false
      alsa.snd_pcm_prepare(pcm)
    end
    local n = C.read(fd, buf + carry, CHUNK - carry)
    if n <= 0 then
      -- end of the stream: let the device play what it has
      alsa.snd_pcm_drain(pcm)
      break
    end
    n = n + carry
    local frames = math.floor(n / frame_bytes)
    carry = n - frames * frame_bytes
    local off = 0
    while frames > 0 and st.cmd ~= shared.CMD_STOP do
      local w = tonumber(alsa.snd_pcm_writei(pcm, buf + off, frames))
      if w < 0 then
        st.xruns = st.xruns + 1
        if alsa.snd_pcm_recover(pcm, w, 1) < 0 then love.timer.sleep(0.01) end
      else
        frames = frames - w
        off = off + w * frame_bytes
        publish(w)
        if st.state ~= shared.STATE_PLAY and st.cmd == shared.CMD_RUN then st.state = shared.STATE_PLAY end
      end
    end
    if carry > 0 then ffi.copy(buf, buf + n - carry, carry) end
  end
end

if st.cmd == shared.CMD_STOP then alsa.snd_pcm_drop(pcm) end
alsa.snd_pcm_close(pcm)
finish(shared.STATE_EOF)
