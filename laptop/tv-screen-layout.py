#!/usr/bin/env python3
"""Save a GNOME display layout for "the usual screens plus the TV screen".

Without one, GNOME lays out a new set of monitors with its defaults (landscape, side by
side) when the TV screen appears. This keeps the current layout, adds the TV screen to the
left of the primary monitor, and applies it persistently, so GNOME reuses it every time
the TV screen is plugged in. GNOME then asks to keep the change: click "Keep Changes".
The layout is applied temporarily first, so if nobody clicks, GNOME falls back to that
rather than to its defaults.
Run it with the TV screen unplugged. Usage: python3 -I laptop/tv-screen-layout.py
"""
import os
import subprocess
import sys
import time

from gi.repository import Gio, GLib

TV = "DVI-I-"  # evdi's connector name prefix

bus = Gio.bus_get_sync(Gio.BusType.SESSION)


def call(method, args=None, timeout=-1):
    return bus.call_sync("org.gnome.Mutter.DisplayConfig", "/org/gnome/Mutter/DisplayConfig",
                         "org.gnome.Mutter.DisplayConfig", method, args, None,
                         Gio.DBusCallFlags.NONE, timeout, None).unpack()


def state():
    serial, monitors, logical, _ = call("GetCurrentState")
    current = {}
    for (connector, *_), modes, _props in monitors:
        for mode_id, _w, _h, _r, _s, _ss, props in modes:
            if props.get("is-current"):
                current[connector] = mode_id
    return serial, monitors, logical, current


_, monitors, logical, current = state()
if any(m[0][0].startswith(TV) for m in monitors):
    sys.exit("Unplug the TV screen first: systemctl --user stop tv-screen.service")

# The layout as it is now, to keep
keep = [(x, y, scale, transform, primary, [(m[0], current[m[0]], {}) for m in mons])
        for x, y, scale, transform, primary, mons, _props in logical]
primary = next(l for l in logical if l[4])
px, py = primary[0], primary[1]

subprocess.run(["systemctl", "--user", "start", "tv-screen.service"], check=True)
for _ in range(40):
    serial, monitors, _, _ = state()
    tv = next((m for m in monitors if m[0][0].startswith(TV)), None)
    if tv:
        break
    time.sleep(0.25)
else:
    sys.exit("The TV screen didn't appear")

tv_mode, tv_width = next((mid, w) for mid, w, *_rest, props in tv[1] if props.get("is-preferred"))
# Everything moves right by the TV screen's width; the TV screen sits level with the primary
layout = [(x + tv_width, y, s, t, p, mons) for x, y, s, t, p, mons in keep]
layout.append((px, py, 1.0, 0, False, [(tv[0][0], tv_mode, {})]))
saved = os.path.expanduser("~/.config/monitors.xml")
before = os.path.getmtime(saved) if os.path.exists(saved) else 0
time.sleep(2)  # let GNOME finish setting up the new monitor first
for method in (1, 2):  # temporary, then persistent
    serial = state()[0]
    call("ApplyMonitorsConfig",
         GLib.Variant("(uua(iiduba(ssa{sv}))a{sv})", (serial, method, layout, {})), 20000)
    time.sleep(2)
print(f"Applied: {tv[0][0]} {tv_mode}, left of the primary monitor."
      " Click \"Keep Changes\" on the screen.", flush=True)
# GNOME only writes the layout to disk once "Keep Changes" is clicked
for _ in range(60):
    if os.path.exists(saved) and os.path.getmtime(saved) > before:
        sys.exit(print("Saved.") or 0)
    time.sleep(0.5)
sys.exit("Not saved: \"Keep Changes\" wasn't clicked within 30 seconds")
