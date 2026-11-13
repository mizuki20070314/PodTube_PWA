-- The ffmpeg command lines of a playback and of a download (pure functions: tools/avsync/avsync_test.py builds the very same
-- lines through lupa to measure the A/V sync of the real pipeline).
--
-- Contract with the engine: the picture pipe (fd 3) holds frames at exactly `fps`, frame i being the picture of media time
-- start + i/fps; the audio pipe (fd 4) holds samples at exactly `rate`, sample n being the sound of media time start + n/rate
-- (stretched by `speed`).  "Media time" is the time stamp inside the stream, so the two stay in step whatever the start time of
-- each track is and wherever the first usable picture happens to be.  What makes that true:
--   * -seek_timestamp 1 on both inputs: ffmpeg normally shifts every input by its own start time, which moves a video that starts
--     a frame (or a few hundred ms) after its audio ahead of the sound for good.  With it both inputs keep the time stamps of the
--     stream, and "-ss" is an absolute media time on both;
--   * the HLS demuxer, after a seek, hands over video from the next key frame on - the video input therefore starts a few
--     seconds *before* the wanted position (-ss), is shifted back by the same amount (-itsoffset) so that its time line starts at
--     the wanted position again, and the pictures of that pre-roll are cut off after decoding (trim).  Without it the picture
--     would start up to a whole GOP late, and ffmpeg would call that late first picture frame 0.  (A trim/setpts pair made by hand
--     instead of -itsoffset leaves the end-of-stream time of the input unshifted, and fps then pads the end by the pre-roll.)
--   * fps start_time=0 / aresample first_pts=0 fill a late start with the first picture / with silence, and aresample async=1 keeps
--     filling and trimming when the audio time stamps jump (the picture is made constant-rate by fps in the same way);
--   * a first time stamp beyond BASE_LIMIT is a time base (MPEG-TS from some packagers starts at 10 s) and not a real offset: that
--     track is shifted to zero by itself instead of being padded with seconds of silence.
local A = {}

local FFMPEG = "/usr/bin/ffmpeg"
A.FFMPEG = FFMPEG
A.PREROLL = 6.5          -- seconds: more than a segment (up to 6 s) - after a seek the HLS demuxer hands over video from the next key frame on
A.BASE_LIMIT = 3.0       -- seconds

local function atempo_chain(speed)
  if math.abs(speed - 1) < 0.01 then return nil end
  local parts, s = {}, speed
  while s > 2.0 do parts[#parts + 1] = "atempo=2.0"; s = s / 2.0 end
  while s < 0.5 do parts[#parts + 1] = "atempo=0.5"; s = s / 0.5 end
  parts[#parts + 1] = string.format("atempo=%.4f", s)
  return table.concat(parts, ",")
end
A.atempo_chain = atempo_chain

local function secs(t) return (string.format("%.3f", t):gsub("0+$", ""):gsub("%.$", "")) end

local function rebase_expr(name)
  return string.format("%s='PTS-if(gt(STARTPTS*TB,%g),STARTPTS,0)'", name, A.BASE_LIMIT)
end

--- spec = { vurl=, aurl= | single=, start=seconds, fps=, fps_arg=, speed=, rate=, threads= }  ->  argv
function A.build(spec)
  local argv = { FFMPEG, "-hide_banner", "-loglevel", "warning", "-nostdin", "-nostats" }
  local function add(...) for _, a in ipairs { ... } do argv[#argv + 1] = a end end
  local start = spec.start or 0
  local seeking = start > 0.5
  local vf, af = {}, {}
  local audio_map
  if spec.single then
    -- a downloaded file: one input with both streams, one time line (ffmpeg shifts both by the same start time)
    if seeking then add("-ss", secs(start)) end
    add("-c:v", "h264", "-threads", tostring(spec.threads or 3), "-i", spec.single)
    audio_map = "0:a:0"
  else
    local pre = seeking and math.min(start, A.PREROLL) or 0
    add("-seek_timestamp", "1", "-thread_queue_size", "64")
    if start - pre > 0.01 then add("-ss", secs(start - pre)) end
    if pre > 0 then add("-itsoffset", "-" .. secs(pre)) end   -- the picture time line starts at the wanted position again
    add("-c:v", "h264", "-threads", tostring(spec.threads or 3), "-i", spec.vurl)
    add("-seek_timestamp", "1", "-thread_queue_size", "64")
    if seeking then add("-ss", secs(start)) end
    add("-i", spec.aurl)
    audio_map = "1:a:0"
    if pre > 0 then
      vf[#vf + 1] = "trim=start=0"                            -- the pictures of the pre-roll (before the wanted position) go away
    else
      vf[#vf + 1] = rebase_expr("setpts")
      af[#af + 1] = rebase_expr("asetpts")
    end
  end
  if spec.probe then vf[#vf + 1] = "showinfo" end          -- (tools only) print the time stamp of every picture, before and after fps
  if spec.fps then vf[#vf + 1] = string.format("fps=fps=%s:start_time=0", spec.fps_arg or tostring(spec.fps)) end
  if spec.probe then vf[#vf + 1] = "showinfo" end
  add("-map", "0:v:0", "-an", "-sn", "-pix_fmt", "yuv420p")
  if #vf > 0 then add("-vf", table.concat(vf, ",")) end
  if spec.fps then add("-r", spec.fps_arg or tostring(spec.fps)) end
  add("-f", "rawvideo", "pipe:3")
  add("-map", audio_map, "-vn", "-sn", "-ac", "2", "-ar", tostring(spec.rate or 44100))
  if spec.probe then af[#af + 1] = "ashowinfo" end
  af[#af + 1] = "aresample=async=1:first_pts=0"
  local at = atempo_chain(spec.speed or 1)
  if at then af[#af + 1] = at end
  if spec.probe then af[#af + 1] = "ashowinfo" end
  add("-af", table.concat(af, ","))
  add("-f", "s16le", "pipe:4")
  return argv
end

--- the two HLS tracks copied into one .mp4 (no re-encoding).  Both inputs keep the time stamps of the stream and one common
--- shift (avoid_negative_ts) goes in the file, so the offset between the tracks is not lost the way ffmpeg's per-input shift loses it.
--- progress: also write -progress lines to descriptor 3.
function A.download_argv(vurl, aurl, out, progress)
  local argv = { FFMPEG, "-hide_banner", "-loglevel", "warning", "-nostdin", "-nostats" }
  local function add(...) for _, a in ipairs { ... } do argv[#argv + 1] = a end end
  if progress then add("-progress", "pipe:3") end
  add("-seek_timestamp", "1", "-i", vurl, "-seek_timestamp", "1", "-i", aurl, "-map", "0:v:0", "-map", "1:a:0", "-c", "copy",
    "-bsf:a", "aac_adtstoasc", "-avoid_negative_ts", "make_zero", "-movflags", "+faststart", "-f", "mp4", "-y", out)
  return argv
end

return A
