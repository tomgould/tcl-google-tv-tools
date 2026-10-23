# The TV as a screen for a Linux PC

Sunshine on the PC and Moonlight on the TV put a PC screen on the TV, with the sound from the TV. There are two ways to use it: stream one of the PC's existing screens, or give the PC an extra 4K screen that only exists while the TV is connected. Tested with Sunshine 2026.914 on Ubuntu 22.04 (GNOME on X11, NVIDIA RTX 4080 laptop, kernel 6.8) and Moonlight 12.2 on the TCL 65C6K.

## Sunshine

```bash
sudo apt install ./sunshine_<version>+ubuntu22.04_amd64.deb
systemctl --user enable --now app-dev.lizardbyte.app.Sunshine
# If ufw is on, let only the TV in (the settings page on 47990 stays local):
sudo ufw allow from <tv-ip> to any port 47984,47989,48010 proto tcp
sudo ufw allow from <tv-ip> to any port 47998:48010 proto udp
```

Settings live in `~/.config/sunshine/sunshine.conf`. To stream an existing screen:

```
capture = x11
output_name = eDP-1-1
origin_web_ui_allowed = pc
```

On the TV, open Moonlight, pick the PC, then Desktop. One press of Back on the TV remote ends the session. In Moonlight's settings, set the video resolution to match the TV: it may default to 720p.

## An extra screen, in software

This uses evdi, the virtual display driver behind DisplayLink docks. `laptop/tv-screen` plugs a virtual monitor into it, described by a hand-made EDID, and Sunshine plugs it in when the TV connects and unplugs it afterwards. The desktop treats it like a monitor being connected, so windows can be dragged onto it.

1. Install the driver and tell X11 not to accelerate it (DisplayLink's advice for NVIDIA), then restart:
   ```bash
   sudo apt install evdi-dkms libevdi0 libevdi0-dev
   printf 'Section "OutputClass"\n    Identifier "evdi"\n    MatchDriver "evdi"\n    Driver "modesetting"\n    Option "AccelMethod" "none"\nEndSection\n' | sudo tee /etc/X11/xorg.conf.d/20-evdi.conf
   echo 'options evdi initial_device_count=1' | sudo tee /etc/modprobe.d/evdi.conf
   echo evdi | sudo tee /etc/modules-load.d/evdi.conf
   ```
   Ubuntu 22.04's package has patches for kernel 6.8 and for running without a DisplayLink device. After the restart, `xrandr` shows a new, disconnected `DVI-I-…` output.
2. Build the helper and the EDID (3840×2160 at 60 Hz, with 1920×1080 as a second mode; add `1080p` for a 1080p-only one). The unit files expect this repo at `~/tcl-google-tv-tools`:
   ```bash
   cd ~/tcl-google-tv-tools
   gcc -O2 -Wall -o laptop/tv-screen laptop/tv-screen.c -levdi
   python3 -I laptop/make-edid.py laptop/tv-screen-4k.edid
   systemctl --user link "$PWD/laptop/tv-screen.service"
   systemctl --user enable --now "$PWD/laptop/tv-screen-follow.service"
   ```
3. Save a desktop layout for "the usual screens plus the TV screen", with all other screens unplugged from Sunshine first. It puts the TV screen left of the primary screen. Click Keep Changes when GNOME asks:
   ```bash
   python3 -I laptop/tv-screen-layout.py
   ```
4. Point Sunshine at it. Use the output name `xrandr` shows while the screen is plugged in (`systemctl --user start tv-screen.service`, then stop it):
   ```
   output_name = DVI-I-2-1
   global_prep_cmd = [{"do":"/home/<you>/tcl-google-tv-tools/laptop/tv-screen-prep.sh do","undo":"/home/<you>/tcl-google-tv-tools/laptop/tv-screen-prep.sh undo","elevated":false}]
   ```
5. `tv-screen-follow.service` closes Sunshine's Desktop app whenever the TV disconnects, so the screen unplugs. It reads Sunshine's web login from `~/.config/sunshine-webui-login.txt`, with `Username: …` and `Password: …` lines (`chmod 600` it).

To undo it all: stop and disable both services, delete the three files from step 1, `sudo apt remove evdi-dkms libevdi0 libevdi0-dev`, and restart.

## Problems and fixes

- **Sunshine hangs at "Detecting displays"** after `Couldn't release NvFBC context`. NvFBC needs a patched NVIDIA driver on consumer cards. `capture = x11` skips it.
- **The wrong screen, or every screen at once.** On X11 a numeric `output_name` is read two ways: the capture code counts every output the X server reports, connected or not, while the session matches output names. Use the output's name from `xrandr`.
- **Pairing from the command line.** This version needs the ID of the waiting request as well as the PIN:
  ```bash
  curl -sk -u "$SUNSHINE_LOGIN" https://localhost:47990/api/pin
  curl -sk -u "$SUNSHINE_LOGIN" -X POST -H 'Content-Type: application/json' \
    -d '{"pairing_id":"<id>","pin":"<pin>","name":"TV"}' https://localhost:47990/api/pin
  ```
  It returns `{"status":false}` if the PIN dialog on the TV has been closed, because that cancels the request.
- **Every screen goes black when the virtual screen appears.** evdi doesn't finish a display update until a client has collected the frame. A helper that only plugs the screen in leaves the X server waiting 10 seconds per update (`flip_done timed out` in the kernel log). `tv-screen` grabs every frame and throws it away, which costs about 8% of one CPU core at 1080p and about 23% at 4K while a session runs.
- **Portrait monitors turn landscape.** GNOME lays out a new set of monitors with its defaults, and only saves a layout once "Keep Changes" is clicked. `tv-screen-layout.py` applies the layout temporarily first, then asks GNOME to save it.
- **The screen stays plugged in after Back.** Sunshine keeps the Desktop app running after a disconnect, so the client can resume, and only runs the prep command's undo when the app is closed. `tv-screen-follow.sh` closes it on every disconnect through `POST /api/apps/close`.
- **"Couldn't get info for requested display" at the start of a session.** Sunshine tests its encoders before running the prep command, and falls back to the whole desktop for that test. The stream itself starts after the prep command and finds the screen.
- **Screenshots.** While a session runs, a screenshot of the TV (for example `adb exec-out screencap`) shows the PC's screen.

## Not covered

The delay hasn't been measured, and what the TV remote's arrows do in a session hasn't been tested. `tv-screen-follow.sh`'s close call was tested by hand; its first automatic run on a real disconnect hasn't happened yet. Moonlight crashed once, seven minutes into a 720p session, with a decoder error on the TV (`ErrorWhileStreamingFormat: 100`); the cause isn't known. Wayland hasn't been tried.
