"""Shared test helpers.  Importing this puts src/ on the path, so `import truffle` works.

Run from the repository root:  python3 -m unittest discover -s tests -v
"""
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import curses  # noqa: E402

LAUNCHER = os.path.join(ROOT, "truffle")
FAKE_SSH = os.path.join(ROOT, "tests", "fake_ssh.py")


def args(**kw):
    """What argparse would hand load_config."""
    base = dict(config=None, data=None, log=False, debug=False, check=False, ascii=False)
    base.update(kw)
    return types.SimpleNamespace(**base)


def log_cfg(tmp):
    """The parts of a Config the log functions read."""
    state = os.path.join(tmp, "st")
    return types.SimpleNamespace(log_dir=os.path.join(tmp, "logs"), state_dir=state,
                                 debug_log=os.path.join(state, "debug.log"))


class PrivateTmux(object):
    """A tmux server of the tests' own (D44).  The tests used to run on the default
    server and closed every truffle-* session in it - the live switch logins of a real
    TRuffle included.  TMUX_TMPDIR moves the socket, and TMUX is dropped so a test run
    from inside tmux cannot reach the outer server either; TRuffle and its panes
    inherit both, so they land on the private server too."""

    def start(self):
        self.dir = tempfile.mkdtemp(prefix="truffle-tmux-")
        self.saved = dict((k, os.environ.get(k)) for k in ("TMUX_TMPDIR", "TMUX", "TMUX_PANE"))
        os.environ["TMUX_TMPDIR"] = self.dir
        os.environ.pop("TMUX", None)
        os.environ.pop("TMUX_PANE", None)

    def stop(self):
        subprocess.run(["tmux", "kill-server"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(self.dir, ignore_errors=True)


class TempDir(unittest.TestCase):
    """A private temp dir, and no real user config read."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._env = dict(os.environ)
        os.environ["XDG_CONFIG_HOME"] = os.path.join(self.tmp, "xdg")   # ignore the real user config

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)
        shutil.rmtree(self.tmp)

    def write(self, name, content, mode="w", encoding="utf-8"):
        path = os.path.join(self.tmp, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if "b" in mode:
            with open(path, mode) as f:
                f.write(content)
        else:
            with open(path, mode, encoding=encoding, newline="") as f:
                f.write(content)
        return path


class FakeWin(object):
    """Feeds a character stream to read_key the way curses would."""

    def __init__(self, text):
        self.buf = list(text)

    def timeout(self, ms):
        pass

    def get_wch(self):
        if not self.buf:
            raise curses.error("no input")
        return self.buf.pop(0)
