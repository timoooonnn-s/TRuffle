"""Session logs, the tmux recorder (--log-sink), and finding the log files."""

import os
import shlex
import shutil
import subprocess
import unittest

from support import TempDir, args, log_cfg
from truffle import config, logs, session, tmux


class TestSessionLog(TempDir):
    """tmux records a running pane through `truffle --log-sink FILE`, so the session log
    can be switched on while the panes are already logged in."""

    def cfg(self):
        return log_cfg(self.tmp)

    def sink(self, path, data, header="# head\n"):
        """Run the recorder the way tmux does: '##' back to '#', then the shell."""
        command = tmux.pipe_command(path, header).replace("##", "#")
        return subprocess.run(shlex.split(command), input=data).returncode

    def test_the_log_file_is_private_and_named_after_the_switch(self):
        log, error = logs.open_session_log(self.cfg(), "sw 1", "10.0.0.1", "timmy")
        self.assertIsNone(error)
        log.close()
        path = os.path.join(self.cfg().log_dir, os.listdir(self.cfg().log_dir)[0])
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
        self.assertEqual(os.stat(os.path.dirname(path)).st_mode & 0o777, 0o700)
        self.assertTrue(path.endswith("_sw_1.log"), path)

    def test_the_sink_writes_the_header_and_what_the_pane_shows(self):
        path = logs.session_log_path(self.cfg(), "sw 1", "10.0.0.1")
        header = logs.log_header("sw 1", "10.0.0.1", "timmy")
        self.assertEqual(self.sink(path, b"\x1b[1;32mFAKE-SW:1>\x1b[0m show vlan\r\n", header), 0)
        with open(path, "rb") as f:
            text = f.read()
        self.assertTrue(text.startswith(b"# TRuffle session log: sw 1 (10.0.0.1) as timmy"))
        self.assertIn(b"FAKE-SW:1> show vlan\n", text)
        self.assertNotIn(b"\x1b", text)
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)      # created private, whatever the umask

    def test_the_sink_never_writes_through_a_symlink(self):
        target = os.path.join(self.tmp, "elsewhere")
        link = os.path.join(self.tmp, "x.log")
        os.symlink(target, link)
        self.assertEqual(self.sink(link, b"secret output"), 1)
        self.assertFalse(os.path.exists(target))

    def test_an_escape_sequence_cut_in_two_is_still_removed(self):
        strip = session.EscapeStripper()
        out = strip.feed(b"FAKE \x1b[1;3") + strip.feed(b"2mSW\x1b") + strip.feed(b"[0m>") + strip.flush()
        self.assertEqual(out, b"FAKE SW>")
        self.assertEqual(session.EscapeStripper().feed(b"plain\r\n"), b"plain\n")

    @unittest.skipUnless(shutil.which("tmux"), "tmux not installed")
    def test_a_pipe_that_cannot_start_leaves_no_file(self):
        error = tmux.record_pane(self.cfg(), "%999999", "sw1", "10.0.0.1", "timmy")
        self.assertIsNotNone(error)
        self.assertEqual(os.listdir(self.cfg().log_dir), [])

    def test_an_unwritable_log_folder_is_reported(self):
        os.makedirs(self.cfg().log_dir, mode=0o500)
        try:
            error = tmux.record_pane(self.cfg(), "%1", "sw1", "10.0.0.1", "timmy")
        finally:
            os.chmod(self.cfg().log_dir, 0o700)
        self.assertIn("cannot write session log", error or "")

    def test_a_path_with_spaces_survives_the_shell(self):
        """tmux runs the pipe command through a shell, so the path must be quoted."""
        odd = os.path.join(self.tmp, "a b; echo x", "f.log")
        self.assertEqual(shlex.split(tmux.pipe_command(odd, "# h").replace("##", "#"))[-3:],
                         ["--log-sink", odd, "# h"])

    def test_tmux_formats_in_a_switch_name_are_not_expanded(self):
        """D44: pipe-pane expands tmux formats before the shell runs the line, so a name
        like 'sw #{pane_id}' from the shared CSV ended up expanded in the log header.
        Every '#' goes to tmux doubled - tmux's own way of writing a literal '#'."""
        header = "# TRuffle session log: sw #{pane_id} #(id)\n"
        command = tmux.pipe_command("/x.log", header)
        self.assertNotIn("#{", command.replace("##", ""))
        self.assertNotIn("#(", command.replace("##", ""))
        self.assertEqual(shlex.split(command.replace("##", "#"))[-1], header)

    def test_a_pane_is_told_to_record_itself(self):
        """With the log on, a pane starts its tmux recording before it shows anything -
        TRuffle doing it from outside came too late for a fast switch's banner."""
        cfg = config.load_config(args(log=True))
        self.assertIn("--log", tmux.pane_command(cfg, "/x.sock", "a" * 32, "10.0.0.1", "sw1"))


