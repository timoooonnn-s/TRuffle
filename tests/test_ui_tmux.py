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
SESSION = "treeli-test-%d" % os.getpid()


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
        conf = os.path.join(self.tmp, "test.conf")
        with open(conf, "w") as f:
            f.write("[tree-li]\ndata = data.csv\nuser = timmy\nssh_command = %s %s\n"
                    % (sys.executable, os.path.join(ROOT, "tests", "fake_ssh.py")))
        cmd = "env HOME=%s XDG_CONFIG_HOME=%s TERM=xterm %s %s --config %s; echo EXITED; sleep 30" % (
            shlex.quote(self.tmp), shlex.quote(self.tmp), shlex.quote(sys.executable),
            shlex.quote(os.path.join(ROOT, "tree-li")), shlex.quote(conf))
        tmux("new-session", "-d", "-s", SESSION, "-x", "110", "-y", "30", cmd)
        self.wait_for("TRee-Li")

    def tearDown(self):
        tmux("kill-session", "-t", SESSION)
        for name in self.our_sessions():
            tmux("kill-session", "-t", "=" + name)
        shutil.rmtree(self.tmp)

    def our_sessions(self):
        """The tmux sessions TRee-Li itself started (tree-li-HHMMSS)."""
        out = tmux("list-sessions", "-F", "#{session_name}")
        return [n for n in out.splitlines() if n.startswith("tree-li-")]

    def wait_for_session(self, timeout=15):
        deadline = time.time() + timeout
        while time.time() < deadline:
            names = self.our_sessions()
            if names:
                return names[0]
            time.sleep(0.2)
        self.fail("TRee-Li never started a tmux session:\n%s" % self.screen())

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
        """The whole handover, end to end: one password typed in TRee-Li, two panes
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

    def test_a_pane_login_failure_makes_treeli_forget_the_password(self):
        """A pane cannot answer over the socket (it is closed by then), so it reports a
        wrong password through the status directory - TRee-Li must drop that password
        instead of spending it on switch after switch (TACACS+ lockout)."""
        self.mark_two_and_ssh("wrong-password")
        session = self.wait_for_session()
        self.wait_in_panes(session, "Login failed")
        # Either wording is correct: the wipe can land while TRee-Li is still in
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
