local ffi = require("ffi")
local function p(...) print(...); io.stdout:flush() end
ffi.cdef[[
typedef struct _snd_pcm snd_pcm_t;
int snd_pcm_open(snd_pcm_t **pcm, const char *name, int stream, int mode);
int snd_pcm_close(snd_pcm_t *pcm);
const char *snd_strerror(int err);
int snd_pcm_set_params(snd_pcm_t *pcm, int format, int access, unsigned int channels, unsigned int rate, int soft_resample, unsigned int latency);
long snd_pcm_writei(snd_pcm_t *pcm, const void *buffer, unsigned long size);
int snd_pcm_recover(snd_pcm_t *pcm, int err, int silent);
int snd_pcm_delay(snd_pcm_t *pcm, long *delayp);
int snd_pcm_drain(snd_pcm_t *pcm);
]]
function love.load()
  local alsa = ffi.load("asound")
  local h = ffi.new("snd_pcm_t*[1]")
  local rc = alsa.snd_pcm_open(h, "default", 0, 0)
  p("open rc", rc, ffi.string(alsa.snd_strerror(rc)))
  if rc ~= 0 then return end
  local pcm = h[0]
  rc = alsa.snd_pcm_set_params(pcm, 2, 3, 2, 44100, 1, 100000)  -- S16_LE, RW_INTERLEAVED, 2ch, 44.1k, resample, 100ms
  p("set_params rc", rc, ffi.string(alsa.snd_strerror(rc)))
  local N = 4410
  local buf = ffi.new("int16_t[?]", N * 2)
  local dl = ffi.new("long[1]")
  local t0 = love.timer.getTime()
  local written = 0
  for blk = 0, 9 do   -- 1 second of 440 Hz
    for i = 0, N - 1 do
      local v = math.floor(math.sin(2 * math.pi * 440 * (written + i) / 44100) * 6000)
      buf[2*i] = v; buf[2*i+1] = v
    end
    local w = alsa.snd_pcm_writei(pcm, buf, N)
    if w < 0 then p("write err", w); alsa.snd_pcm_recover(pcm, w, 1) else written = written + w end
    alsa.snd_pcm_delay(pcm, dl)
    p(("blk %d wrote=%d delay=%d frames t=%.3f"):format(blk, written, tonumber(dl[0]), love.timer.getTime() - t0))
  end
  alsa.snd_pcm_drain(pcm)
  alsa.snd_pcm_close(pcm)
  p("done")
  t0 = love.timer.getTime()
end
function love.update() if t0 and love.timer.getTime() - t0 > 2 then love.event.quit() end end
function love.draw() love.graphics.print("alsa probe", 10, 10) end
