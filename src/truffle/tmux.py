"""Several devices at once: one tmux session, one pane per device or terminal-server line
(D23, D40, D51), and the session log of panes that are already running (pipe-pane, D41)."""

import errno
import os
import shlex
import subprocess
import sys
import time

from . import LAUNCHER
from .logs import log_header, session_log_path
from .terminal import terminal_size

MAX_PANES = 9
SESSION_PREFIX = "truffle-"
TMUX_ERRORS = (RuntimeError, OSError, subprocess.SubprocessError)
# Panes start in the tmux SERVER's environment; these decide where a pane reads and writes.
PANE_ENV = ("HOME", "PATH", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "TMUX_TMPDIR",
            "XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_RUNTIME_DIR")


def tmux_run(*args):
    """Run a tmux command.  Returns its stripped output; raises RuntimeError on failure."""
    proc = subprocess.run(["tmux"] + list(args), stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", "replace").strip() or "tmux failed")
    return proc.stdout.decode("utf-8", "replace").strip()


def tmux_try(*args):
    """Best effort: cosmetic tmux settings must not break the feature on an old tmux."""
    try:
        tmux_run(*args)
    except TMUX_ERRORS:
        pass


def truffle_sessions():
    """TRuffle's tmux sessions (of any window) that are still alive, oldest first."""
    try:
        lines = tmux_run("list-sessions", "-F", "#{session_created} #{session_name}").splitlines()
    except TMUX_ERRORS:
        return []
    names = [line.split(" ", 1)[1] for line in sorted(lines) if " " in line]
    return [n for n in names if n.startswith(SESSION_PREFIX)]


def session_exists(session):
    try:
        tmux_run("has-session", "-t", "=" + session)
        return True
    except TMUX_ERRORS:
        return False


def free_session_name():
    """truffle-HHMMSS, with a suffix if that name is taken - two multi-ssh actions in
    the same second would otherwise collide."""
    base = SESSION_PREFIX + time.strftime("%H%M%S")
    name, n = base, 1
    while session_exists(name) and n < 100:
        name, n = "%s-%d" % (base, n), n + 1
    return name


def enter_session(session):
    """Attach until you detach (inside tmux: switch-client).  Returns an error, or ''."""
    if os.environ.get("TMUX"):
        try:
            tmux_run("switch-client", "-t", "=" + session)
            return ""
        except TMUX_ERRORS as e:
            return str(e)
    if not session_exists(session):
        return "the tmux session %s is gone" % session
    try:
        code = subprocess.call(["tmux", "attach-session", "-t", "=" + session])
    except (OSError, subprocess.SubprocessError) as e:
        return "cannot run tmux: %s" % e
    return "" if code == 0 else "tmux attach ended with code %d" % code


def shell_command(argv):
    """argv quoted for the shell, every '#' doubled: pipe-pane expands tmux formats before
    the shell runs, so a CSV name like 'sw #{pane_id}' was expanded (D44)."""
    return " ".join(shlex.quote(a) for a in argv).replace("#", "##")


def pipe_command(path, header):
    """What tmux runs to record a pane that is already running (pipe-pane): TRuffle
    itself, writing what the pane shows to a session log."""
    return shell_command([sys.executable, LAUNCHER, "--log-sink", path, header])


def record_pane(cfg, pane, name, host, user):
    """Record one pane into a new session log via pipe-pane (-o: never twice).  The
    recorder creates the file, so a pipe that fails leaves none.  Returns an error or None."""
    try:
        path = session_log_path(cfg, name, host)
        if not os.access(cfg.log_dir, os.W_OK):
            raise OSError(errno.EACCES, "not writable", cfg.log_dir)
    except OSError as e:
        return "cannot write session log: %s" % e
    try:
        tmux_run("pipe-pane", "-o", "-t", pane, pipe_command(path, log_header(name, host, user)))
    except TMUX_ERRORS as e:
        return "cannot record the tmux pane: %s" % e
    return None


class PaneTarget(object):
    """What one pane connects to: a device by ssh, or one line of a terminal server."""

    def __init__(self, dev, line=None):
        self.dev, self.line = dev, line

    @property
    def console(self):
        return self.line is not None

    @property
    def name(self):
        return self.dev.name if self.line is None else "%s line %d" % (self.dev.name, self.line)


def pane_command(cfg, socket_path, ticket, host, name, console=None):
    """TRuffle in --pane mode: the ticket, never the password.  console: (line, login) for
    a terminal-server line.  (new-session and split-window do not expand tmux formats, so
    shell quoting is enough.)"""
    argv = ["env"] + ["%s=%s" % (k, os.environ[k]) for k in PANE_ENV if os.environ.get(k)]
    argv += [sys.executable, LAUNCHER]
    if cfg.config_file:
        argv += ["--config", cfg.config_file]
    if cfg.debug:
        argv += ["--debug"]
    if cfg.session_log:
        argv += ["--log"]                # the pane starts its tmux recording itself
    if cfg.charset == "ascii":
        argv += ["--ascii"]              # what TRuffle shows now, Ctrl-G included
    if console:
        argv += ["--pane-console", str(console[0]), console[1]]
    argv += ["--pane", socket_path, ticket, host, name]
    return " ".join(shlex.quote(a) for a in argv)


def open_panes(cfg, targets, handover, mode=None):
    """Create a tmux session with one pane per PaneTarget (a bare device is an ssh pane).
    mode: the switch login of the console panes.  Returns the session name and
    {pane id: target} - the pane title cannot be trusted for that, a switch can set it."""
    session = free_session_name()
    panes = {}
    targets = [t if isinstance(t, PaneTarget) else PaneTarget(t) for t in targets]

    def start(target, *where):
        dev = target.dev
        ticket = handover.issue(dev.host, switch=target.console)
        command = pane_command(cfg, handover.path, ticket, dev.host, dev.name,
                               (target.line, mode) if target.console else None)
        out = tmux_run(*(list(where) + ["-P", "-F", "#{pane_pid} #{pane_id}", command]))
        pid, _, pane_id = out.strip().partition(" ")
        handover.bind(ticket, int(pid or 0))
        panes[pane_id] = target
        tmux_try("select-pane", "-t", pane_id, "-T", "%s (%s)" % (target.name, dev.host))

    rows, cols = terminal_size() or (24, 80)          # a detached session would default to 80x24
    try:
        start(targets[0], "new-session", "-d", "-s", session, "-x", str(cols), "-y", str(rows))
        for target in targets[1:]:
            start(target, "split-window", "-t", session)
            tmux_try("select-layout", "-t", session, "tiled")
    except BaseException:
        tmux_try("kill-session", "-t", "=" + session)       # never leave half a session behind
        raise
    tmux_try("set-window-option", "-t", session, "synchronize-panes", "off")   # never type into all
    tmux_try("set-window-option", "-t", session, "pane-border-status", "top")
    tmux_try("set-window-option", "-t", session, "pane-border-format", " #{pane_title} ")
    tmux_try("set-option", "-t", session, "status-left", "[TRuffle]  ")
    consoles = any(t.console for t in targets)
    tmux_try("set-option", "-t", session, "status-right",
             " Ctrl-b d = back to TRuffle   Ctrl-b o = next pane   exit = leave one device "
             + ("  console: log out, then Ctrl-Q " if consoles else ""))
    tmux_try("set-option", "-t", session, "status-right-length", "120" if consoles else "80")
    return session, panes


class PaneSessions(object):
    """The tmux sessions THIS window opened, and what is in which pane."""

    def __init__(self):
        self.mine = []                 # session names, oldest first
        self.panes = {}                # session -> {pane id: (PaneTarget, ssh user)}
        self.foreign = False           # the only live sessions are not ours
        self.ended = []                # ours that ended, not yet reported (take_ended)
        self.checked_at = 0.0

    def add(self, session, panes, user):
        """panes: {pane id: PaneTarget}; user: the ssh user, or a function target -> user."""
        self.mine.append(session)
        user_for = user if callable(user) else (lambda target: user)
        self.panes[session] = dict((pane, (t, user_for(t))) for pane, t in panes.items())

    def consoles(self, sessions):
        """The console panes among these sessions: closing them leaves the switch consoles
        behind them logged in (D51), so Ctrl-K has to say so."""
        return [t.name for s in sessions for t, _ in self.panes.get(s, {}).values() if t.console]

    def refresh(self):
        """Ask tmux now.  Returns the sessions Ctrl-T / Ctrl-K act on: ours, else any TRuffle
        session (`foreign`).  Ours that ended wait in `ended`."""
        alive = set(truffle_sessions())
        self.ended += [s for s in self.mine if s not in alive]
        self.mine = [s for s in self.mine if s in alive]
        self.panes = dict((s, p) for s, p in self.panes.items() if s in self.mine)
        self.checked_at = time.time()
        self.foreign = not self.mine and bool(alive)
        return self.mine or sorted(alive)

    def take_ended(self):
        ended, self.ended = self.ended, []
        return ended

    def record(self, cfg, on):
        """Session log on/off for our running panes (D41).  Returns (panes changed, error or
        None, sessions it could not reach)."""
        self.refresh()
        changed, others = 0, [s for s in truffle_sessions() if s not in self.mine]
        for session in self.mine:
            ours = self.panes.get(session, {})
            try:
                listed = tmux_run("list-panes", "-s", "-t", "=" + session, "-F", "#{pane_id} #{pane_pipe}")
            except TMUX_ERRORS:
                continue
            for line in listed.splitlines():
                pane, _, piping = line.partition(" ")
                if pane not in ours or (piping == "1") == on:
                    continue                         # not ours, or already as wanted
                target, user = ours[pane]
                if on:
                    error = record_pane(cfg, pane, target.name, target.dev.host, user)
                else:
                    try:
                        tmux_run("pipe-pane", "-t", pane)        # no command: stop recording
                        error = None
                    except TMUX_ERRORS as e:
                        error = "cannot stop recording %s: %s" % (target.name, e)
                if error:
                    return changed, error, others
                changed += 1
        return changed, None, others

    def close(self, sessions):
        """Kill them - you closed them, so they are not reported as "ended"."""
        for session in sessions:
            tmux_try("kill-session", "-t", "=" + session)
        self.refresh()
        self.ended = [s for s in self.ended if s not in sessions]
