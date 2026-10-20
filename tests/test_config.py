"""truffle.conf -> Config: defaults, overrides, paths, bad values."""

import os
import unittest

from support import args, TempDir
import truffle
from truffle import config, terminal


class TestConfig(TempDir):
    def test_data_on_the_command_line_expands_the_home_directory(self):
        os.environ["HOME"] = self.tmp
        self.assertEqual(config.load_config(args(data="~/sw.csv")).data, os.path.join(self.tmp, "sw.csv"))

    def test_relative_log_and_state_dirs_follow_the_config_file(self):
        """D44 #8: they used to depend on the directory truffle was started from."""
        conf = self.write("site/c.conf", "[truffle]\nlog_dir = logs\nstate_dir = st\n")
        cfg = config.load_config(args(config=conf))
        self.assertEqual(cfg.log_dir, os.path.join(self.tmp, "site", "logs"))
        self.assertEqual(cfg.state_dir, os.path.join(self.tmp, "site", "st"))

    def test_defaults_resolve_data_next_to_script(self):
        cfg = config.load_config(args())
        self.assertEqual(cfg.data, os.path.join(truffle.INSTALL_DIR, "data.csv"))
        self.assertFalse(cfg.session_log)

    def test_config_file_relative_data_and_overrides(self):
        conf = self.write("my.conf", "[truffle]\ndata = lists/sw.csv\n"
                          "columns = Name, location:Where\nsession_log = yes\nuser = netadmin\n")
        cfg = config.load_config(args(config=conf))
        self.assertEqual(cfg.data, os.path.join(self.tmp, "lists", "sw.csv"))
        self.assertEqual(cfg.columns, [("Name", "Name"), ("location", "Where")])
        self.assertTrue(cfg.session_log)
        self.assertEqual(cfg.user, "netadmin")

    def test_unknown_option_and_bad_values(self):
        for body in ("[truffle]\ndatta = x\n", "[truffle]\nping_rate = lots\n",
                     "[truffle]\nsession_log = maybe\n", "[other]\n", "[truffle]\nuser = -oProxyCommand=x\n"):
            conf = self.write("bad.conf", body)
            with self.assertRaises(config.ConfigError, msg=body):
                config.load_config(args(config=conf))


class TestCharset(TempDir):
    def test_setting_and_flag(self):
        self.assertEqual(config.resolve_charset("ascii"), "ascii")
        self.assertEqual(config.resolve_charset("unicode"), "unicode")
        self.assertIn(config.resolve_charset("auto"), ("ascii", "unicode"))
        self.assertEqual(config.load_config(args(ascii=True)).charset_setting, "ascii")
        with self.assertRaises(config.ConfigError):
            config.load_config(args(config=self.write("c.conf", "[truffle]\ncharset = emoji\n")))

    def test_symbol_sets_match(self):
        self.assertEqual(set(terminal.CHARSETS["ascii"]), set(terminal.CHARSETS["unicode"]))
        for value in terminal.CHARSETS["ascii"].values():
            value.encode("ascii")
        self.assertEqual(len(terminal.CHARSETS["unicode"]["box"]), 6)


if __name__ == "__main__":
    unittest.main()
