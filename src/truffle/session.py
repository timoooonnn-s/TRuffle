"""The system ssh in a pseudo-terminal (D3): TRuffle types the password once, relays
every byte and reports what happened.  No curses, no switch list here."""

import codecs
import errno
import fcntl
import os
import pty
import re
import select
import signal
import sys
import termios
import time
import tty
import warnings

from .inventory import CONTROL_CHARS

PASSWORD_PROMPT = re.compile(r"password[^\r\n]*:\s*$", re.IGNORECASE)
OFFENDING_KEY = re.compile(r"Offending \S+ key in (.+):\d+\s*$", re.MULTILINE)
# A last line that means the session died, not a logout - asked only once it had started.
SSH_FAILURE = re.compile(r"Permission denied|Connection (timed out|refused|reset)|No route to host|"
                         r"Could not resolve|Name or service not known|Network is unreachable|"
                         r"Host key verification failed|no matching|Too many authentication failures|"
                         r"not responding|Broken pipe|cannot run", re.IGNORECASE)
ANSI_ESCAPES = re.compile(rb"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07|\x1b[()][0-9A-Za-z]|\x1b[=>78]|\r")
TICK = 0.2                     # the relay wakes at least this often (window size, console steps)


class EscapeStripper(object):
    """Strips escape sequences from output that arrives in pieces; a sequence cut in two
    is held back until its end arrives (D41)."""

    def __init__(self):
        self.pending = b""

    def feed(self, data):
        data, self.pending = self.pending + data, b""
        cut = data.rfind(b"\x1b")
        if cut >= 0 and len(data) - cut < 64 and not ANSI_ESCAPES.match(data, cut):
            data, self.pending = data[:cut], data[cut:]
        return ANSI_ESCAPES.sub(b"", data)

    def flush(self):
        rest, self.pending = self.pending, b""
        return ANSI_ESCAPES.sub(b"", rest)


def clean_output(text):
    """Terminal output as plain text lines (escape sequences and control characters removed)."""
    text = ANSI_ESCAPES.sub(b"", text.encode("utf-8", "replace")).decode("utf-8", "replace")
    return "\n".join(CONTROL_CHARS.sub(" ", line).rstrip() for line in text.split("\n"))


def last_line(text):
    return re.split(r"[\r\n]", text)[-1]


def is_password_prompt(line):
    """True for 'Password:' / "user@host's password:", never for key passphrases (D3)."""
    return PASSWORD_PROMPT.search(line) is not None and "passphrase" not in line.lower()


def build_ssh_argv(cfg, user, host, inject_password):
    # ssh uses the FIRST value it sees for an option: user options go first so they win.
    argv = list(cfg.ssh_command) + list(cfg.ssh_options)
    argv += ["-o", "StrictHostKeyChecking=accept-new",
             "-o", "ConnectTimeout=%d" % cfg.connect_timeout,
             "-o", "ServerAliveInterval=15",
             "-o", "ServerAliveCountMax=3"]
    if inject_password:
        # One try only: a wrong password must never be repeated (account lockout).
        argv += ["-o", "NumberOfPasswordPrompts=1"]
    if user:
        argv += ["-l", user]
    return argv + ["--", host]


class SessionResult(object):
    """What happened in one run_session."""

    def __init__(self):
        self.exit_code = None
        self.signal = None           # the signal that ended ssh, if one did
        self.started = False         # ssh got as far as an interactive session (see run_session)
        self.password_sent = False
        self.auth_failed = False
        self.hostkey_changed = False
        self.known_hosts = None      # file named in ssh's "Offending ... key in FILE:N"
        self.user_typed = False      # you typed something ...
        self.typed_before_start = False   # ... while ssh was still logging in
        self.prompt_seen = False     # a password prompt showed up before the session started
        self.last_line = ""
        self.wanted_password = False  # a password was stored for this attempt
        self.events = []             # what happened around the login, for --debug
        self.pre_login = ""          # output before your first keystroke (no secrets)
        self.console_closed = False  # console: you pressed Ctrl-Q
        self.switch_refused = False  # console: the switch behind the terminal server said no
        self.log_path = None         # the session log of this connection, if one was written

    @property
    def cancelled(self):
        """You stopped ssh (Ctrl-C, Ctrl-\\) before it was logged in."""
        return not self.started and self.signal in (signal.SIGINT, signal.SIGQUIT)

    @property
    def failed(self):
        """ssh did not get in, or the session died.  Exit 255 is also a normal logout on
        many switches (D9), so only a session that STARTED can be one (D45)."""
        if self.exit_code == 0 or self.console_closed:
            return False
        return not self.started or SSH_FAILURE.search(self.last_line) is not None

    @property
    def prompt_missed(self):
        """You had to type the stored password because no prompt was recognised - not when
        you typed first (D3), not when the connection failed."""
        return (self.wanted_password and not self.password_sent and not self.hostkey_changed
                and self.started and self.typed_before_start and not self.prompt_seen)


