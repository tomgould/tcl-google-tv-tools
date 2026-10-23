#!/usr/bin/env bash
# Read-only health check: confirms the TV still matches the expected setup.
# Run it after a TCL software update, a factory reset, or whenever something seems off.
# Usage: scripts/tv-status.sh   (exits 1 if any check fails)
set -uo pipefail

TV="${TV:?set TV to the TV address, for example TV=192.168.1.50:5555}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
S=(-s "$TV")
fails=0

ok()  { echo "ok    $*"; }
bad() { echo "FAIL  $*"; fails=$((fails + 1)); }
check() { [ "$3" = "$2" ] && ok "$1 = $3" || bad "$1 = $3 (expected $2)"; }
tv() { adb "${S[@]}" shell "$@" 2>/dev/null | tr -d '\r'; }
entries() { grep -vE '^\s*(#|$)' "$1" | awk '{print $1}'; }

adb connect "$TV" >/dev/null
[ "$(adb "${S[@]}" get-state 2>/dev/null)" = device ] || { echo "TV $TV not connected or not authorised" >&2; exit 1; }

# Packages: every batch entry still disabled, nothing on the keep-list disabled
installed=$(tv pm list packages | sed 's/^package://')
disabled=$(tv pm list packages -d --user 0 | sed 's/^package://')
for b in "$ROOT"/batches/batch-*.txt; do
  n=0; off=0
  for p in $(entries "$b"); do
    grep -qxF "$p" <<<"$installed" || continue
    n=$((n + 1))
    if grep -qxF "$p" <<<"$disabled"; then off=$((off + 1)); else bad "$(basename "$b"): $p is enabled again"; fi
  done
  [ "$off" = "$n" ] && ok "$(basename "$b"): $off/$n disabled"
done
for p in $(entries "$ROOT/config/keep-list.txt"); do
  grep -qxF "$p" <<<"$disabled" && bad "keep-list package disabled: $p"
done

# TCL's boot blocker: apps that must start at boot need the AUTO_START app-op
for p in com.spocky.projengmenu io.github.sds100.keymapper; do
  check "AUTO_START $p" "AUTO_START: allow" "$(tv cmd appops get "$p" AUTO_START | cut -d';' -f1)"
done

# Projectivy's Home override and Key Mapper's Disney+ remap run as accessibility services
a11y=$(tv dumpsys accessibility)
for label in "Projectivy Launcher" "Key Mapper"; do
  grep -q "label=$label" <<<"$a11y" && ok "accessibility service bound: $label" || bad "accessibility service not bound: $label (run scripts/rearm-projectivy.sh)"
done
check "accessibility_enabled" 1 "$(tv settings get secure accessibility_enabled)"

# Settings this setup changes (edit to match yours)
check "shut-off timer when watching (attentive_timeout)" -1 "$(tv settings get secure attentive_timeout)"
for k in window_animation_scale transition_animation_scale animator_duration_scale; do
  check "$k" 0.5 "$(tv settings get global "$k")"
done
check "CEC: Fire Stick wakes the TV" "tv_wake_on_one_touch_play = 1" "$(tv cmd hdmi_control cec_setting get tv_wake_on_one_touch_play)"
check "CEC: TV off turns the Fire Stick off" "tv_send_standby_on_sleep = 1" "$(tv cmd hdmi_control cec_setting get tv_send_standby_on_sleep)"
check "screensaver" "com.google.android.apps.tv.dreamx/.service.Backdrop" "$(tv settings get secure screensaver_components)"

# For information only
echo "info  uptime $(tv "cut -d' ' -f1 /proc/uptime")s, boot reason $(tv getprop sys.boot.reason), $(tv grep MemAvailable /proc/meminfo | tr -s ' ')"
echo "info  on screen: $(tv dumpsys activity activities | grep -m1 topResumedActivity | grep -oE '[a-z0-9_.]+/[A-Za-z0-9_.]+' | head -1)"
cec=$(tv dumpsys hdmi_control | sed -n '/mDeviceInfos:/,/CecSwitches/p' | grep -v 'logical_address: 0x00 ' | grep -oE 'display_name: .* power_status|physical_address: 0x[0-9a-f]+' | sed -E 's/display_name: (.*) power_status/\1/; s/physical_address: 0x([0-9a-f])000/on HDMI \1;/' | paste -sd' ' - | sed 's/;$//')
echo "info  CEC devices: ${cec:-none (is CEC switched on in the HDMI device settings?)}"

[ "$fails" -eq 0 ] && echo "All checks passed." || { echo "$fails check(s) failed."; exit 1; }
