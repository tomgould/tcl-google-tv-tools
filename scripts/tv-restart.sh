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

adb connect "$TV" >/dev/null
[ "$(adb "${S[@]}" get-state 2>/dev/null)" = device ] || { echo "TV $TV not connected or not authorised" >&2; exit 1; }

adb "${S[@]}" shell cmd appops write-settings >/dev/null
sleep 12
echo "$(date -Is) restart via scripts/tv-restart.sh (appops write-settings, svc power reboot)" >> "$ROOT/logs/changes.log"
adb "${S[@]}" shell svc power reboot || true
echo "Restarting..."

sleep 10
for _ in $(seq 1 60); do
  adb connect "$TV" >/dev/null 2>&1 || true
  [ "$(adb "${S[@]}" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = 1 ] && break
  sleep 3
done
[ "$(adb "${S[@]}" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = 1 ] || { echo "TV didn't come back within about 3 minutes" >&2; exit 1; }

# Give Projectivy time to open HDMI 1 and the accessibility services time to bind
until [ "$(adb "${S[@]}" shell "cut -d. -f1 /proc/uptime" | tr -d '\r')" -ge 45 ]; do sleep 3; done
exec "$ROOT/scripts/tv-status.sh"
