#!/bin/sh
# PodTube for M17 - launcher (MinUI: Ports > PodTube)
APP=/mnt/sdcard/Ports/PodTube
HOME=$APP
XDG_DATA_HOME=$APP
XDG_CONFIG_HOME=$APP/.config
export HOME XDG_DATA_HOME XDG_CONFIG_HOME
export LD_LIBRARY_PATH=$APP/libs
export LD_PRELOAD="$APP/libs/libstat_compat.so.1 $APP/libs/libsdl_compat.so.1"

mkdir -p "$APP/.config" "$APP/logs"
LOG="$APP/logs/podtube.log"

# MinUI pins everything to CPU3 (taskset 8); decoding needs all four cores.
taskset -p 0xf $$ >/dev/null 2>&1

# Network: this machine has no NIC.  When the PC's tunnel (m17-net.sh) is up its proxy listens on 127.0.0.1:8899.
if netstat -ltn 2>/dev/null | grep -q '127.0.0.1:8899'; then
    [ -f /userdata/bin/net-env.sh ] && . /userdata/bin/net-env.sh
    echo "net: proxy at 127.0.0.1:8899" > "$LOG"
else
    echo "net: no proxy (tunnel is down)" > "$LOG"
fi

# MinUI leaves this codec's Master control lopsided (only the left channel); copy the level to both channels.
vol=$(amixer -c 0 sget Master 2>/dev/null | sed -n 's/.*Front Left: Playback \([0-9]*\).*/\1/p')
[ -n "$vol" ] && amixer -c 0 sset Master "$vol" >/dev/null 2>&1

cd "$APP"
./bin/love.armhf ./app >> "$LOG" 2>&1
killall ffmpeg 2>/dev/null
exit 0
