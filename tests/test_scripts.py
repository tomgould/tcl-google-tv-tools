"""Offline tests for the shell scripts.

Each test copies scripts/, config/ and batches/ into a temporary folder and runs them
there, with tests/fake-bin first on PATH. Its adb records every call and answers from
files, so nothing touches a TV or the network, and the repo's own logs/ is never written.
"""
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FAKE_BIN = REPO / "tests" / "fake-bin"
TV = "192.0.2.1:5555"  # TEST-NET-1: reserved for documentation, never routed

# The six packages from other debloat lists that the keep-list protects.
REFUSED = [
    "com.google.android.tts",
    "com.google.android.tungsten.setupwraith",
    "com.android.tv.frameworkpackagestubs",
    "com.tcl.suspension",
    "com.tcl.ttvs",
    "com.android.sdksandbox",
]


def entries(path: Path) -> list[str]:
    """Package names in a batch or keep-list file, as the scripts read them."""
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line.split()[0])
    return out


BATCHES = sorted((REPO / "batches").glob("batch-*.txt"))
KEEP = entries(REPO / "config" / "keep-list.txt")
BATCHED = [p for b in BATCHES for p in entries(b)]


class ScriptTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        self.root = tmp / "repo"
        for d in ("scripts", "config", "batches"):
            shutil.copytree(REPO / d, self.root / d)
        self.state = tmp / "adb"
        self.state.mkdir()
        self.env = {
            "PATH": f"{FAKE_BIN}:{os.environ['PATH']}",
            "HOME": str(tmp),
            "TV": TV,
            "FAKE_ADB_STATE": str(self.state),
        }
        found = subprocess.run(
            ["bash", "-c", "command -v adb"], env=self.env, capture_output=True, text=True
        ).stdout.strip()
        self.assertEqual(found, str(FAKE_BIN / "adb"), "the fake adb must come first on PATH")

    def tearDown(self):
        self._tmp.cleanup()

    def tv_has(self, installed=(), disabled=()):
        (self.state / "installed.txt").write_text("".join(f"package:{p}\n" for p in installed))
        (self.state / "disabled.txt").write_text("".join(f"package:{p}\n" for p in disabled))

    def disabled(self) -> set[str]:
        text = (self.state / "disabled.txt").read_text()
        return {l.removeprefix("package:") for l in text.splitlines() if l}

    def calls(self) -> list[str]:
        log = self.state / "calls.log"
        return log.read_text().splitlines() if log.exists() else []

    def write_batch(self, name, packages):
        path = self.root / "batches" / name
        path.write_text("# test batch\n" + "".join(f"{p}   # reason\n" for p in packages))
        return path

    def run_script(self, *args, env=None):
        return subprocess.run(
            ["bash", str(self.root / "scripts" / args[0]), *args[1:]],
            env=env or self.env, capture_output=True, text=True, timeout=60,
        )