class TestLogFiles(TempDir):
    def test_only_files_written_since_start_oldest_first(self):
        cfg = log_cfg(self.tmp)
        os.makedirs(cfg.log_dir)
        os.makedirs(cfg.state_dir)
        old = self.write("logs/20261001-0900_old.log", "x")
        os.utime(old, (1000, 1000))
        self.write("logs/notes.txt", "x")
        a = self.write("logs/20261020-1400_ab-12-ts1-01_line_12.log", "x")
        os.utime(a, (5000, 5000))
        d = self.write("st/debug.log", "x")
        os.utime(d, (6000, 6000))
        self.assertEqual(logs.logs_since(cfg, 2000), [a, d])
        self.assertEqual(logs.logs_since(cfg, 0), [old, a, d])
        cfg.log_dir = os.path.join(self.tmp, "missing")
        self.assertEqual(logs.logs_since(cfg, 0), [d])

    def test_the_footer_names_the_file_only(self):
        r = session.SessionResult()
        self.assertEqual(logs.log_note(r), "")
        r.log_path = "/home/timmy/.local/state/truffle/logs/20261020-1400_sw1.log"
        self.assertEqual(logs.log_note(r), " - session log 20261020-1400_sw1.log (Ctrl-G f: full path)")

    def test_session_log_remembers_its_path(self):
        cfg = log_cfg(self.tmp)
        log, error = logs.open_session_log(cfg, "ab-12-ts1-01 line 12", "10.0.0.1", "timmy:7012")
        log.close()
        self.assertTrue(log.path.endswith("_ab-12-ts1-01_line_12.log"), log.path)
        self.assertTrue(os.path.isfile(log.path))


if __name__ == "__main__":
    unittest.main()


class TestLogCleanup(TempDir):
    """D50: session logs are deleted after log_keep_days, debug.log rotates at 1 MB."""

    def cfg(self, days=180):
        cfg = log_cfg(self.tmp)
        cfg.log_keep_days = days
        os.makedirs(cfg.log_dir, exist_ok=True)
        return cfg

    def old(self, path, days):
        stamp = 1_000_000_000 - days * 86400
        os.utime(path, (stamp, stamp))
        return path

    def test_only_truffles_own_old_logs_go(self):
        cfg = self.cfg()
        now = 1_000_000_000
        gone = self.old(self.write("logs/20250101-090000_ab-12-s34-w4.log", "x"), 200)
        fresh = self.old(self.write("logs/20261001-090000_ab-12-s34-w4.log", "x"), 10)
        mine = self.old(self.write("logs/my-notes.log", "x"), 400)            # not a TRuffle name
        kept_elsewhere = self.old(self.write("kept/20250101-090000_sw.log", "x"), 400)
        target = self.old(self.write("elsewhere.txt", "x"), 400)
        os.symlink(target, os.path.join(cfg.log_dir, "20250101-090000_link.log"))
        self.assertEqual(logs.prune_logs(cfg, now=now), (1, None))
        self.assertFalse(os.path.exists(gone))
        for path in (fresh, mine, kept_elsewhere, target):
            self.assertTrue(os.path.exists(path), path)
        self.assertTrue(os.path.islink(os.path.join(cfg.log_dir, "20250101-090000_link.log")))

    def test_zero_keeps_everything_and_a_missing_folder_is_fine(self):
        cfg = self.cfg(days=0)
        self.old(self.write("logs/20200101-090000_sw.log", "x"), 3000)
        self.assertEqual(logs.prune_logs(cfg, now=1_000_000_000), (0, None))
        cfg = self.cfg()
        cfg.log_dir = os.path.join(self.tmp, "missing")
        self.assertEqual(logs.prune_logs(cfg), (0, None))

    def test_the_default_is_half_a_year(self):
        self.assertEqual(config.load_config(args()).log_keep_days, 180)
        for bad in ("lots", "-1", "4000"):
            with self.assertRaises(config.ConfigError):
                config.load_config(args(config=self.write("c.conf", "[truffle]\nlog_keep_days = %s\n" % bad)))

    def test_the_debug_log_rotates_instead_of_growing(self):
        path = self.write("debug.log", "x" * 2000)
        logs.rotate_debug_log(path, limit=1000)
        self.assertFalse(os.path.exists(path))
        self.assertTrue(os.path.exists(path + ".1"))
        self.write("debug.log", "small")
        logs.rotate_debug_log(path, limit=1000)
        self.assertTrue(os.path.exists(path))
        logs.rotate_debug_log(os.path.join(self.tmp, "none.log"))           # no file: nothing to do
