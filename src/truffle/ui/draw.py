"""Small drawing helpers: text that never raises, fits its cell, and the PING / SSH cell."""

import curses

from ..results import STALE_SECONDS, WAIT


def put(win, y, x, text, attr=0):
    """addstr that never raises: clips at the screen edge, survives odd locales."""
    h, w = win.getmaxyx()
    if y < 0 or y >= h or x < 0 or x >= w:
        return
    text = text[:w - x]
    if y == h - 1 and x + len(text) >= w:
        text = text[:w - x - 1]      # writing the bottom-right cell raises in curses
    if not text:
        return
    try:
        win.addstr(y, x, text, attr)
    except (curses.error, UnicodeError, ValueError):
        try:
            win.addstr(y, x, text.encode("ascii", "replace").decode("ascii"), attr)
        except (curses.error, ValueError):
            pass


def fit(text, width, more="~"):
    """text padded or cut to exactly width, a cut marked with `more`."""
    if width <= 0:
        return ""
    if len(text) <= width:
        return text.ljust(width)
    return text[:width - 1] + more


def fit_widths(widths, available, minimum=6):
    """Shrink the widest columns first until they fit (never below minimum)."""
    widths = list(widths)
    while sum(widths) > available and max(widths) > minimum:
        i = widths.index(max(widths))
        widths[i] -= 1
    return widths


def wrap_lines(lines, width):
    """Hard-wrap lines at width (a terminal does not break at words either)."""
    out = []
    width = max(10, width)
    for line in lines:
        line = line.expandtabs(8)
        if not line:
            out.append("")
        while line:
            out.append(line[:width])
            line = line[width:]
    return out


def age_text(seconds):
    """'now', '12m', '5h', '3d': how old a ping / ssh result is, short enough for its cell.
    Hours up to two days, because "26h" is still "since yesterday morning"."""
    if seconds < 60:
        return "now"
    if seconds < 3600:
        return "%dm" % (seconds // 60)
    if seconds < 48 * 3600:
        return "%dh" % (seconds // 3600)
    return "%dd" % (seconds // 86400)


def status_cell(state, checked, now, width, dot):
    """(word, age, stale) for one PING / SSH cell.  The age is left out when the column
    is too narrow for it, and a running ping ("wait") has none."""
    word = "%s %s" % (dot, state)
    if not checked or state == WAIT:
        return word, "", False
    age = age_text(max(0, now - checked))
    if len(word) + 1 + len(age) > width:
        age = ""
    return word, age, now - checked >= STALE_SECONDS