class TvBatchTest(ScriptTest):
    def test_refuses_every_keep_list_package_and_changes_nothing(self):
        self.tv_has(installed=REFUSED)
        batch = self.write_batch("other-lists.txt", REFUSED)
        r = self.run_script("tv-batch.sh", "apply", str(batch))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(
            r.stdout.splitlines(), [f"REFUSED  {p} (on keep-list)" for p in REFUSED]
        )
        self.assertFalse([c for c in self.calls() if "disable-user" in c])
        self.assertEqual(self.disabled(), set())
        self.assertFalse((self.root / "logs" / "changes.log").exists())

    def test_disables_the_rest_of_a_mixed_batch(self):
        self.tv_has(installed=["com.tcl.tv", "com.tcl.gallery", "com.tcl.bi"])
        batch = self.write_batch("mixed.txt", ["com.tcl.gallery", "com.tcl.tv", "com.tcl.bi"])
        r = self.run_script("tv-batch.sh", "apply", str(batch))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("REFUSED  com.tcl.tv (on keep-list)", r.stdout)
        self.assertEqual(self.disabled(), {"com.tcl.gallery", "com.tcl.bi"})
        disables = [c for c in self.calls() if "disable-user" in c]
        self.assertEqual(len(disables), 2)
        self.assertFalse([c for c in self.calls() if "uninstall" in c])

    def test_disables_with_disable_user_and_logs_each_change_with_a_timestamp(self):
        self.tv_has(installed=["com.tcl.gallery", "com.tcl.bi"])
        batch = self.write_batch("batch-99.txt", ["com.tcl.gallery", "com.tcl.bi"])
        r = self.run_script("tv-batch.sh", "apply", str(batch))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"-s {TV} shell pm disable-user --user 0 com.tcl.gallery", self.calls())
        log = (self.root / "logs" / "changes.log").read_text().splitlines()
        self.assertEqual(len(log), 2)
        stamp = r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d"
        self.assertRegex(log[0], rf"^{stamp} apply batch-99\.txt com\.tcl\.gallery: Package com\.tcl\.gallery new state: disabled-user$")
        self.assertRegex(log[1], rf"^{stamp} apply batch-99\.txt com\.tcl\.bi: ")

    def test_skips_packages_that_are_not_installed(self):
        self.tv_has(installed=["com.tcl.gallery"])
        batch = self.write_batch("batch-99.txt", ["com.tcl.gallery", "com.example.absent"])
        r = self.run_script("tv-batch.sh", "apply", str(batch))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("absent   com.example.absent", r.stdout)
        self.assertEqual(self.disabled(), {"com.tcl.gallery"})

    def test_undo_enables_the_batch_again_and_logs_it(self):
        self.tv_has(installed=["com.tcl.gallery", "com.tcl.bi"], disabled=["com.tcl.gallery", "com.tcl.bi"])
        batch = self.write_batch("batch-99.txt", ["com.tcl.gallery", "com.tcl.bi"])
        r = self.run_script("tv-batch.sh", "undo", str(batch))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.disabled(), set())
        log = (self.root / "logs" / "changes.log").read_text()
        self.assertIn("undo batch-99.txt com.tcl.gallery:", log)

    def test_status_reports_without_changing_anything(self):
        self.tv_has(installed=["com.tcl.gallery", "com.tcl.bi"], disabled=["com.tcl.gallery"])
        batch = self.write_batch("batch-99.txt", ["com.tcl.gallery", "com.tcl.bi"])
        r = self.run_script("tv-batch.sh", "status", str(batch))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines(), ["disabled com.tcl.gallery", "enabled  com.tcl.bi"])
        self.assertFalse([c for c in self.calls() if "disable-user" in c or "enable --user" in c])

    def test_needs_the_tv_address(self):
        env = {k: v for k, v in self.env.items() if k != "TV"}
        batch = self.write_batch("batch-99.txt", ["com.tcl.gallery"])
        r = self.run_script("tv-batch.sh", "apply", str(batch), env=env)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("set TV", r.stderr)
        self.assertEqual(self.calls(), [])

    def test_stops_if_the_tv_has_not_authorised_this_computer(self):
        (self.state / "state").write_text("unauthorized\n")
        self.tv_has(installed=["com.tcl.gallery"])
        batch = self.write_batch("batch-99.txt", ["com.tcl.gallery"])
        r = self.run_script("tv-batch.sh", "apply", str(batch))
        self.assertEqual(r.returncode, 1)
        self.assertFalse([c for c in self.calls() if " shell " in c])

    def test_rejects_an_unknown_action_and_a_missing_batch_file(self):
        self.tv_has(installed=["com.tcl.gallery"])
        batch = self.write_batch("batch-99.txt", ["com.tcl.gallery"])
        r = self.run_script("tv-batch.sh", "remove", str(batch))
        self.assertEqual(r.returncode, 1)
        self.assertIn("unknown action", r.stderr)
        r = self.run_script("tv-batch.sh", "apply", str(self.root / "batches" / "nope.txt"))
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.disabled(), set())


class BatchFilesTest(unittest.TestCase):
    def test_no_batch_package_is_on_the_keep_list(self):
        self.assertEqual(sorted(set(BATCHED) & set(KEEP)), [])

    def test_no_package_is_in_two_batches(self):
        self.assertEqual(len(BATCHED), len(set(BATCHED)))

    def test_every_entry_is_a_package_name(self):
        name = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+$")
        for p in BATCHED + KEEP:
            self.assertRegex(p, name)


def healthy_responses(state: Path):
    """What a correctly set-up TV answers to tv-status.sh."""
    lines = {
        "cmd appops get com.spocky.projengmenu AUTO_START": "AUTO_START: allow; time=+1d",
        "cmd appops get io.github.sds100.keymapper AUTO_START": "AUTO_START: allow; time=+1d",
        "dumpsys accessibility": "Bound services:{Service[label=Projectivy Launcher, ...], Service[label=Key Mapper, ...]}",
        "settings get secure accessibility_enabled": "1",
        "settings get secure attentive_timeout": "-1",
        "settings get global window_animation_scale": "0.5",
        "settings get global transition_animation_scale": "0.5",
        "settings get global animator_duration_scale": "0.5",
        "cmd hdmi_control cec_setting get tv_wake_on_one_touch_play": "tv_wake_on_one_touch_play = 1",
        "cmd hdmi_control cec_setting get tv_send_standby_on_sleep": "tv_send_standby_on_sleep = 1",
        "settings get secure screensaver_components": "com.google.android.apps.tv.dreamx/.service.Backdrop",
        "cut -d. -f1 /proc/uptime": "120",
        "getprop sys.boot_completed": "1",
    }
    (state / "responses.txt").write_text("".join(f"{k}\t{v}\n" for k, v in lines.items()))
    return lines


