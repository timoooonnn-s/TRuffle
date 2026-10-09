"""Security properties of the tmux-pane login handover.

Every one of these is a rule the design depends on, so they are tested rather than
assumed: only our own user, only the process tmux started, only once, only briefly.
"""
import os
import socket
import subprocess
import sys
import time
import unittest

from test_truffle import args, tl


class HandoverTest(unittest.TestCase):

    def setUp(self):
        self.handovers = []

    def tearDown(self):
        for h in self.handovers:
            h.close()

    def make(self, user="timmy", password="secret"):
        h = tl.Handover(lambda: (user, password))
        self.handovers.append(h)
        return h

    def ask(self, handover, ticket):
        return tl.handover_request(handover.path, "GET %s" % ticket)

    # -- the normal case ----------------------------------------------------

    def test_a_bound_ticket_gives_the_login_once(self):
        h = self.make()
        ticket = h.issue("10.0.0.1")
        h.bind(ticket, os.getpid())                 # we play the pane tmux started
        answer = self.ask(h, ticket)
        self.assertTrue(answer.startswith("OK "), answer)
        self.assertIn('"password": "secret"', answer)
        self.assertIn('"user": "timmy"', answer)

    def test_a_ticket_cannot_be_used_twice(self):
        h = self.make()
        ticket = h.issue("10.0.0.1")
        h.bind(ticket, os.getpid())
        self.assertTrue(self.ask(h, ticket).startswith("OK "))
        self.assertEqual(self.ask(h, ticket), "ERR already used")
        self.assertTrue(any("twice" in r for r in h.take_refusals()))

    # -- the refusals -------------------------------------------------------

    def test_another_process_cannot_steal_a_ticket(self):
        """The ticket is visible in ps, so it is bound to the pane's process."""
        h = self.make()
        ticket = h.issue("10.0.0.1")
        h.bind(ticket, 999999)                      # some other process is the real pane
        self.assertEqual(self.ask(h, ticket), "ERR wrong process")
        self.assertTrue(any("not the pane" in r for r in h.take_refusals()))

    def test_an_unknown_ticket_is_refused(self):
        h = self.make()
        self.assertEqual(self.ask(h, "0" * 32), "ERR unknown ticket")

    def test_an_expired_ticket_is_refused(self):
        h = self.make()
        ticket = h.issue("10.0.0.1")
        h.bind(ticket, os.getpid())
        h.tickets[ticket]["created"] -= tl.TICKET_LIFETIME + 1
        self.assertEqual(self.ask(h, ticket), "ERR ticket expired")

    def test_an_unbound_ticket_is_refused_at_once(self):
        """issue() without bind() means tmux has not reported a pane yet - nobody may use
        that ticket, and the answer is immediate: no waiting, so no window in which
        anything running as us could keep asking."""
        h = self.make()
        start = time.time()
        self.assertEqual(self.ask(h, h.issue("10.0.0.1")), "ERR wrong process")
        self.assertLess(time.time() - start, 1.0, "an unbound ticket must be refused at once")

    def test_a_ticket_bound_after_the_request_is_still_refused(self):
        """The pane that lost the race asks the user for the password itself.  We do NOT
        hold the request open waiting for the binding - that only widens the window."""
        h = self.make()
        ticket = h.issue("10.0.0.1")
        self.assertEqual(self.ask(h, ticket), "ERR wrong process")
        h.bind(ticket, os.getpid())                   # tmux reports the pid a moment later
        self.assertTrue(self.ask(h, ticket).startswith("OK "))   # a later, bound ask works

    # -- the files on disk --------------------------------------------------

    def test_socket_and_directory_are_private(self):
        h = self.make()
        self.assertEqual(os.stat(h.dir).st_mode & 0o777, 0o700)
        self.assertEqual(os.stat(h.dir).st_uid, os.getuid())
        self.assertEqual(os.stat(h.path).st_mode & 0o077, 0)      # nothing for group / others

    def test_close_removes_everything(self):
        h = self.make()
        path, directory = h.path, h.dir
        h.close()
        self.assertFalse(os.path.exists(path))
        self.assertFalse(os.path.exists(directory))
        with self.assertRaises(OSError):                          # nobody can connect any more
            tl.handover_request(path, "GET x")

    def test_close_twice_is_harmless(self):
        h = self.make()
        h.close()
        h.close()

    # -- the password never reaches a command line --------------------------

    def test_the_pane_command_line_carries_no_password(self):
        cfg = tl.load_config(args())
        cfg.config_file, cfg.debug, cfg.session_log = None, False, False
        command = tl.pane_command(cfg, "/tmp/x.sock", "a" * 32, "10.0.0.1", "sw1")
        self.assertNotIn("secret", command)
        self.assertIn("--pane", command)
        self.assertIn("a" * 32, command)             # only the ticket, which is useless alone

    def test_peer_identity_sees_this_process(self):
        """The uid / pid check is what keeps other users out - make sure it works here
        and is not silently unsupported on this platform."""
        a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            uid, pid = tl.peer_identity(a)
        finally:
            a.close()
            b.close()
        self.assertEqual(uid, os.getuid(), "peer uid unavailable - the handover would refuse everything")
        self.assertEqual(pid, os.getpid())


@unittest.skipUnless(tl.which("tmux"), "tmux not installed")
class TmuxHelpersTest(unittest.TestCase):
    def test_sessions_list_only_ours(self):
        name = "notatrufflesession-%d" % os.getpid()
        try:
            tl.tmux_run("new-session", "-d", "-s", name, "sleep 5")
        except (RuntimeError, OSError):
            self.skipTest("cannot start tmux here")
        try:
            self.assertNotIn(name, tl.truffle_sessions())
        finally:
            tl.tmux_try("kill-session", "-t", name)

    def test_tmux_try_swallows_failures(self):
        tl.tmux_try("this-command-does-not-exist")          # must not raise

    def test_parent_pid_of_a_child(self):
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(3)"])
        try:
            self.assertEqual(tl.parent_pid(proc.pid), os.getpid())
        finally:
            proc.kill()
            proc.wait()


if __name__ == "__main__":
    unittest.main()
