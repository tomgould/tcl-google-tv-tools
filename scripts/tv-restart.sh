#!/usr/bin/env bash
# Restart the TV without losing recent changes, then run the health check.
# Android writes package changes about 10 s after they're made and app-op changes up to
# 30 min later, and `adb reboot` skips the normal shutdown that would save them. So: save
# app-ops now, wait for package settings, then restart through the normal shutdown.
# Usage: scripts/tv-restart.sh
set -euo pipefail

TV="${TV:?set TV to the TV address, for example TV=192.168.1.50:5555}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
S=(-s "$TV")
up() { adb "${S[@]}" shell "cut -d. -f1 /proc/uptime" 2>/dev/null | tr -d '\r'; }
bootid() { adb "${S[@]}" shell cat /proc/sys/kernel/random/boot_id 2>/dev/null | tr -d '\r'; }

adb connect "$TV" >/dev/null || true
[ "$(adb "${S[@]}" get-state 2>/dev/null)" = device ] || { echo "TV $TV not connected or not authorised" >&2; exit 1; }

adb "${S[@]}" shell cmd appops write-settings >/dev/null
sleep 15
old=$(bootid) || true
[ -n "$old" ] || { echo "Couldn't read the TV's boot ID" >&2; exit 1; }
mkdir -p "$ROOT/logs"
echo "$(date -Is) restart via scripts/tv-restart.sh (appops write-settings, svc power reboot)" >> "$ROOT/logs/changes.log"
adb "${S[@]}" shell svc power reboot || true
echo "Restarting..."

# The old boot can answer for a while as it shuts down, so wait for a new boot ID. 45 s
# after boot, Projectivy has opened HDMI 1 and the accessibility services have bound.
for _ in $(seq 1 100); do
  sleep 3
  adb connect "$TV" >/dev/null 2>&1 || true
  id=$(bootid) || true
  [ -n "$id" ] && [ "$id" != "$old" ] && [ "$(up)" -ge 45 ] 2>/dev/null &&
    [ "$(adb "${S[@]}" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = 1 ] &&
    exec "$ROOT/scripts/tv-status.sh"
done
echo "No new boot seen within 5 minutes. Check the TV, then run scripts/tv-status.sh." >&2
exit 1
