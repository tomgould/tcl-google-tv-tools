#!/usr/bin/env bash
# Show what is on the TV screen as text: the top activity and every labelled UI node,
# marking the focused one with '>'. Optional: save a 40% screenshot to the given path.
# Usage: scripts/tv-screen.sh [screenshot.png]
#
# Warning: `uiautomator dump` registers a test accessibility service, and Android suspends
# other accessibility services (Projectivy's Home-button override) while it runs. Don't use
# the text dump while configuring an accessibility-based app; take a screenshot instead.
# Delete screenshots once done: they show whatever is on screen.
set -euo pipefail

TV="${TV:?set TV to the TV address, for example TV=192.168.1.50:5555}"
S=(-s "$TV")

adb "${S[@]}" shell dumpsys activity activities | grep -m1 topResumedActivity | grep -oE 'u0 [^ ]+' || true
adb "${S[@]}" shell uiautomator dump /sdcard/ui.xml >/dev/null 2>&1
adb "${S[@]}" shell cat /sdcard/ui.xml | python3 -I -c '
import sys, xml.etree.ElementTree as ET
root = ET.fromstring(sys.stdin.read())
for n in root.iter("node"):
    label = n.get("text") or n.get("content-desc") or ""
    if not label.strip():
        continue
    mark = ">" if n.get("focused") == "true" else " "
    state = " [on]" if n.get("checked") == "true" else ""
    print(mark, label.strip()[:70] + state, " ", n.get("bounds"))
'

if [ $# -ge 1 ]; then
  adb "${S[@]}" exec-out screencap -p > "$1.full.png"
  convert "$1.full.png" -resize 40% "$1" && rm -f "$1.full.png"
fi
