"""Terminal servers: recognised by name, the line, and the two logins (ConsoleLogin)."""

import os
import unittest

from support import args, TempDir
from truffle import config, console, inventory, state
from truffle.terminal import Notes

QUIET = Notes(colors=False)


class TestConsole(TempDir):
    """Terminal servers: recognised by name, logged into as user:<7000 + line>."""

    def dev(self, name):
        return inventory.Device({}, "10.0.0.1", name, [name])

    def test_recognised_by_name_only(self):
        cfg = config.load_config(args())
        self.assertTrue(console.is_console_server(cfg, self.dev("ab-12-ts1-01")))
        self.assertTrue(console.is_console_server(cfg, self.dev("AB-12-TS3-02.example.net")))
        for name in ("ab-12-s34-w4", "ab-12-ts12-01", "ab-12-ts-01", "ts1", ""):
            self.assertFalse(console.is_console_server(cfg, self.dev(name)), name)

    def test_console_hosts_can_be_changed_or_switched_off(self):
        cfg = config.load_config(args(config=self.write("c.conf", "[truffle]\nconsole_hosts = con-*, *-cs?\n")))
        self.assertTrue(console.is_console_server(cfg, self.dev("con-berlin")))
        self.assertTrue(console.is_console_server(cfg, self.dev("ber-cs1")))
        self.assertFalse(console.is_console_server(cfg, self.dev("ab-12-ts1-01")))
        cfg = config.load_config(args(config=self.write("c.conf", "[truffle]\nconsole_hosts =\n")))
        self.assertFalse(console.is_console_server(cfg, self.dev("ab-12-ts1-01")))

    def test_line_to_username(self):
        cfg = config.load_config(args())
        self.assertEqual(console.parse_console_line(cfg, "12"), 12)
        self.assertEqual(console.parse_console_line(cfg, " 7 "), 7)
        for bad in ("", "0", "abc", "1 2", "1234", "-1", "12a"):
            self.assertIsNone(console.parse_console_line(cfg, bad), bad)
        self.assertEqual(console.console_user(cfg, "timmy", 12), "timmy:7012")
        self.assertEqual(console.console_user(cfg, "timmy", 1), "timmy:7001")
        self.assertTrue(config.valid_user(console.console_user(cfg, "timmy", 12)))

    def test_login_template(self):
        cfg = config.load_config(args(config=self.write("c.conf", "[truffle]\nconsole_login = {user}:port{port}\n"
                                                               "console_port_base = 0\n")))
        self.assertEqual(console.console_user(cfg, "timmy", 5), "timmy:port5")
        for body in ("console_login = {user}\n", "console_login = {user}:{port}{0}\n",
                     "console_login = {user.__class__}:{port}\n", "console_port_base = lots\n"):
            with self.assertRaises(config.ConfigError, msg=body):
                config.load_config(args(config=self.write("c.conf", "[truffle]\n" + body)))

    def test_last_lines_and_login_are_remembered_per_terminal_server(self):
        st = state.UserState(os.path.join(self.tmp, "state"))
        self.assertEqual(st.console_choice("ab-12-ts1-01"), ([], "radius"))
        st.save_console_choice("ab-12-ts1-01", [12], "local")
        st.save_console_choice("ab-12-ts2-01", [3, 7, 12], "manual")
        st.save_console_choice("ab-12-ts1-01", [14], "radius")
        again = state.UserState(os.path.join(self.tmp, "state"))
        self.assertEqual(again.console_choice("ab-12-ts1-01"), ([14], "radius"))
        self.assertEqual(again.console_choice("ab-12-ts2-01"), ([3, 7, 12], "manual"))
        with open(os.path.join(self.tmp, "state", "console")) as f:
            self.assertEqual(len(f.readlines()), 2)

    def test_a_saved_single_line_from_before_still_reads(self):
        d = os.path.join(self.tmp, "state")
        os.makedirs(d)
        with open(os.path.join(d, "console"), "w") as f:
            f.write("ab-12-ts1-01\t12\tlocal\nab-12-ts2-01\tx y\tradius\n")
        st = state.UserState(d)
        self.assertEqual(st.console_choice("ab-12-ts1-01"), ([12], "local"))
        self.assertEqual(st.console_choice("ab-12-ts2-01"), ([], "radius"))         # garbage: ignored

    def test_several_lines(self):
        cfg = config.load_config(args())
        for text, lines in (("12", [12]), ("3 7 12", [3, 7, 12]), ("3,7, 12", [3, 7, 12]),
                            ("3-5 12", [3, 4, 5, 12]), ("12 3 12", [12, 3]), (" 4-4 ", [4])):
            self.assertEqual(console.parse_console_lines(cfg, text), (lines, None), text)
        for bad in ("", " ", "abc", "5-3", "0", "3 x", "1-200", "-4", "3--5"):
            lines, why = console.parse_console_lines(cfg, bad)
            self.assertIsNone(lines, bad)
            self.assertTrue(why, bad)
        self.assertEqual(console.lines_text([3, 7, 12]), "3 7 12")


