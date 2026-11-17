"""truffle --check: what it prints and its exit codes."""

import contextlib
import io
import os
import time
import unittest

from support import args, TempDir
from truffle import cli, config


class TestCheck(TempDir):
    def run_check(self, csv_body):
        data = self.write("sw.csv", csv_body)
        return self.check(self.write("c.conf", "[truffle]\ndata = %s\n" % data))

    def check(self, conf):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = cli.check(config.load_config(args(config=conf)))
        return code, out.getvalue()

    COLUMNS = "Name;IP;subnet;aliases;comment\n"

    def test_clean_list_exits_zero(self):
        code, out = self.run_check(self.COLUMNS + "sw1;10.0.0.1;a;b;c\n")
        self.assertEqual(code, 0)
        self.assertIn("data check   : ok", out)
        self.assertIn("ssh results  : ok", out)          # the pty self-test, D45 review

    def test_warnings_exit_one_so_cron_can_gate(self):
        code, out = self.run_check(self.COLUMNS + "sw1;10.0.0.1;a;b;c\nsw2;10.0.0.1;a;b;c\n")
        self.assertEqual(code, 1)
        self.assertIn("is used 2 times", out)

    def aged_check(self, days, extra=""):
        """--check on a device list last written `days` ago."""
        data = self.write("sw.csv", self.COLUMNS + "sw1;10.0.0.1;a;b;c\n")
        when = time.time() - days * 86400 - 60
        os.utime(data, (when, when))
        return self.check(self.write("c.conf", "[truffle]\ndata = %s\n%s" % (data, extra)))

    def test_the_age_of_the_device_list_is_reported_and_gates_the_exit_code(self):
        """The list is an export somebody runs by hand; when that stops, the list still
        looks correct.  --check says when it was written, and a stale one is a warning so
        a cron check can gate on it."""
        code, out = self.aged_check(2)
        self.assertEqual(code, 0)
        self.assertIn("(2 days ago)", out)
        self.assertNotIn("OLDER", out)
        code, out = self.aged_check(43)
        self.assertEqual(code, 1)
        self.assertIn("43 days ago - OLDER than data_max_age_days = 30", out)

    def test_the_age_check_can_be_switched_off(self):
        code, out = self.aged_check(400, "data_max_age_days = 0\n")
        self.assertEqual(code, 0)
        self.assertIn("not checked: data_max_age_days = 0", out)
        self.assertIn("400 days ago", out)          # still printed, never silently dropped

    def test_a_missing_list_has_no_age_line(self):
        path = self.write("c.conf", "[truffle]\ndata = %s/nope.csv\n" % self.tmp)
        code, out = self.check(path)
        self.assertEqual(code, 2)
        self.assertNotIn("list written", out)

    def test_missing_list_exits_two(self):
        path = self.write("c.conf", "[truffle]\ndata = %s/nope.csv\n" % self.tmp)
        self.assertEqual(self.check(path)[0], 2)

    def test_a_retired_option_is_a_hard_error_not_a_silent_note(self):
        """Back-compat for old config files was dropped on purpose: a stale option now
        refuses to start and names itself, instead of being quietly ignored."""
        data = self.write("sw.csv", self.COLUMNS + "sw1;10.0.0.1;a;b;c\n")
        path = self.write("c.conf", "[truffle]\ndata = %s\nping_workers = 200\n" % data)
        with self.assertRaises(config.ConfigError) as caught:
            config.load_config(args(config=path))
        self.assertIn("ping_workers", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
