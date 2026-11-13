-- Shared definitions between the main thread and the playback threads.
local ffi = require("ffi")

-- state block in a ByteData: the audio thread writes position/state, the main thread writes commands
pcall(ffi.cdef, [[
typedef struct {
  volatile int32_t seq;       /* bumped on every update */
  volatile int32_t frames;    /* audio frames written to ALSA since the start */
  volatile int32_t delay;     /* frames still queued in the device */
  volatile int32_t state;     /* 0 starting, 1 playing, 2 paused, 3 end of stream, 4 error */
  volatile int32_t cmd;       /* 0 run, 1 pause, 2 stop */
  volatile int32_t rate;
  volatile int32_t xruns;
  volatile int32_t err;
} pt_audio_state;
]])

local S = {
  STATE_START = 0, STATE_PLAY = 1, STATE_PAUSED = 2, STATE_EOF = 3, STATE_ERROR = 4,
  CMD_RUN = 0, CMD_PAUSE = 1, CMD_STOP = 2,
}
return S
