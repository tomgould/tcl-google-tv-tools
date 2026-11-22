#!/usr/bin/env bash
# Sunshine prep command: plug the virtual "TV screen" in when the TV connects (do), and
# unplug it when the session ends (undo). The desktop treats it like a monitor being
# connected and disconnected, so windows on it move back to the other screens afterwards.
# Usage: tv-screen-prep.sh do|undo
set -uo pipefail

# evdi's connector shows up as DVI-I; the "connected WxH+X+Y" form means it's switched on
on() { xrandr --query | grep -qE '^DVI-I-[0-9-]+ connected( primary)? [0-9]+x[0-9]+\+'; }

case "${1:-}" in
  do)
    systemctl --user start tv-screen.service || exit 1
    for i in $(seq 1 40); do
      on && exit 0
      # The desktop normally switches a new monitor on by itself; if not after 3 s, do it
      if [ "$i" = 12 ]; then
        out=$(xrandr --query | grep -oE '^DVI-I-[0-9-]+ connected' | cut -d' ' -f1 | head -1)
        [ -n "$out" ] && xrandr --output "$out" --auto
      fi
      sleep 0.25
    done
    echo "TV screen didn't come up within 10 seconds" >&2
    exit 1 ;;
  undo)
    systemctl --user stop tv-screen.service ;;
  *)
    echo "usage: $0 do|undo" >&2
    exit 2 ;;
esac
