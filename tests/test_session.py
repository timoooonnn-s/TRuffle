"""Tests for the ssh session relay (run_session) against tests/fake_ssh.py.

A pseudo-terminal plays the user's terminal; a thread on its other side
waits for text and types like a user would.
"""
import os
import pty
import select
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import warnings

from test_truffle import tl

FAKE_SSH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fake_ssh.py")


class User(threading.Thread):
    """Waits for each expected text, then types the answer. Records everything shown."""

    def __init__(self, fd, script):
        threading.Thread.__init__(self)
        self.daemon = True
        self.fd, self.script = fd, script
        self.transcript, self.error, self.finished = "", None, False

    def _read(self, timeout):
        if select.select([self.fd], [], [], timeout)[0]:
            try:
                data = os.read(self.fd, 4096)
            except OSError:
                return False
            if not data:
                return False
            self.transcript += data.decode("utf-8", "replace")
        return True

    def run(self):
        pos = 0
        for expect, answer in self.script:
            deadline = time.time() + 10
            while expect not in self.transcript[pos:]:
                if time.time() > deadline or not self._read(0.1):
                    self.error = "timed out waiting for %r" % expect
                    return
            pos = self.transcript.index(expect, pos) + len(expect)
            time.sleep(0.05)
            os.write(self.fd, answer.encode())
        while not self.finished and self._read(0.1):
            pass                                  # keep draining so the child never blocks


class PtyTest(unittest.TestCase):

    def setUp(self):
        # forkpty() next to the helper thread is fine here (the child execs at once)
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        self.home = tempfile.mkdtemp()
        self._home = os.environ.get("HOME")
        os.environ["HOME"] = self.home            # fake_ssh's known_hosts lives here
        self.master, self.slave = pty.openpty()

    def tearDown(self):
        os.environ["HOME"] = self._home
        for fd in (self.master, self.slave):
            try:
                os.close(fd)
            except OSError:
                pass
        shutil.rmtree(self.home)

    def session(self, host, password, script=(), one_try=True, typeahead=None, user="timmy", console=None):
        argv = [sys.executable, FAKE_SSH, "-l", user]
        if one_try:
            argv += ["-o", "NumberOfPasswordPrompts=1"]
        user = User(self.master, list(script))
        if typeahead:
            os.write(self.master, typeahead)
        user.start()
        result = tl.run_session(argv + ["--", host], password, in_fd=self.slave, out_fd=self.slave,
                                console=console)
        user.finished = True
        user.join(2)
        self.assertIsNone(user.error, user.transcript)
        return result, user.transcript


class SessionTest(PtyTest):

    def test_login_session_logout(self):
        r, out = self.session("10.99.0.1", "secret", [("FAKE-SW:1>", "show vlan\r"), ("you typed", "exit\r")])
        self.assertTrue(r.password_sent)
        self.assertFalse(r.auth_failed)
        self.assertTrue(r.user_typed)
        self.assertEqual(r.exit_code, 255)                 # like many switches on logout ...
        self.assertFalse(r.failed)                         # ... but still a normal logout
        self.assertNotIn("secret", out)                    # the password is never echoed

    def test_wrong_password_one_try(self):
        r, out = self.session("10.99.0.1", "wrong")
        self.assertTrue(r.auth_failed)
        self.assertTrue(r.failed)

    def test_second_prompt_aborts_instead_of_retrying(self):
        r, out = self.session("10.99.0.1", "wrong", one_try=False)
        self.assertTrue(r.auth_failed)
        self.assertEqual(out.count("Permission denied, please try again."), 1)
        self.assertNotEqual(r.exit_code, 0)

    def test_permission_denied_inside_session_is_not_a_login_failure(self):
        r, _ = self.session("10.99.0.1", "secret", [("FAKE-SW:1>", "denied\r"), ("Permission denied", "exit\r")])
        self.assertFalse(r.auth_failed)
        self.assertFalse(r.failed)

    def test_later_password_prompt_is_not_answered(self):
        r, out = self.session("10.99.0.1", "secret", [("FAKE-SW:1>", "pwtest\r"), ("Enter password:", "manual\r"),
                                                      ("got", "exit\r")])
        self.assertIn("got 'manual'", out)
        self.assertNotIn("got 'secret'", out)

    def test_typeahead_is_dropped(self):
        r, _ = self.session("10.99.0.1", "secret", [("FAKE-SW:1>", "exit\r")], typeahead=b"\r\r")
        self.assertTrue(r.password_sent)
        self.assertFalse(r.auth_failed)

    def test_prompt_not_recognised_is_reported(self):
        """A stored password that never gets typed must be visible, not silent."""
        r, _ = self.session("10.99.0.1", "secret", [("FAKE-SW:1>", "exit\r")])
        self.assertFalse(r.prompt_missed)                  # normal case: the prompt was found
        result = tl.SessionResult()
        result.wanted_password, result.password_sent = True, False
        result.user_typed, result.exit_code = True, 255        # logged in by hand, then logged out
        self.assertTrue(result.prompt_missed)
        result.password_sent = True                            # TRuffle did type it
        self.assertFalse(result.prompt_missed)
        result.password_sent, result.user_typed, result.exit_code = False, False, 255
        self.assertFalse(result.prompt_missed)                 # dead host: no prompt could appear

    def test_manual_login_logout_is_not_a_failure(self):
        """No stored password (or the prompt was missed): the user types it by hand, and
        the switch exits 255 on logout."""
        r, _ = self.session("10.99.0.1", None, [("password: ", "secret\r"), ("FAKE-SW:1>", "exit\r")],
                            one_try=False)
        self.assertFalse(r.password_sent)
        self.assertTrue(r.user_typed)
        self.assertEqual(r.exit_code, 255)
        self.assertFalse(r.failed)                         # a normal logout, not an error

    def test_manual_wrong_password_is_a_failure(self):
        r, _ = self.session("10.99.0.1", None, [("password: ", "nope\r")])
        self.assertTrue(r.failed)                          # not reported as "Disconnected"
        self.assertIn("Permission denied", r.last_line)

    def test_connection_timeout(self):
        r, _ = self.session("10.99.0.3", "secret")
        self.assertTrue(r.failed)
        self.assertFalse(r.password_sent)

    def test_changed_host_key_names_the_file(self):
        kh = os.path.join(self.home, ".ssh", "known_hosts")
        os.makedirs(os.path.dirname(kh))
        with open(kh, "w") as f:
            f.write("10.99.0.2 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGq7ojR2h0Wq6FvDm3yPq0bqH7m1bE2VtLZmXH1H9g9k\n")
        r, _ = self.session("10.99.0.2", "secret")
        self.assertTrue(r.hostkey_changed)
        self.assertEqual(r.known_hosts, kh)


