function love.conf(t)
  t.identity = "podtube"
  t.version = "11.4"
  t.window.title = "PodTube"
  t.window.width = 480
  t.window.height = 272
  t.window.fullscreen = true
  t.window.fullscreentype = "desktop"
  t.window.vsync = 1
  t.window.resizable = false
  t.modules.physics = false
  t.modules.audio = false   -- OpenAL would keep the sound device busy; the player writes to ALSA itself
  t.modules.sound = false
  t.modules.touch = false
  t.modules.video = false
end
