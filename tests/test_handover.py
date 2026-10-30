"""Security properties of the tmux-pane login handover.

Every one of these is a rule the design depends on, so they are tested rather than
assumed: only our own user, only the process tmux started, only once, only briefly.
"""
import json
import os
import socket
import subprocess
import sys
import time
import unittest

from support import PrivateTmux, args
from truffle import config, handover, tmux
from truffle.terminal import which


class HandoverTest(unittest.TestCase):

    def setUp(self):
        self.handovers = []

    def tearDown(self):
        for h in self.handovers:
            h.close()

    def make(self, user="timmy", password="secret"):
        h = handover.Handover(lambda: (user, password))
        self.handovers.append(h)
        return h

    def ask(self, h, ticket):
        return handover.handover_request(h.path, "GET %s" % ticket)

    # -- the normal case ----------------------------------------------------

    def test_a_bound_ticket_gives_the_login_once(self):
        h = self.make()
        ticket = h.issue("10.0.0.1")
        h.bind(ticket, os.getpid())                 # we play the pane tmux started
        answer = self.ask(h, ticket)
        self.assertTrue(answer.startswith("OK "), answer)
        self.assertIn('"password": "secret"', answer)
        self.assertIn('"user": "timmy"', answer)

    def test_only_a_console_ticket_carries_the_switch_login(self):
        """D51: the switch login (e.g. the local account) goes to console panes only -
        an ssh pane next to them never gets it."""
        h = handover.Handover(lambda: ("timmy", "secret"), lambda: ("admin", "local123"))
        self.handovers.append(h)
        ssh_ticket, console_ticket = h.issue("10.0.0.1"), h.issue("10.0.0.9", switch=True)
        h.bind(ssh_ticket, os.getpid())
        h.bind(console_ticket, os.getpid())
        ssh_answer, console_answer = self.ask(h, ssh_ticket), self.ask(h, console_ticket)
        self.assertNotIn("local123", ssh_answer)
        self.assertNotIn("switch_user", ssh_answer)
        login = json.loads(console_answer[3:])
        self.assertEqual((login["user"], login["switch_user"], login["switch_password"]),
                         ("timmy", "admin", "local123"))

    def test_a_local_terminal_server_account_goes_to_console_panes_only(self):
        """D54: a lab terminal server takes its own local account - its console panes get
        that one as THE login, an ssh pane next to them still gets yours."""
        h = handover.Handover(lambda: ("timmy", "secret"), lambda: ("timmy", "secret"),
                              lambda: ("labts", "lab123"))
        self.handovers.append(h)
        ssh_ticket, console_ticket = h.issue("10.0.0.1"), h.issue("10.0.0.9", switch=True)
        h.bind(ssh_ticket, os.getpid())
        h.bind(console_ticket, os.getpid())
        ssh_login = json.loads(self.ask(h, ssh_ticket)[3:])
        console_login = json.loads(self.ask(h, console_ticket)[3:])
        self.assertEqual((ssh_login["user"], ssh_login["password"]), ("timmy", "secret"))
        self.assertEqual((console_login["user"], console_login["password"]), ("labts", "lab123"))
        self.assertEqual(console_login["switch_user"], "timmy")

    def test_a_user_at_host_pane_gets_that_login_only(self):
        """D55: a device saved as labadmin@host gets labadmin's login, the others yours."""
        logins = {"labadmin": ("labadmin", "lab123")}
        h = handover.Handover(lambda: ("timmy", "secret"), account_credentials=lambda u: logins.get(u, (None, None)))
        self.handovers.append(h)
        mine, lab, gone = h.issue("10.0.0.1"), h.issue("10.0.0.2", account="labadmin"), h.issue("10.0.0.3", account="x")
        for t in (mine, lab, gone):
            h.bind(t, os.getpid())
        self.assertEqual(json.loads(self.ask(h, mine)[3:])["user"], "timmy")
        self.assertEqual(json.loads(self.ask(h, lab)[3:]), {"user": "labadmin", "password": "lab123"})
        self.assertEqual(self.ask(h, gone), "ERR no login")

    def test_no_login_held_for_a_pane_is_an_error_not_an_empty_user(self):
        h = handover.Handover(lambda: (None, None))
        self.handovers.append(h)
        ticket = h.issue("10.0.0.1")
        h.bind(ticket, os.getpid())
        self.assertEqual(self.ask(h, ticket), "ERR no login")

    def test_manual_hands_no_switch_login(self):
        h = handover.Handover(lambda: ("timmy", "secret"), lambda: (None, None))
        self.handovers.append(h)
        ticket = h.issue("10.0.0.9", switch=True)
        h.bind(ticket, os.getpid())
        login = json.loads(self.ask(h, ticket)[3:])
        self.assertEqual((login["switch_user"], login["switch_password"]), ("", ""))

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
        h.tickets[ticket]["created"] -= handover.TICKET_LIFETIME + 1
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
            handover.handover_request(path, "GET x")

    def test_close_twice_is_harmless(self):
        h = self.make()
        h.close()
        h.close()

    # -- the password never reaches a command line --------------------------

    def test_the_pane_command_line_carries_no_password(self):
        cfg = config.load_config(args())
        cfg.config_file, cfg.debug, cfg.session_log = None, False, False
        command = tmux.pane_command(cfg, "/tmp/x.sock", "a" * 32, "10.0.0.1", "sw1")
        self.assertNotIn("secret", command)
        self.assertIn("--pane", command)
        self.assertIn("a" * 32, command)             # only the ticket, which is useless alone
        console_command = tmux.pane_command(cfg, "/tmp/x.sock", "a" * 32, "10.0.0.9", "ts1", (7, "local"))
        self.assertIn("--pane-console 7 local", console_command)      # the line and the CHOICE, no login
        self.assertNotIn("--pane-server-login", console_command)
        lab = tmux.pane_command(cfg, "/tmp/x.sock", "a" * 32, "10.0.0.9", "ts1", (7, "radius", "local"))
        self.assertIn("--pane-console 7 radius --pane-server-login local", lab)
        account = tmux.pane_command(cfg, "/tmp/x.sock", "a" * 32, "10.0.0.2", "lab-box", user="labadmin")
        self.assertIn("--pane-user labadmin --pane", account)
        self.assertNotIn("lab123", lab)

    def test_peer_identity_sees_this_process(self):
        """The uid / pid check is what keeps other users out - make sure it works here
        and is not silently unsupported on this platform."""
        a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            uid, pid = handover.peer_identity(a)
        finally:
            a.close()
            b.close()
        self.assertEqual(uid, os.getuid(), "peer uid unavailable - the handover would refuse everything")
        self.assertEqual(pid, os.getpid())


@unittest.skipUnless(which("tmux"), "tmux not installed")
class TmuxHelpersTest(unittest.TestCase):
    def setUp(self):
        self.tmux = PrivateTmux()
        self.tmux.start()
        self.addCleanup(self.tmux.stop)

    def test_sessions_list_only_ours(self):
        name = "notatrufflesession-%d" % os.getpid()
        try:
            tmux.tmux_run("new-session", "-d", "-s", name, "sleep 5")
        except (RuntimeError, OSError):
            self.skipTest("cannot start tmux here")
        try:
            self.assertNotIn(name, tmux.truffle_sessions())
        finally:
            tmux.tmux_try("kill-session", "-t", name)

    def test_tmux_try_swallows_failures(self):
        tmux.tmux_try("this-command-does-not-exist")          # must not raise

    def test_parent_pid_of_a_child(self):
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(3)"])
        try:
            self.assertEqual(handover.parent_pid(proc.pid), os.getpid())
        finally:
            proc.kill()
            proc.wait()


if __name__ == "__main__":
    unittest.main()
