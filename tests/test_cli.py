"""truffle --check: what it prints and its exit codes."""

import contextlib
import io
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