class ConsoleSessionTest(PtyTest):
    """A terminal server (10.99.0.9 in fake_ssh) and the switch on the serial line behind it."""

    TS, QUIT = "10.99.0.9", "\x11"

    def console(self, line, password="secret", script=(), mode="radius", user="timmy", pw="secret"):
        login = tl.ConsoleLogin(None if mode == "manual" else user, None if mode == "manual" else pw,
                                mode, wait=20, quiet=0.3, wake=0.6, colors=False)
        return self.session(self.TS, password, script, user="timmy:70%02d" % line, console=login)

    def test_both_logins_typed_then_ctrl_q_after_logout(self):
        r, out = self.console(1, script=[("FAKE-CON:1>", "show\r"), ("you typed: show", "exit\r"),
                                         ("goes back to TRuffle", self.QUIT)])
        self.assertTrue(r.password_sent)
        self.assertTrue(r.console_closed)
        self.assertFalse(r.failed)                      # Ctrl-Q is how a console session ends
        self.assertFalse(r.switch_refused)
        self.assertNotIn("secret", out)
        self.assertIn("username typed (radius)", r.events)

    def test_a_console_left_logged_in_gets_nothing_typed(self):
        """Enter shows a CLI prompt, not a login prompt: typing the username and the
        password there would put them into the switch's CLI."""
        r, out = self.console(2, script=[("TRuffle typed nothing", "show\r"), ("you typed: show", self.QUIT)])
        self.assertNotIn("you typed: timmy", out)
        self.assertNotIn("you typed: secret", out)
        self.assertNotIn("username typed (radius)", r.events)
        self.assertTrue(r.console_closed)

    def test_a_refused_switch_login_is_typed_once_then_yours(self):
        r, out = self.console(3, script=[("refused the radius login", "admin\r"), ("Password: ", "local123\r"),
                                         ("FAKE-CON:1>", self.QUIT)])
        self.assertTrue(r.switch_refused)
        self.assertFalse(r.auth_failed)                 # the terminal server took the password
        self.assertEqual(out.count("Login incorrect"), 1)

    def test_the_local_account(self):
        r, out = self.console(3, mode="local", user="admin", pw="local123", script=[("FAKE-CON:1>", self.QUIT)])
        self.assertFalse(r.switch_refused)
        self.assertNotIn("Login incorrect", out)

    def test_a_slow_radius_answer_is_waited_for(self):
        r, out = self.console(4, script=[("FAKE-CON:1>", self.QUIT)])
        self.assertFalse(r.switch_refused)
        self.assertNotIn("over to you", out)

    def test_manual_types_nothing_at_the_switch(self):
        r, out = self.console(1, mode="manual", script=[("Login: ", "timmy\r"), ("Password: ", "secret\r"),
                                                        ("FAKE-CON:1>", self.QUIT)])
        self.assertNotIn("username typed", " ".join(r.events))
        self.assertTrue(r.console_closed)

    def test_wrong_terminal_server_password(self):
        r, _ = self.console(1, password="wrong")
        self.assertTrue(r.auth_failed)
        self.assertTrue(r.failed)


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen not installed")
class RemoveHostKeyTest(unittest.TestCase):
    def test_remove_and_not_found(self):
        tmp = tempfile.mkdtemp()
        try:
            kh = os.path.join(tmp, "known_hosts")
            subprocess.check_call(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", os.path.join(tmp, "k")])
            with open(os.path.join(tmp, "k.pub")) as f:
                key = " ".join(f.read().split()[:2])
            with open(kh, "w") as f:
                f.write("10.99.0.2 %s\n" % key)
            self.assertTrue(tl.remove_host_key("10.99.0.2", kh)[0])
            self.assertFalse(tl.remove_host_key("10.99.0.2", kh)[0])            # already gone
            self.assertFalse(tl.remove_host_key("10.99.0.2", os.path.join(tmp, "missing"))[0])
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
