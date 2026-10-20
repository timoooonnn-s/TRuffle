"""The machine outside curses: the terminal's size, paste mode, one key, a TRuffle
note, the programs on PATH, and keeping the password out of core dumps."""

import fcntl
import functools
import os
import resource
import shutil
import struct
import sys
import termios
import tty

# Bracketed paste: the terminal wraps pasted text in ESC[200~ ... ESC[201~, so a pasted
# newline is text and not Enter (which would have run ssh on whatever row was selected).
PASTE_ON, PASTE_OFF = b"\033[?2004h", b"\033[?2004l"

# Symbols: Unicode when the terminal speaks UTF-8, plain ASCII otherwise (charset = auto).
# Only characters present in the common PuTTY/Windows fonts (Consolas, Courier New, DejaVu).
CHARSETS = {
    "unicode": {"hline": "─", "marker": "▌", "dot": "●", "prompt": "›", "up": "▲",
                "down": "▼", "sep": "·", "lr": "←→", "ud": "↑↓", "mask": "•",
                "box": "╭╮╰╯─│", "more": "…", "lt": "‹", "gt": "›",
                "track": "│", "thumb": "┃"},
    "ascii": {"hline": "-", "marker": ">", "dot": "*", "prompt": ">", "up": "^", "down": "v", "sep": "|",
              "lr": "<>", "ud": "Up/Dn", "mask": "*", "box": "++++-|", "more": "~", "lt": "<", "gt": ">",
              "track": "|", "thumb": "#"},
}


def terminal_size(fd=None):
    """(rows, cols) of the terminal on fd (default: stdout), or None."""
    fd = sys.stdout.fileno() if fd is None else fd
    try:
        rows, cols = struct.unpack("hhhh", fcntl.ioctl(fd, termios.TIOCGWINSZ, b"\0" * 8))[:2]
    except OSError:
        return None
    return (rows, cols) if rows > 0 and cols > 0 else None


def bracketed_paste(on):
    """Bracketed paste on/off (D28) - harmless where unsupported.  Off while ssh or tmux
    has the terminal."""
    try:
        os.write(sys.stdout.fileno(), PASTE_ON if on else PASTE_OFF)
    except OSError:
        pass


def write(text):
    os.write(sys.stdout.fileno(), text.encode("utf-8", "replace"))


def wait_key(prompt):
    """Print prompt, return one key (bytes), typeahead dropped.  Raw, so Ctrl-C is a key too
    - it used to quit TRuffle from a "Press any key"."""
    write(prompt)
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        termios.tcflush(fd, termios.TCIFLUSH)
        ch = os.read(fd, 1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    write("\r\n")
    return ch


class Notes(object):
    """'TRuffle > first line', further lines indented - how TRuffle talks while ssh or
    tmux has the terminal."""

    def __init__(self, colors=True, gt=">"):
        self.colors, self.gt = colors, gt

    def text(self, *lines):
        prefix = "\033[1;34mTRuffle\033[0m" if self.colors else "TRuffle"
        return "\r\n%s %s %s" % (prefix, self.gt, ("\r\n" + " " * 10).join(lines))

    def say(self, *lines):
        write(self.text(*lines))

    def ask(self, *lines):
        """Say it and wait for one key; returns the key (bytes)."""
        return wait_key(self.text(*lines))


@functools.lru_cache(maxsize=None)
def which(cmd):
    """Like shutil.which, also looking in /usr/sbin and /sbin (ping lives there on RHEL)."""
    path = os.environ.get("PATH", os.defpath) + os.pathsep + "/usr/sbin" + os.pathsep + "/sbin"
    return shutil.which(cmd, path=path)


def harden_process():
    """Keep the password out of core dumps and, on Linux, out of reach of other processes
    of the same user (PR_SET_DUMPABLE; macOS has none) - D21."""
    try:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    except (ValueError, OSError):
        pass
    if sys.platform.startswith("linux"):
        try:
            import ctypes
            libc = ctypes.CDLL(None, use_errno=True)
            libc.prctl(4, 0, 0, 0, 0)          # PR_SET_DUMPABLE = 4, value 0
        except (OSError, AttributeError):
            pass
