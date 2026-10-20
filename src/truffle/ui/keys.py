"""Keyboard: curses keypad plus our own escape-sequence parser, so PuTTY's default
F-keys (ESC[11~), the Linux console and Tabby all work."""

import curses
import re

from ..inventory import CONTROL_CHARS

MAX_PASTE = 512
HUGE_PASTE = 1 << 20                  # hard stop: a terminal that never sends the end marker

CURSES_KEYS = {
    curses.KEY_UP: "UP", curses.KEY_DOWN: "DOWN", curses.KEY_LEFT: "LEFT", curses.KEY_RIGHT: "RIGHT",
    curses.KEY_PPAGE: "PGUP", curses.KEY_NPAGE: "PGDN", curses.KEY_HOME: "HOME", curses.KEY_END: "END",
    curses.KEY_FIND: "HOME", curses.KEY_SELECT: "END", curses.KEY_ENTER: "ENTER",
    curses.KEY_BACKSPACE: "BACKSPACE", curses.KEY_DC: "DELETE", curses.KEY_BTAB: "BTAB",
    curses.KEY_RESIZE: "RESIZE",
}
CURSES_KEYS.update((curses.KEY_F0 + n, "F%d" % n) for n in range(1, 13))

ESC_SEQUENCES = {
    "[A": "UP", "[B": "DOWN", "[C": "RIGHT", "[D": "LEFT",
    "OA": "UP", "OB": "DOWN", "OC": "RIGHT", "OD": "LEFT",
    "[H": "HOME", "[F": "END", "OH": "HOME", "OF": "END",
    "[1~": "HOME", "[7~": "HOME", "[4~": "END", "[8~": "END",
    "[5~": "PGUP", "[6~": "PGDN", "[3~": "DELETE", "[Z": "BTAB", "OM": "ENTER",
    "OP": "F1", "OQ": "F2", "OR": "F3", "OS": "F4",
    "[11~": "F1", "[12~": "F2", "[13~": "F3", "[14~": "F4", "[15~": "F5",
    "[17~": "F6", "[18~": "F7", "[19~": "F8", "[20~": "F9", "[21~": "F10",
    "[23~": "F11", "[24~": "F12",
    "[[A": "F1", "[[B": "F2", "[[C": "F3", "[[D": "F4", "[[E": "F5",
    "[200~": "PASTE_START", "[201~": "PASTE_END",
}


class Paste(str):
    """read_key's answer to a paste: equal to "PASTE", carrying the text (D44)."""

    def __new__(cls, text):
        key = str.__new__(cls, "PASTE")
        key.text = text
        return key

    def as_text(self, multiline=True):
        """The paste as field text: control characters dropped, line breaks become spaces
        (one-line fields take the first line only), capped at MAX_PASTE."""
        lines = [CONTROL_CHARS.sub("", line) for line in re.split(r"[\r\n]", self.text or "")]
        lines = [line for line in lines if line]
        if not multiline:
            return lines[0][:MAX_PASTE] if lines else ""
        return " ".join(lines)[:MAX_PASTE]


def parse_escape_sequence(seq):
    """Map the characters after ESC to a key name ('' -> 'ESC', unknown -> None)."""
    if seq == "":
        return "ESC"
    if seq in ESC_SEQUENCES:
        return ESC_SEQUENCES[seq]
    m = re.match(r"^\[(\d*)(?:;\d+)+([A-Za-z~])$", seq)    # with modifiers, e.g. ESC[1;5A
    if m:
        num, final = m.groups()
        return ESC_SEQUENCES.get("[%s~" % num if final == "~" else "[" + final)
    return None


def read_escape(win, timeout_ms):
    """Read the characters after an ESC and name the key ('' -> 'ESC', unknown -> None)."""
    seq = ""
    win.timeout(100)
    try:
        while len(seq) < 12:
            try:
                c = win.get_wch()
            except curses.error:
                break
            if isinstance(c, int) or (not seq and c not in "[O"):
                # not an escape sequence: a plain ESC, then another key - keep that key
                try:
                    if isinstance(c, int):
                        curses.ungetch(c)            # a key code such as KEY_UP
                    else:
                        curses.unget_wch(c)
                except (curses.error, OverflowError, ValueError):
                    pass
                break
            seq += c
            if len(seq) >= 2 and (c.isalpha() or c == "~") and seq != "[[":
                break
    finally:
        win.timeout(timeout_ms)
    return parse_escape_sequence(seq)


def read_paste(win, timeout_ms):
    """The text up to the ESC[201~ marker - text, never keys, so a pasted newline cannot
    run ssh.  Always drained to the end, even past what is kept (D29)."""
    out, seen = [], 0
    win.timeout(200)                     # the terminal sends a paste in one burst
    try:
        while seen < HUGE_PASTE:         # a terminal that never ends the paste cannot hang us
            try:
                c = win.get_wch()
            except curses.error:
                break                    # terminal stopped mid-paste: take what we have
            seen += 1
            if isinstance(c, int):
                continue
            if c == "\x1b":
                if read_escape(win, 200) == "PASTE_END":
                    break
                continue                 # any other sequence inside a paste is dropped
            if len(out) < MAX_PASTE * 2:     # keep draining past the cap, just stop collecting
                out.append(c)
    finally:
        win.timeout(timeout_ms)
    return "".join(out)


def read_key(win, timeout_ms):
    """A key name ('UP', 'F1', 'CTRL_R', 'RESIZE', ...), a printable character, a Paste, or
    None (timeout / unknown).  timeout_ms < 0 waits."""
    win.timeout(timeout_ms)
    try:
        ch = win.get_wch()
    except curses.error:
        return None
    if isinstance(ch, int):
        return CURSES_KEYS.get(ch)
    if ch == "\x1b":
        name = read_escape(win, timeout_ms)
        if name == "PASTE_START":
            return Paste(read_paste(win, timeout_ms))
        return name
    if ch in ("\n", "\r"):
        return "ENTER"
    if ch in ("\x7f", "\x08"):
        return "BACKSPACE"
    if ch == "\t":
        return "TAB"
    if ord(ch) < 32:
        return "CTRL_" + chr(ord(ch) + 64)
    return ch if ch.isprintable() else None
