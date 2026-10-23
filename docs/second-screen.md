# The TV as a screen for a Linux PC

Sunshine on the PC and Moonlight on the TV put the PC's screen on the TV, with the sound from the TV. Tested with Sunshine 2026.914 on Ubuntu 22.04 (GNOME, X11, NVIDIA RTX 4080 laptop) and Moonlight 12.2 on the TCL 65C6K.

## Setup

```bash
sudo apt install ./sunshine_<version>+ubuntu22.04_amd64.deb
systemctl --user enable --now app-dev.lizardbyte.app.Sunshine
# If ufw is on, let only the TV in (the settings page on 47990 stays local):
sudo ufw allow from <tv-ip> to any port 47984,47989,48010 proto tcp
sudo ufw allow from <tv-ip> to any port 47998:48010 proto udp
```

Settings live in `~/.config/sunshine/sunshine.conf`. These three fixed the problems below:

```
capture = x11
output_name = eDP-1-1
origin_web_ui_allowed = pc
```

## Using it

On the TV, open Moonlight, pick the PC, then Desktop. One press of Back on the TV remote ends the session without a prompt, and Sunshine puts the PC's sound back in the same second.

## Problems and fixes

- **Sunshine hangs at "Detecting displays"** after `Couldn't release NvFBC context`. NvFBC needs a patched NVIDIA driver on consumer cards. `capture = x11` skips it.
- **The wrong screen, or every screen at once.** On X11 a numeric `output_name` is read two ways: the capture code counts every output the X server reports, connected or not, while the session matches output names. Use the output's name from `xrandr`, for example `eDP-1-1` for a laptop panel or `HDMI-0` for a dummy plug.
- **Pairing from the command line.** This version needs the ID of the waiting request as well as the PIN:
  ```bash
  curl -sk -u "$SUNSHINE_LOGIN" https://localhost:47990/api/pin
  curl -sk -u "$SUNSHINE_LOGIN" -X POST -H 'Content-Type: application/json' \
    -d '{"pairing_id":"<id>","pin":"<pin>","name":"TV"}' https://localhost:47990/api/pin
  ```
  It returns `{"status":false}` if the PIN dialog on the TV has been closed, because that cancels the request.
- **Screenshots.** While a session runs, a screenshot of the TV (for example `adb exec-out screencap`) shows the PC's screen.

## Not covered

An extra screen, as opposed to a copy of an existing one, needs a display Sunshine can stream that the PC isn't showing. A dummy HDMI plug is the simplest way on X11. That hasn't been tested here yet, and neither has the delay.

Faking the display in software is risky on NVIDIA if your monitors come through a dock. The driver's `ConnectedMonitor` option replaces its own detection of every connected display, so each docked monitor would have to be listed by hand.