def _write_all(fd, data):
    while data:
        try:
            n = os.write(fd, data)
        except OSError as e:
            if e.errno == errno.EAGAIN:
                select.select([], [fd], [], 1.0)
                continue
            raise
        data = data[n:]


def _window_size(fd):
    try:
        return fcntl.ioctl(fd, termios.TIOCGWINSZ, b"\0" * 8)
    except OSError:
        return None


def raw_mode_visible():
    """Self-test for `truffle --check`: can TRuffle see from its side of a pty that the
    program on the other side switched to raw mode?  The SSH column depends on it."""
    master, slave = pty.openpty()
    try:
        before = _in_raw_mode(master)
        tty.setraw(slave)
        return not before and _in_raw_mode(master)
    except termios.error:
        return False
    finally:
        os.close(master)
        os.close(slave)


def _in_raw_mode(master):
    """Did ssh switch the pty to raw mode?  It does exactly when the session starts, never
    at a prompt.  Termios on the master acts on the slave (Linux and macOS, D45)."""
    try:
        return not termios.tcgetattr(master)[3] & termios.ICANON
    except termios.error:
        return False


FAILED_STATUS = 255 << 8          # what a child we lost track of counts as: exit code 255


def _exit_code(status):
    """The shell's view of a wait status: the exit code, or 128 + the signal."""
    if os.WIFEXITED(status):
        return os.WEXITSTATUS(status)
    if os.WIFSIGNALED(status):
        return 128 + os.WTERMSIG(status)
    return 255


def _reap(pid, grace=2.0):
    """Wait for the child; escalate to SIGTERM / SIGKILL if it does not go away.
    Returns its wait status."""
    for sig in (None, signal.SIGTERM, signal.SIGKILL):
        if sig is not None:
            try:
                os.kill(pid, sig)
            except OSError:
                pass
        deadline = time.time() + grace
        while time.time() < deadline:
            try:
                wpid, status = os.waitpid(pid, os.WNOHANG)
            except ChildProcessError:
                return FAILED_STATUS
            if wpid:
                return status
            time.sleep(0.05)
    return FAILED_STATUS


def _spawn(argv, winsize):
    """fork ssh onto a new pty; returns (pid, master)."""
    with warnings.catch_warnings():
        # fork() while batch-ping threads run warns on Python 3.12+; the child execs at
        # once, so it is safe - and the warning would only garble the screen.
        warnings.simplefilter("ignore", DeprecationWarning)
        pid, master = pty.fork()
    if pid == 0:   # child: becomes ssh
        try:
            signal.signal(signal.SIGPIPE, signal.SIG_DFL)
            if winsize:
                fcntl.ioctl(0, termios.TIOCSWINSZ, winsize)
            os.execvp(argv[0], argv)
        except BaseException as e:
            try:
                os.write(2, ("TRuffle: cannot run %s: %s\r\n" % (argv[0], e)).encode())
            except Exception:
                pass
        os._exit(127)
    return pid, master


def is_wrapper(argv):
    """ssh_command is not ssh itself but a program in front of it (`ct ssh`, D52)."""
    return os.path.basename(argv[0]) != "ssh"


def started_text(text):
    """Output that shows a relayed login got past ssh: a whole line that is neither a
    password prompt nor one of ssh's failures (D53)."""
    lines = clean_output(text).split("\n")[:-1]      # the last one is not complete yet
    return any(line.strip() and not is_password_prompt(line) and not SSH_FAILURE.search(line)
               for line in lines)


