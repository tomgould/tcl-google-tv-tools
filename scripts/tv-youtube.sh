#!/usr/bin/env bash
# Send a YouTube link from this PC to SmartTube on the TV (the ad-free player).
# Usage: scripts/tv-youtube.sh [--dry-run] <youtube-url>
# It wakes the TV if it's asleep, then opens the link in SmartTube. The stock YouTube apps are
# disabled (batch-07), so this replaces casting from YouTube, which can't find SmartTube.
set -euo pipefail

TV="${TV:?set TV to the TV address, for example TV=192.168.1.50:5555}"
PKG=app.smarttube.fdroid
ACT=com.liskovsoft.smartyoutubetv2.tv.ui.main.SplashActivity

dry=0
if [ "${1:-}" = "--dry-run" ]; then dry=1; shift; fi
url="${1:?usage: tv-youtube.sh [--dry-run] <youtube-url>}"

# Only plain YouTube links, with characters that are safe inside the TV's shell quoting.
if ! [[ "$url" =~ ^https://(www\.|m\.|music\.)?(youtube\.com|youtu\.be)/[A-Za-z0-9_./?=\&%+-]*$ ]]; then
  echo "not a youtube.com or youtu.be link (or it has unusual characters): $url" >&2
  exit 1
fi

cmd="am start -a android.intent.action.VIEW -n $PKG/$ACT -d '$url'"
if [ "$dry" = 1 ]; then echo "adb -s $TV shell $cmd"; exit 0; fi

adb connect "$TV" >/dev/null
[ "$(adb -s "$TV" get-state 2>/dev/null)" = device ] || { echo "TV $TV not connected or not authorised" >&2; exit 1; }

# Wake the TV if the screen is off (no key press is sent when it's already on).
if adb -s "$TV" shell dumpsys power | grep -q 'mWakefulness=Asleep\|mWakefulness=Dozing'; then
  adb -s "$TV" shell input keyevent KEYCODE_WAKEUP
  sleep 3
fi

adb -s "$TV" shell "$cmd" | tr -d '\r'
