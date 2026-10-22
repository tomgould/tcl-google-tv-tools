#!/usr/bin/env python3
# Control the TV over the Android TV Remote v2 protocol (ports 6466/6467), the same one
# the Fairphone's built-in remote uses. No ADB needed once paired.
# Uses androidtvremote2 0.3.2 from the project venv (.venv). The pairing key lives in
# ~/.config/tcl_tv/remote/ and must never be printed.
#
# Usage (run with .venv/bin/python):
#   scripts/tv-remote.py pair [--code-file PATH]   TV shows a 6-character code; type it,
#                                                 or write it to PATH (waits 3 minutes)
#   scripts/tv-remote.py status                    power, current app, volume
#   scripts/tv-remote.py key KEY [KEY...]          e.g. key DPAD_DOWN DPAD_CENTER, or a number
#   scripts/tv-remote.py app LINK                  launch by deep link, e.g. https://www.netflix.com/title.*
import argparse
import asyncio
import os
import sys
from pathlib import Path

from androidtvremote2 import AndroidTVRemote

TV = os.environ.get("TV_HOST") or sys.exit("set TV_HOST to the TV's IP address")
CONF = Path.home() / ".config" / "tcl_tv" / "remote"
CERT, KEY = CONF / "cert.pem", CONF / "key.pem"


def remote() -> AndroidTVRemote:
    CONF.mkdir(parents=True, exist_ok=True)
    os.chmod(CONF, 0o700)
    return AndroidTVRemote("tcl_tv PC", str(CERT), str(KEY), TV, enable_ime=False)


async def wait_for_code(path: Path) -> str:
    for _ in range(180):
        if path.exists() and path.read_text().strip():
            code = path.read_text().strip()
            path.unlink()
            return code
        await asyncio.sleep(1)
    sys.exit("no pairing code within 3 minutes")


async def pair(code_file: str | None) -> None:
    r = remote()
    await r.async_generate_cert_if_missing()
    for f in (CERT, KEY):
        os.chmod(f, 0o600)
    await r.async_start_pairing()
    print("Pairing code is showing on the TV", flush=True)
    code = await wait_for_code(Path(code_file)) if code_file else input("Code: ").strip()
    await r.async_finish_pairing(code)
    print("Paired")


async def connected() -> AndroidTVRemote:
    if not CERT.exists():
        sys.exit("not paired yet: run 'pair' first")
    r = remote()
    await r.async_connect()
    await asyncio.sleep(1)  # let the TV send its initial state
    return r


async def status() -> None:
    r = await connected()
    print(f"on={r.is_on} app={r.current_app} volume={r.volume_info} device={r.device_info}")
    r.disconnect()


async def keys(names: list[str]) -> None:
    r = await connected()
    for k in names:
        r.send_key_command(int(k) if k.isdigit() else k)
        await asyncio.sleep(0.3)
    r.disconnect()


async def app(link: str) -> None:
    r = await connected()
    r.send_launch_app_command(link)
    await asyncio.sleep(0.5)
    r.disconnect()


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    pp = sub.add_parser("pair")
    pp.add_argument("--code-file")
    sub.add_parser("status")
    sub.add_parser("key").add_argument("names", nargs="+")
    sub.add_parser("app").add_argument("link")
    a = p.parse_args()
    if a.cmd == "pair":
        asyncio.run(pair(a.code_file))
    elif a.cmd == "status":
        asyncio.run(status())
    elif a.cmd == "key":
        asyncio.run(keys(a.names))
    else:
        asyncio.run(app(a.link))


if __name__ == "__main__":
    main()