def run_session(argv, password=None, log=None, in_fd=None, out_fd=None, console=None):
    """Run argv (ssh) on a pty connected to our terminal and return a SessionResult.
    The password is typed once, at the first prompt, unless you typed first; a second
    prompt aborts (D3).  console: a ConsoleLogin for a terminal server; its EXIT_KEY ends
    the session.  The window size is polled, never via SIGWINCH - that would remove
    ncurses' own handler for good (D45).

    A wrapper that runs ssh on a terminal of its own (D53) switches ours to raw mode
    before ssh has even asked for the password.  Raw mode then says nothing: the session
    counts as started at the first line after the login that is not ssh's."""
    in_fd = sys.stdin.fileno() if in_fd is None else in_fd
    out_fd = sys.stdout.fileno() if out_fd is None else out_fd
    result = SessionResult()
    result.wanted_password = bool(password)
    if console is not None:
        console.events = result.events
        if not password:
            console.no_password()
    try:
        termios.tcflush(in_fd, termios.TCIFLUSH)    # drop typeahead, e.g. a double Enter
    except termios.error:
        pass
    winsize = _window_size(in_fd)
    pid, master = _spawn(argv, winsize)

    old_attrs = None
    try:
        old_attrs = termios.tcgetattr(in_fd)
        tty.setraw(in_fd)
    except termios.error:
        pass
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    strip = EscapeStripper()
    armed = bool(password)       # watching for the password prompt
    wrapper, relayed = is_wrapper(argv), False
    tail = captured = before_input = after_login = ""
    wait_status = None
    try:
        while True:
            ready = select.select([master, in_fd], [], [], TICK)[0]
            now, actions = time.time(), []
            size = _window_size(in_fd)
            if size and size != winsize:
                winsize = size
                try:
                    fcntl.ioctl(master, termios.TIOCSWINSZ, size)
                except OSError:
                    pass
            if not result.started and not relayed and _in_raw_mode(master):
                if wrapper and armed and not result.prompt_seen:
                    relayed = True
                    result.events.append("%s switched the terminal to raw mode before any password "
                                         "prompt -> it relays ssh, session start taken from the output"
                                         % os.path.basename(argv[0]))
                else:
                    result.started = True
                    result.events.append("ssh switched the terminal to raw mode -> session started")
            if master in ready:
                try:
                    data = os.read(master, 65536)
                except OSError as e:
                    if e.errno in (errno.EIO, errno.EBADF):
                        break          # Linux: slave side closed, ssh is gone
                    raise
                if not data:
                    break
                _write_all(out_fd, data)
                if log is not None:
                    try:
                        log.write(strip.feed(data))
                        log.flush()
                    except OSError:
                        log = None
                text = decoder.decode(data)
                captured = (captured + text)[-16384:]
                if not result.user_typed:
                    before_input = (before_input + text)[-16384:]
                # Prompts are ssh's only until the session starts: a banner ending in
                # "password:" must not abort it.  The switch's own are ConsoleLogin's.
                if relayed and not result.started and (result.password_sent or not armed):
                    # Not before the password went in: until then it is ssh's banner.  Before
                    # the prompt check: the switch's banner may end in "password:" (D45).
                    after_login = (after_login + text)[-4096:]
                    if started_text(after_login):
                        result.started = True
                        result.events.append("a line after the login that is not ssh's -> session started")
                if not result.started:
                    tail = (tail + text)[-1024:]
                    prompt = last_line(tail)
                    if is_password_prompt(prompt):
                        tail = ""
                        result.prompt_seen = True
                        result.events.append("password prompt seen: %r" % prompt.strip())
                        if armed and result.password_sent:
                            result.events.append("second password prompt -> wrong password, ssh stopped")
                            result.auth_failed = True
                            armed = False
                            try:
                                os.kill(pid, signal.SIGTERM)
                            except OSError:
                                pass
                        elif armed:
                            _write_all(master, password.encode("utf-8") + b"\r")
                            result.password_sent = True
                            result.events.append("password typed (once)")
                            if console is not None:
                                console.password_sent(now)
                                text = ""            # the prompt is the terminal server's, not the switch's
                if console is not None:
                    actions += console.output(text, now)
            if in_fd in ready:
                try:
                    data = os.read(in_fd, 4096)
                except OSError:
                    data = b""
                if not data:           # our own terminal is gone
                    break
                if console is not None and console.EXIT_KEY in data:
                    before = data[:data.index(console.EXIT_KEY)]
                    if before:
                        try:
                            _write_all(master, before)
                        except OSError:
                            pass
                    result.console_closed = True
                    result.events.append("%s -> session closed" % console.EXIT_NAME)
                    try:
                        os.kill(pid, signal.SIGTERM)
                    except OSError:
                        pass
                    break
                if console is not None:
                    console.typed()
                if armed:
                    result.events.append("you typed -> TRuffle stops watching for prompts" if result.password_sent
                                         else "you typed before any password prompt -> TRuffle will not type it")
                armed = False          # the user took over: never type the password again
                result.user_typed = True
                result.typed_before_start = result.typed_before_start or not result.started
                try:
                    _write_all(master, data)
                except OSError:
                    pass
            if console is not None:
                actions += console.tick(now)
                for kind, payload in actions:
                    try:
                        if kind == "send":
                            _write_all(master, payload)
                        else:
                            _write_all(out_fd, payload.encode("utf-8", "replace"))
                    except OSError:
                        pass
            if not ready:
                # ssh may have exited while something else keeps the pty open (ControlPersist).
                try:
                    wpid, status = os.waitpid(pid, os.WNOHANG)
                except ChildProcessError:
                    wpid, status = pid, FAILED_STATUS
                if wpid:
                    wait_status = status
                    break
    finally:
        if log is not None:
            try:
                log.write(strip.flush())
            except OSError:
                pass
        if old_attrs is not None:
            termios.tcsetattr(in_fd, termios.TCSADRAIN, old_attrs)
        if wait_status is None:
            wait_status = _reap(pid)
        os.close(master)

    result.exit_code = _exit_code(wait_status)
    result.signal = os.WTERMSIG(wait_status) if os.WIFSIGNALED(wait_status) else None
    if console is not None:
        result.switch_refused = console.refused
    if (result.password_sent and not result.started and result.exit_code == 255
            and "Permission denied" in before_input):
        result.auth_failed = True
    result.hostkey_changed = "REMOTE HOST IDENTIFICATION HAS CHANGED" in before_input
    m = OFFENDING_KEY.search(before_input.replace("\r", ""))
    if m:
        result.known_hosts = m.group(1).strip()
    result.last_line = clean_output(captured).strip().split("\n")[-1].strip()
    result.pre_login = clean_output(before_input)
    return result
