"""Offline tests for scripts/tv-remote.py.

androidtvremote2 is replaced by a fake that records what the script asks of it, HOME
points at a temporary folder, and asyncio.sleep returns at once. Nothing reaches a TV,
the network or the real pairing key in ~/.config/tcl_tv/remote/.
"""
import asyncio
import importlib.util
import os
import stat
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "tv-remote.py"


class FakeRemote:
    instances: list["FakeRemote"] = []

    def __init__(self, client_name, certfile, keyfile, host, enable_ime=True):
        self.args = (client_name, certfile, keyfile, host, enable_ime)
        self.certfile, self.keyfile = Path(certfile), Path(keyfile)
        self.calls: list[tuple] = []
        self.is_on, self.current_app = True, "com.example.app"
        self.volume_info = {"level": 10, "max": 100, "muted": False}
        self.device_info = {"manufacturer": "TCL"}
        FakeRemote.instances.append(self)

    async def async_generate_cert_if_missing(self):
        self.calls.append(("generate_cert",))
        for f in (self.certfile, self.keyfile):
            f.write_text("not a real key")
            os.chmod(f, 0o644)

    async def async_start_pairing(self):
        self.calls.append(("start_pairing",))

    async def async_finish_pairing(self, code):
        self.calls.append(("finish_pairing", code))

    async def async_connect(self):
        self.calls.append(("connect",))

    def send_key_command(self, key):
        self.calls.append(("key", key))

    def send_launch_app_command(self, link):
        self.calls.append(("app", link))

    def disconnect(self):
        self.calls.append(("disconnect",))


async def no_sleep(_seconds):
    return None


class TvRemoteTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)
        FakeRemote.instances = []
        fake = types.ModuleType("androidtvremote2")
        fake.AndroidTVRemote = FakeRemote
        patches = [
            mock.patch.dict(sys.modules, {"androidtvremote2": fake}),
            mock.patch.dict(os.environ, {"HOME": str(self.home), "TV_HOST": "192.0.2.1"}),
            mock.patch("asyncio.sleep", no_sleep),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self._tmp.cleanup)
        self.tv = self.load()
        self.assertTrue(str(self.tv.CONF).startswith(str(self.home)))

    def load(self):
        spec = importlib.util.spec_from_file_location("tv_remote", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def run_cli(self, *args):
        with mock.patch.object(sys, "argv", ["tv-remote.py", *args]):
            self.tv.main()
        return FakeRemote.instances[-1]

    def pair_first(self):
        self.tv.CONF.mkdir(parents=True)
        self.tv.CERT.write_text("cert")

    def test_needs_the_tv_address(self):
        with mock.patch.dict(os.environ, {"TV_HOST": ""}):
            with self.assertRaises(SystemExit) as e:
                self.load()
        self.assertIn("TV_HOST", str(e.exception.code))

    def test_connects_to_the_address_in_tv_host_without_the_keyboard(self):
        self.pair_first()
        with mock.patch("builtins.print"):
            r = self.run_cli("status")
        name, cert, key, host, ime = r.args
        self.assertEqual((name, host, ime), ("tcl_tv PC", "192.0.2.1", False))
        self.assertEqual(Path(cert).parent, self.home / ".config" / "tcl_tv" / "remote")

    def test_key_names_go_as_names_and_numbers_as_key_codes(self):
        self.pair_first()
        r = self.run_cli("key", "DPAD_DOWN", "243", "HOME")
        self.assertEqual(
            [c for c in r.calls if c[0] == "key"],
            [("key", "DPAD_DOWN"), ("key", 243), ("key", "HOME")],
        )
        self.assertEqual(r.calls[-1], ("disconnect",))

    def test_app_hands_the_tv_a_link(self):
        self.pair_first()
        link = "https://play.google.com/store/apps/details?id=com.spocky.projengmenu"
        r = self.run_cli("app", link)
        self.assertIn(("app", link), r.calls)
        self.assertEqual(r.calls[-1], ("disconnect",))

    def test_status_prints_what_the_tv_reports(self):
        self.pair_first()
        with mock.patch("builtins.print") as out:
            self.run_cli("status")
        line = out.call_args.args[0]
        self.assertTrue(line.startswith("on=True app=com.example.app volume={'level': 10"))

    def test_commands_refuse_to_run_before_pairing(self):
        for args in (["status"], ["key", "HOME"], ["app", "https://example.com"]):
            with self.assertRaises(SystemExit) as e:
                self.run_cli(*args)
            self.assertIn("not paired yet", str(e.exception.code))
        self.assertEqual(FakeRemote.instances, [])

    def test_pairing_keeps_the_key_private(self):
        with mock.patch("builtins.input", return_value=" DAE61C "), mock.patch("builtins.print"):
            r = self.run_cli("pair")
        self.assertEqual(stat.S_IMODE(self.tv.CONF.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(self.tv.CERT.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.tv.KEY.stat().st_mode), 0o600)
        self.assertEqual(
            r.calls, [("generate_cert",), ("start_pairing",), ("finish_pairing", "DAE61C")]
        )

    def test_pairing_reads_the_code_from_a_file_and_removes_it(self):
        code_file = self.home / "code.txt"
        code_file.write_text("DAE61C\n")
        with mock.patch("builtins.print"):
            r = self.run_cli("pair", "--code-file", str(code_file))
        self.assertIn(("finish_pairing", "DAE61C"), r.calls)
        self.assertFalse(code_file.exists())

    def test_waiting_for_a_code_gives_up_after_three_minutes(self):
        slept = []

        async def count_sleep(seconds):
            slept.append(seconds)

        with mock.patch("asyncio.sleep", count_sleep):
            with self.assertRaises(SystemExit) as e:
                asyncio.run(self.tv.wait_for_code(self.home / "never.txt"))
        self.assertEqual(sum(slept), 180)
        self.assertIn("3 minutes", str(e.exception.code))


if __name__ == "__main__":
    unittest.main()
