"""End-to-end smoke test: the real curses UI in a tmux pane, ssh = tests/fake_ssh.py.
Skipped when tmux is not installed."""
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SESSION = "uitest-%d" % os.getpid()     # not truffle-*: TRuffle would count it as its own


def tmux(*args):
    return subprocess.run(["tmux"] + list(args), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          check=False).stdout.decode("utf-8", "replace")


@unittest.skipUnless(shutil.which("tmux"), "tmux not installed")
class UiSmokeTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        with open(os.path.join(self.tmp, "data.csv"), "w") as f:
            f.write("Name;IP;subnet;aliases;comment\n"
                    "fake-good;10.99.0.1;lab;Good switch;pw secret\n"
                    "fake-two;10.99.0.5;lab;Second good switch;pw secret\n"
                    "fake-dead;10.99.0.3;lab;Dead switch;timeout\n"
                    "sw10;192.0.2.10;ber;Core Berlin;\n")
        self.start()

    def start(self, extra_conf=""):
        """(Re)start TRuffle in the test session, with extra lines for its config."""
        tmux("kill-session", "-t", SESSION)
        conf = os.path.join(self.tmp, "test.conf")
        with open(conf, "w") as f:
            f.write("[truffle]\ndata = data.csv\nuser = timmy\nssh_command = %s %s\n%s"
                    % (sys.executable, os.path.join(ROOT, "tests", "fake_ssh.py"), extra_conf))
        cmd = "env HOME=%s XDG_CONFIG_HOME=%s TERM=xterm %s %s --config %s; echo EXITED; sleep 30" % (
            shlex.quote(self.tmp), shlex.quote(self.tmp), shlex.quote(sys.executable),
            shlex.quote(os.path.join(ROOT, "truffle")), shlex.quote(conf))
        tmux("new-session", "-d", "-s", SESSION, "-x", "110", "-y", "30", cmd)
        self.wait_for("TRuffle")

    def tearDown(self):
        tmux("kill-session", "-t", SESSION)
        for name in self.our_sessions():
            tmux("kill-session", "-t", "=" + name)
        shutil.rmtree(self.tmp)

    def our_sessions(self):
        """The tmux sessions TRuffle itself started (truffle-HHMMSS)."""
        out = tmux("list-sessions", "-F", "#{session_name}")
        return [n for n in out.splitlines() if n.startswith("truffle-")]

    def wait_for_session(self, timeout=15):
        deadline = time.time() + timeout
        while time.time() < deadline:
            names = self.our_sessions()
            if names:
                return names[0]
            time.sleep(0.2)
        self.fail("TRuffle never started a tmux session:\n%s" % self.screen())

    def panes(self, session):
        out = tmux("list-panes", "-t", "=" + session, "-F", "#{pane_id}")
        return [p for p in out.splitlines() if p.startswith("%")]

    def wait_in_panes(self, session, text, timeout=15):
        """Wait until every pane of that session shows text."""
        deadline = time.time() + timeout
        seen = []
        while time.time() < deadline:
            ids = self.panes(session)
            seen = [tmux("capture-pane", "-p", "-t", p) for p in ids]
            if len(ids) >= 2 and all(text in s for s in seen):
                return
            time.sleep(0.2)
        self.fail("%r not in every pane of %s:\n%s" % (text, session, "\n--\n".join(seen)))

    def mark_two_and_ssh(self, password):
        """Mark the two good switches with Tab, then run ssh with that password."""
        self.keys("fake", literal=True)          # fake-good, fake-two, fake-dead
        self.keys("Tab")                         # marks fake-good, moves down
        self.keys("Tab")                         # marks fake-two
        self.wait_for("2 marked")
        self.keys("Enter")
        self.wait_for("Username")
        self.keys(password, literal=True)
        self.keys("Enter")

    def screen(self):
        return tmux("capture-pane", "-p", "-t", SESSION)

    def keys(self, *keys, literal=False):
        tmux("send-keys", "-t", SESSION, *(["-l"] if literal else []), *keys)
        time.sleep(0.3)

    def wait_for(self, text, timeout=8):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if text in self.screen():
                return
            time.sleep(0.1)
        self.fail("%r not on screen:\n%s" % (text, self.screen()))

    def test_search_ssh_and_back(self):
        self.keys("sw10", literal=True)
        self.assertNotIn("fake-good", self.screen())
        # ESC and a key in the same burst: search is cleared AND the key is kept
        self.keys("\x1bf", literal=True)
        self.wait_for("fake-good")
        self.assertNotIn("sw10", self.screen())             # the search is "f" now
        self.keys("C-u")
        self.keys("Enter")                       # ssh is the default command
        self.wait_for("Username")
        self.keys("secret", literal=True)
        self.keys("Enter")
        self.wait_for("FAKE-SW:1>")
        self.keys("exit", literal=True)
        self.keys("Enter")
        self.wait_for("Disconnected from fake-good")
        self.keys("Left", "Enter")               # "exit" is left of "ssh" (the bar wraps)
        self.wait_for("credentials forgotten")

    def test_two_marked_switches_share_one_login(self):
        """The whole handover, end to end: one password typed in TRuffle, two panes
        logged in by themselves, no password on any command line."""
        self.mark_two_and_ssh("secret")
        session = self.wait_for_session()
        self.wait_in_panes(session, "FAKE-SW:1>")
        self.assertEqual(len(self.panes(session)), 2)
        self.wait_for("1 tmux", timeout=15)              # the top bar names the open session
        ps = subprocess.run(["ps", "-Ao", "args"], stdout=subprocess.PIPE).stdout.decode("utf-8", "replace")
        ours = [line for line in ps.splitlines() if " --pane " in line]
        self.assertTrue(ours, "no pane process found:\n%s" % ps[:2000])
        for line in ours:                      # only the one-time ticket may be visible
            self.assertNotIn("secret", line, "the password reached a command line: %s" % line)

    def test_marks_connect_even_when_the_search_shows_nothing(self):
        """With 2+ marks the selected row does not matter - not even when there is none.
        This used to say "No switch selected" while ping in the same state worked."""
        self.keys("fake", literal=True)
        self.keys("Tab")
        self.keys("Tab")
        self.wait_for("2 marked")
        self.keys("C-u")
        self.keys("zzzz", literal=True)
        self.wait_for("No switch matches")
        self.keys("Enter")
        self.wait_for("Username")
        self.keys("secret", literal=True)
        self.keys("Enter")
        self.wait_in_panes(self.wait_for_session(), "FAKE-SW:1>")

    def test_the_session_log_can_be_switched_on_while_the_panes_run(self):
        """Logged in without a log, then Ctrl-G -> l: the show commands typed into the
        running panes from now on are on file - and the password never is."""
        self.mark_two_and_ssh("secret")
        session = self.wait_for_session()
        self.wait_in_panes(session, "FAKE-SW:1>")
        logs = os.path.join(self.tmp, ".local", "state", "truffle", "logs")
        self.assertFalse(os.path.isdir(logs) and os.listdir(logs), "nothing may be logged yet")
        self.keys("C-g")
        self.wait_for("Settings")
        self.keys("l")
        self.keys("Escape")
        self.wait_for("recording 2 running tmux panes")
        files = sorted(os.listdir(logs))
        self.assertEqual(len(files), 2, files)
        pane = self.panes(session)[0]
        tmux("send-keys", "-t", pane, "-l", "show vlan")
        tmux("send-keys", "-t", pane, "Enter")
        texts = self.wait_for_log(logs, "you typed: show vlan")
        for name in files:
            self.assertEqual(os.stat(os.path.join(logs, name)).st_mode & 0o777, 0o600)
        self.assertNotIn("secret", texts)
        self.keys("C-g")
        self.wait_for("Settings")
        self.keys("l")
        self.keys("Escape")
        self.wait_for("stopped recording 2 running tmux panes")
        tmux("send-keys", "-t", pane, "-l", "after the log")
        tmux("send-keys", "-t", pane, "Enter")
        deadline = time.time() + 10
        while "you typed: after the log" not in tmux("capture-pane", "-p", "-t", pane):
            self.assertLess(time.time(), deadline, "the pane never answered")
            time.sleep(0.2)
        time.sleep(1)                            # give a pipe that wrongly survived time to write
        self.assertNotIn("after the log", self.wait_for_log(logs, "show vlan"))

    def test_panes_started_with_the_log_on_are_recorded_from_the_login(self):
        self.keys("C-g")
        self.wait_for("Settings")
        self.keys("l")
        self.keys("Escape")
        self.mark_two_and_ssh("secret")
        self.wait_in_panes(self.wait_for_session(), "FAKE-SW:1>")
        logs = os.path.join(self.tmp, ".local", "state", "truffle", "logs")
        texts = self.wait_for_log(logs, "Extreme Networks Fabric Engine")
        self.assertEqual(len(os.listdir(logs)), 2)               # one per pane, not two each
        self.assertIn("password:", texts)                       # the prompt is there ...
        self.assertNotIn("secret", texts)                       # ... the password is not

    def test_switching_the_log_off_beats_truffle_conf(self):
        """truffle.conf says session_log = yes, Ctrl-G says off: new panes must not record.
        They used to re-read truffle.conf and record anyway."""
        self.start("session_log = yes\n")
        self.keys("C-g")
        self.wait_for("Settings")
        self.keys("l")
        self.keys("Escape")
        self.mark_two_and_ssh("secret")
        self.wait_in_panes(self.wait_for_session(), "FAKE-SW:1>")
        time.sleep(1)
        logs = os.path.join(self.tmp, ".local", "state", "truffle", "logs")
        self.assertFalse(os.path.isdir(logs) and os.listdir(logs), "panes recorded although the log is off")

    def test_a_log_that_cannot_be_written_says_so(self):
        """The error used to be overwritten by 'Session log on - recording 0 panes'."""
        blocked = os.path.join(self.tmp, "blocked")
        os.makedirs(blocked, mode=0o500)
        self.start("log_dir = %s\n" % blocked)
        self.mark_two_and_ssh("secret")
        self.wait_in_panes(self.wait_for_session(), "FAKE-SW:1>")
        self.keys("C-g")
        self.wait_for("Settings")
        self.keys("l")
        self.keys("Escape")
        self.wait_for("cannot write session log")
        os.chmod(blocked, 0o700)

    def wait_for_log(self, logs, text, timeout=10):
        deadline = time.time() + timeout
        while True:
            texts = ""
            for name in os.listdir(logs):
                with open(os.path.join(logs, name), encoding="utf-8", errors="replace") as f:
                    texts += f.read()
            if text in texts or time.time() > deadline:
                self.assertIn(text, texts)
                return texts
            time.sleep(0.2)

    def test_a_pane_login_failure_makes_truffle_forget_the_password(self):
        """A pane cannot answer over the socket (it is closed by then), so it reports a
        wrong password through the status directory - TRuffle must drop that password
        instead of spending it on switch after switch (TACACS+ lockout)."""
        self.mark_two_and_ssh("wrong-password")
        session = self.wait_for_session()
        self.wait_in_panes(session, "Login failed")
        # Either wording is correct: the wipe can land while TRuffle is still in
        # connect_many (then it is carried into that message) or later, from the poll.
        self.wait_for("you will be asked again", timeout=25)

    def test_failed_connection_pauses(self):
        self.keys("dead", literal=True)
        self.keys("Enter")
        self.wait_for("Username")
        self.keys("secret", literal=True)
        self.keys("Enter")
        self.wait_for("Press any key")
        self.keys("x")
        self.wait_for("ssh exit code 255")       # the reason is also shown in the status line


if __name__ == "__main__":
    unittest.main()