class TestConsoleLogin(unittest.TestCase):
    """The console login's decisions, without a pty: what is typed when."""

    def run_to_login(self, c):
        c.password_sent(0.0)
        self.assertEqual(c.tick(2.0), [("send", b"\r")])          # quiet -> Enter wakes the line

    def test_types_only_at_the_prompts(self):
        c = console.ConsoleLogin("timmy", "secret", "radius", notes=QUIET)
        self.run_to_login(c)
        self.assertEqual(c.output("\r\nLast login: Mon Oct 19 on ttyS0\r\n", 2.1), [])
        self.assertEqual(c.output("Login: ", 2.2), [("send", b"timmy\r")])
        self.assertEqual(c.output("timmy\r\n", 2.3), [])          # our own echo is no prompt
        self.assertEqual(c.output("Password: ", 2.4), [("send", b"secret\r")])
        self.assertEqual(c.output("\r\nsw:1>", 2.5), [])
        self.assertFalse(c.refused)

    def test_no_login_prompt_means_nothing_typed(self):
        c = console.ConsoleLogin("timmy", "secret", "radius", wake=5, notes=QUIET)
        self.run_to_login(c)
        self.assertEqual(c.output("\r\nsw:1#", 2.1), [])                # somebody left it logged in
        self.assertEqual(c.tick(7.1), [("send", b"\r")])                # Enter once more ...
        self.assertEqual(c.output("\r\nsw:1#", 7.2), [])
        actions = c.tick(12.2)                                          # ... then hand over
        self.assertEqual(c.step, "watch")
        self.assertEqual([kind for kind, _ in actions], ["show"])
        self.assertEqual(c.output("Login: ", 13), [])                   # too late: never typed now

    def test_refused_once_then_yours(self):
        c = console.ConsoleLogin("timmy", "secret", "radius", notes=QUIET)
        self.run_to_login(c)
        c.output("Login: ", 2.1)
        c.output("Password: ", 2.2)
        actions = c.output("\r\nLogin incorrect\r\nLogin: ", 30)
        self.assertTrue(c.refused)
        self.assertEqual([kind for kind, _ in actions], ["show"])
        self.assertEqual(c.output("Password: ", 31), [])                # never a second time

    def test_your_key_takes_over(self):
        c = console.ConsoleLogin("timmy", "secret", "radius", notes=QUIET)
        self.run_to_login(c)
        c.typed()
        self.assertEqual(c.output("Login: ", 2.1), [])

    def test_the_logout_hint_comes_once_per_logout(self):
        c = console.ConsoleLogin(None, None, "manual", notes=QUIET)
        self.run_to_login(c)
        self.assertEqual(c.output("Login: ", 2.1), [])                  # manual: yours, no hint yet
        c.typed()
        hint = c.output("\r\nLogin: ", 50)
        self.assertIn("Ctrl-Q", hint[0][1])
        self.assertEqual(c.output("", 51) + c.output("\x1b[K", 51), [])
        c.typed()
        self.assertEqual(len(c.output("\r\nLogin: ", 90)), 1)

    def test_terminal_server_prompt_line_wakes_by_itself(self):
        c = console.ConsoleLogin("timmy", "secret", "radius", notes=QUIET)
        c.password_sent(0.0)
        self.assertEqual(c.output("\r\nsw login: ", 0.5), [("send", b"timmy\r")])


if __name__ == "__main__":
    unittest.main()
