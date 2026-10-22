# TCL Google TV tools

Scripts and notes for decluttering a TCL Google TV over ADB, without root. Tested on a TCL 65C6K (Android 14, MediaTek MT9689). Other TCL Google TVs probably behave the same, but they haven't been tested.

Everything here disables rather than uninstalls, so `pm enable` or a factory reset undoes it.

## What's here

| Path | What it does |
|---|---|
| `scripts/tv-batch.sh` | `apply`, `undo` or `status` for a batch file of packages. Refuses anything in the keep-list, skips packages that aren't installed, and logs every change to `logs/changes.log`. |
| `scripts/rearm-projectivy.sh` | Restores Projectivy Launcher's Home-button override if TCL's boot blocker stopped it (see below). |
| `scripts/tv-screen.sh` | Prints the current screen as text, with an optional screenshot. |
| `scripts/tv-status.sh` | Read-only health check. Confirms every batch is still disabled, nothing on the keep-list is disabled, the boot permissions and accessibility services are in place, and the settings are as expected. Run it after a TCL update. |
| `scripts/tv-restart.sh` | Restarts without losing recent changes (saves app-ops, waits for package settings, uses a normal shutdown), then runs the health check. |
| `scripts/tv-remote.py` | Pairs with the TV over the Android TV Remote v2 protocol, then sends keys, launches apps and reads status, without ADB. |
| `batches/` | The five batches used on the 65C6K, with a reason for each package. |
| `config/keep-list.txt` | Packages never to disable, with the reason for each. |
| `docs/second-screen.md` | Using the TV as a screen for a Linux PC with Sunshine and Moonlight, and the three fixes it needed. |

## Using it

Turn on Developer options (press OK on the build number seven times) and USB debugging, then:

```bash
export TV=192.168.1.50:5555            # your TV's address
adb connect "$TV"
scripts/tv-batch.sh status batches/batch-01.txt
scripts/tv-batch.sh apply  batches/batch-01.txt
scripts/tv-batch.sh undo   batches/batch-01.txt
```

For the remote script, install `androidtvremote2` (see `requirements.txt`), then:

```bash
export TV_HOST=192.168.1.50
python3 scripts/tv-remote.py pair      # type the 6-character code shown on the TV
python3 scripts/tv-remote.py status
python3 scripts/tv-remote.py key HOME
```

The pairing key is saved in `~/.config/tcl_tv/remote/`. Keep it private.

Read each batch file before applying it, and test the TV (inputs, voice, casting, your apps) between batches.

## Things worth knowing

- **TCL blocks third-party apps from starting at boot.** A system component called TclAppBoot refuses to start apps that lack a TCL-only app-op, `AUTO_START`, which defaults to `ignore`. That's why launchers and remappers stop working after a restart. Allow it per app:
  ```bash
  adb shell cmd appops set <package> AUTO_START allow
  adb shell cmd appops write-settings
  ```
- **If you use Projectivy and watch through an HDMI device**, set "Launch on boot" on that input's tile (long-press it). Otherwise, once Projectivy is allowed to start at boot, it can land on top of the last-used input after a full restart.
- **Save before you restart.** In Android 14, app-op changes are written to disk 30 minutes after they're made, and package changes after 10 seconds. `adb reboot` skips the normal shutdown, so recent changes can be lost. Use `adb shell cmd appops write-settings`, then `adb shell svc power reboot`.
- **Apps only mode disables the Google Assistant**, so the voice button stops working.
- **Some debloat lists break things:**
  - `com.google.android.tts` is the voice recogniser.
  - Disabling `setupwraith` reportedly breaks volume on some Google TVs.
  - Disabling the stock launcher on Android 14 reportedly leaves a black screen.
  - `com.android.sdksandbox` reportedly causes a boot loop.

  These are in the keep-list.
- **Reading the screen with `uiautomator dump`** suspends other accessibility services while it runs, including a launcher's Home override.
- **The branded remote buttons use TCL keycodes.** On this remote, the Disney+ button sends HID usage `0x0C004D`, which becomes keycode 4141. Its handler can't be changed without root, but an accessibility remapper such as Key Mapper can catch it. Key Mapper only learns the key from a real press, not from `adb shell input`. One intent switches straight to HDMI 1:
  ```bash
  adb shell am start -a android.intent.action.VIEW \
    -d 'content://android.media.tv/passthrough/com.tcl.tvinput%2F.TvPassThroughService%2FHW15'
  ```
  The input ID (`HW15`) comes from `adb shell dumpsys tv_input` and may differ on other models.

## Not covered

TCL software updates may re-enable packages or reset `AUTO_START`. That hasn't been tested yet.

## Licence

MIT. See [LICENSE](LICENSE).