class TvStatusTest(ScriptTest):
    def setUp(self):
        super().setUp()
        healthy_responses(self.state)
        self.tv_has(installed=BATCHED + KEEP, disabled=BATCHED)

    def assert_read_only(self):
        changes = re.compile(r"disable-user|pm enable|uninstall|settings (put|delete)|appops set|appops write|reboot|input |am start")
        self.assertFalse([c for c in self.calls() if changes.search(c)])

    def test_passes_on_a_tv_that_matches_the_setup(self):
        r = self.run_script("tv-status.sh")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertTrue(r.stdout.rstrip().endswith("All checks passed."))
        for b in BATCHES:
            n = len(entries(b))
            self.assertIn(f"ok    {b.name}: {n}/{n} disabled", r.stdout)
        self.assertNotIn("FAIL", r.stdout)
        self.assert_read_only()

    def test_fails_when_a_batch_package_is_enabled_again(self):
        self.tv_has(installed=BATCHED + KEEP, disabled=BATCHED[1:])
        r = self.run_script("tv-status.sh")
        self.assertEqual(r.returncode, 1)
        self.assertIn(f"FAIL  {BATCHES[0].name}: {BATCHED[0]} is enabled again", r.stdout)
        self.assert_read_only()

    def test_fails_when_a_keep_list_package_is_disabled(self):
        self.tv_has(installed=BATCHED + KEEP, disabled=BATCHED + ["com.google.android.tts"])
        r = self.run_script("tv-status.sh")
        self.assertEqual(r.returncode, 1)
        self.assertIn("FAIL  keep-list package disabled: com.google.android.tts", r.stdout)

    def test_fails_when_the_boot_permission_is_reset(self):
        lines = healthy_responses(self.state)
        lines["cmd appops get com.spocky.projengmenu AUTO_START"] = "AUTO_START: ignore"
        (self.state / "responses.txt").write_text("".join(f"{k}\t{v}\n" for k, v in lines.items()))
        r = self.run_script("tv-status.sh")
        self.assertEqual(r.returncode, 1)
        self.assertIn("FAIL  AUTO_START com.spocky.projengmenu = AUTO_START: ignore (expected AUTO_START: allow)", r.stdout)

    def test_fails_when_an_accessibility_service_is_not_bound(self):
        lines = healthy_responses(self.state)
        lines["dumpsys accessibility"] = "Bound services:{Service[label=Key Mapper, ...]}"
        (self.state / "responses.txt").write_text("".join(f"{k}\t{v}\n" for k, v in lines.items()))
        r = self.run_script("tv-status.sh")
        self.assertEqual(r.returncode, 1)
        self.assertIn("FAIL  accessibility service not bound: Projectivy Launcher", r.stdout)


class TvRestartTest(ScriptTest):
    def setUp(self):
        super().setUp()
        healthy_responses(self.state)
        self.tv_has(installed=BATCHED + KEEP, disabled=BATCHED)
        (self.state / "boot_id").write_text("before-restart\n")

    def test_saves_state_then_restarts_with_a_normal_shutdown_then_checks(self):
        r = self.run_script("tv-restart.sh")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        calls = self.calls()
        write = calls.index(f"-s {TV} shell cmd appops write-settings")
        restart = calls.index(f"-s {TV} shell svc power reboot")
        self.assertLess(write, restart)
        self.assertFalse([c for c in calls if c.endswith(" reboot") and "svc power" not in c])
        self.assertIn("All checks passed.", r.stdout)
        log = (self.root / "logs" / "changes.log").read_text()
        self.assertIn("restart via scripts/tv-restart.sh", log)

    def test_waits_for_a_new_boot_before_checking(self):
        # The fake TV's boot ID only changes when it gets `svc power reboot`; the health
        # check must run after the new ID appears, never against the old boot.
        r = self.run_script("tv-restart.sh")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        calls = self.calls()
        restart = calls.index(f"-s {TV} shell svc power reboot")
        first_check = next(i for i, c in enumerate(calls) if "pm list packages" in c)
        self.assertGreater(first_check, restart)


class TvYoutubeTest(ScriptTest):
    def test_dry_run_prints_the_command_without_touching_the_tv(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        r = self.run_script("tv-youtube.sh", "--dry-run", url)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"-d '{url}'", r.stdout)
        self.assertIn("app.smarttube.fdroid/", r.stdout)
        self.assertEqual(self.calls(), [])

    def test_accepts_short_and_music_links(self):
        for url in ("https://youtu.be/dQw4w9WgXcQ", "https://music.youtube.com/watch?v=abc_123-x"):
            r = self.run_script("tv-youtube.sh", "--dry-run", url)
            self.assertEqual(r.returncode, 0, url)

    def test_refuses_other_sites_and_shell_characters(self):
        for url in (
            "https://example.com/watch?v=x",
            "http://www.youtube.com/watch?v=x",
            "https://www.youtube.com/watch?v=x';reboot;'",
            "https://www.youtube.com/watch?v=x$(id)",
            "https://www.youtube.com.evil.example/watch",
        ):
            r = self.run_script("tv-youtube.sh", "--dry-run", url)
            self.assertEqual(r.returncode, 1, url)
            self.assertIn("not a youtube.com or youtu.be link", r.stderr)
        self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main()
