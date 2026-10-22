#!/usr/bin/env bash
# Disable, re-enable or check a batch of TV packages over ADB, logging every change.
# Usage: scripts/tv-batch.sh apply|undo|status <batch-file>
# Uses disable-user (never uninstall), so `undo` or a factory reset restores everything.
set -euo pipefail

TV="${TV:?set TV to the TV address, for example TV=192.168.1.50:5555}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KEEP="$ROOT/config/keep-list.txt"
LOG="$ROOT/logs/changes.log"

action="${1:?usage: tv-batch.sh apply|undo|status <batch-file>}"
batch="${2:?usage: tv-batch.sh apply|undo|status <batch-file>}"
[ -f "$batch" ] || { echo "no such batch file: $batch" >&2; exit 1; }

entries() { grep -vE '^\s*(#|$)' "$1" | awk '{print $1}'; }

adb connect "$TV" >/dev/null
[ "$(adb -s "$TV" get-state 2>/dev/null)" = device ] || { echo "TV $TV not connected or not authorised" >&2; exit 1; }

keep=$(entries "$KEEP")
installed=$(adb -s "$TV" shell pm list packages | sed 's/^package://' | tr -d '\r')
disabled=$(adb -s "$TV" shell pm list packages -d | sed 's/^package://' | tr -d '\r')
mkdir -p "$(dirname "$LOG")"

for p in $(entries "$batch"); do
  if ! grep -qxF "$p" <<<"$installed"; then
    echo "absent   $p"; continue
  fi
  case "$action" in
    apply)
      if grep -qxF "$p" <<<"$keep"; then echo "REFUSED  $p (on keep-list)"; continue; fi
      out=$(adb -s "$TV" shell pm disable-user --user 0 "$p" | tr -d '\r') ;;
    undo)
      out=$(adb -s "$TV" shell pm enable --user 0 "$p" | tr -d '\r') ;;
    status)
      grep -qxF "$p" <<<"$disabled" && echo "disabled $p" || echo "enabled  $p"
      continue ;;
    *) echo "unknown action: $action" >&2; exit 1 ;;
  esac
  echo "$action $p: $out"
  echo "$(date -Is) $action $(basename "$batch") $p: $out" >> "$LOG"
done
