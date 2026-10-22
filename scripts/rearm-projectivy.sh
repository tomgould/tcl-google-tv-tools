#!/usr/bin/env bash
# Re-arm Projectivy's Home-button override after a full boot (power cut, unplugging, update).
# TCL's TclAppBoot refuses to start Projectivy's accessibility service at boot unless Projectivy
# has TCL's AUTO_START app-op or is already running. First try silently: allow AUTO_START, save
# it to disk, re-apply the accessibility setting. Only if that fails, open Projectivy on screen.
# Normal remote on/off is a suspend, not a boot, and doesn't need this.
# Usage: scripts/rearm-projectivy.sh
set -euo pipefail

TV="${TV:?set TV to the TV address, for example TV=192.168.1.50:5555}"
S=(-s "$TV")
SVC=com.spocky.projengmenu/com.spocky.projengmenu.services.ProjectivyAccessibilityService

bound() { adb "${S[@]}" shell dumpsys accessibility | grep -q 'Bound services:{Service\[label=Projectivy'; }

adb connect "$TV" >/dev/null
[ "$(adb "${S[@]}" get-state 2>/dev/null)" = device ] || { echo "TV $TV not connected or not authorised" >&2; exit 1; }

if bound; then
  echo "Projectivy override already active"
  exit 0
fi

reapply() {
  adb "${S[@]}" shell settings delete secure enabled_accessibility_services >/dev/null
  sleep 1
  adb "${S[@]}" shell settings put secure enabled_accessibility_services "$SVC"
  adb "${S[@]}" shell settings put secure accessibility_enabled 1
  sleep 3
}

adb "${S[@]}" shell cmd appops set com.spocky.projengmenu AUTO_START allow
adb "${S[@]}" shell cmd appops write-settings >/dev/null
reapply
if bound; then
  echo "Projectivy override re-armed (silently, via AUTO_START)"
  exit 0
fi

adb "${S[@]}" shell am start -n com.spocky.projengmenu/.ui.home.MainActivity >/dev/null
sleep 3
reapply

if bound; then
  echo "Projectivy override re-armed (opened Projectivy on screen)"
else
  echo "Projectivy accessibility service still not bound; check 'adb logcat | grep TclAppBoot'" >&2
  exit 1
fi
