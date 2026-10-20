"""Colours and attributes: every PALETTE name becomes a ready-to-use curses attribute."""

import curses

from ..results import PING_DOWN, PING_UP, SSH_FAILED, SSH_OK, WAIT
from ..terminal import CHARSETS

# name: ((fg, bg, flags) on 256-colour terminals, (fg, bg, flags) on 8-colour terminals)
# -1 = the terminal's own colour, so light and dark terminal themes both work.
# Flags: b = bold, d = dim, u = underline, r = reverse.
#
# Colours follow STYLE.md (TRuffle palette), as xterm-256 numbers:
#   Navy 18   Truffle Blue 25   Signal Blue 26   Steel 67   Sky 111   Mist 189   Highlight 214
# Light shades carry text on dark terminals, strong shades are used as backgrounds.
PALETTE = {
    "brand":       ((111, -1, "b"), ("cyan", -1, "b")),
    "brand_sub":   ((67, -1, ""),   (-1, -1, "")),
    "info":        ((67, -1, ""),   ("blue", -1, "b")),
    "rule":        ((25, -1, ""),   ("blue", -1, "")),
    "tab":         ((111, -1, ""),  ("cyan", -1, "")),
    "tab_active":  ((231, 25, "b"), ("white", "blue", "b")),
    "prompt":      ((111, -1, "b"), ("cyan", -1, "b")),
    "cursor":      ((231, 26, ""),  ("black", "cyan", "")),
    "placeholder": ((67, -1, ""),   (-1, -1, "d")),
    "head":        ((111, -1, "b"), ("cyan", -1, "b")),
    "sort":        ((189, -1, "b"), ("cyan", -1, "b")),
    "text":        ((-1, -1, ""),   (-1, -1, "")),
    "sel":         ((231, 25, "b"), ("white", "blue", "b")),
    "marker":      ((111, -1, "b"), ("cyan", -1, "b")),
    "up":          ((78, -1, "b"),  ("green", -1, "b")),
    "down":        ((203, -1, "b"), ("red", -1, "b")),
    "wait":        ((179, -1, ""),  ("yellow", -1, "")),
    "up_sel":      ((120, 25, "b"), ("green", "blue", "b")),
    "down_sel":    ((217, 25, "b"), ("red", "blue", "b")),
    "wait_sel":    ((223, 25, ""),  ("yellow", "blue", "")),
    "age":         ((67, -1, ""),   (-1, -1, "d")),       # "3h" after a result, and a stale result
    "age_sel":     ((189, 25, ""),  ("white", "blue", "")),
    "fav":         ((214, -1, "b"), ("yellow", -1, "b")),
    "mark":        ((120, -1, "b"), ("green", -1, "b")),
    "mark_sel":    ((120, 25, "b"), ("green", "blue", "b")),
    "fav_sel":     ((214, 25, "b"), ("yellow", "blue", "b")),
    "match":       ((111, -1, "bu"), ("cyan", -1, "bu")),
    "match_sel":   ((189, 25, "bu"), ("white", "blue", "bu")),
    "key":         ((111, -1, "b"), ("cyan", -1, "b")),
    "hint":        ((67, -1, ""),   ("blue", -1, "b")),
    "msg":         ((189, -1, ""),  ("cyan", -1, "")),
    "err":         ((203, -1, "b"), ("red", -1, "b")),
    # dialog windows: the screen behind fades a little, the window is a framed
    # mid-blue panel with pale-blue input fields
    "backdrop":    ((246, -1, ""),  ("blue", -1, "b")),
    "win":         ((189, 67, ""),  ("white", "blue", "")),
    "win_frame":   ((189, 67, ""),  ("cyan", "blue", "b")),
    "win_title":   ((231, 67, "b"), ("white", "blue", "b")),
    "win_hint":    ((189, 67, ""),  ("white", "blue", "")),
    "win_key":     ((231, 67, "b"), ("white", "blue", "b")),
    "win_label":   ((231, 67, "b"), ("white", "blue", "b")),
    "win_err":     ((224, 67, "b"), ("yellow", "blue", "b")),
    "field":       ((18, 189, ""),  ("black", "white", "")),
    "field_idle":  ((18, 111, ""),  ("black", "cyan", "")),
    "banner1":     ((25, -1, "b"),  ("blue", -1, "b")),
    "banner2":     ((26, -1, "b"),  ("blue", -1, "b")),
    "banner3":     ((67, -1, "b"),  ("cyan", -1, "")),
    "banner4":     ((111, -1, "b"), ("cyan", -1, "b")),
    "banner5":     ((189, -1, "b"), ("cyan", -1, "b")),
}
# Without colours: attributes only.
MONO = {
    "mark": "b", "mark_sel": "r", "match": "bu", "match_sel": "rbu", "fav": "b", "fav_sel": "r",
    "brand": "b", "info": "d", "tab_active": "r", "prompt": "b", "cursor": "r",
    "placeholder": "d", "head": "b", "sort": "b", "sel": "r", "marker": "b", "up": "b", "down": "b",
    "up_sel": "r", "down_sel": "r", "wait_sel": "r", "age": "d", "age_sel": "r", "key": "b", "hint": "d",
    "err": "b", "field": "r", "backdrop": "d", "win_title": "b", "win_label": "b", "win_key": "b",
    "win_err": "b", "field_idle": "u",
    "banner1": "b", "banner2": "b", "banner3": "b", "banner4": "b", "banner5": "b",
}
COLOR_NAMES = {"black": curses.COLOR_BLACK, "red": curses.COLOR_RED, "green": curses.COLOR_GREEN,
               "yellow": curses.COLOR_YELLOW, "blue": curses.COLOR_BLUE, "cyan": curses.COLOR_CYAN,
               "white": curses.COLOR_WHITE}
# The palette name a status word is drawn with ("_sel" is added on the selected row).
STATUS_STYLE = {PING_UP: "up", SSH_OK: "up", PING_DOWN: "down", SSH_FAILED: "down", WAIT: "wait"}
FLAGS = {"b": curses.A_BOLD, "d": curses.A_DIM, "u": curses.A_UNDERLINE, "r": curses.A_REVERSE}

BANNER = [
    r" _____  ____           __   __  _        ",
    r"|_   _||  _ \  _   _  / _| / _|| |  ___  ",
    r"  | |  | |_) || | | || |_ | |_ | | / _ \ ",
    r"  | |  |  _ < | |_| ||  _||  _|| ||  __/ ",
    r"  |_|  |_| \_\ \__,_||_|  |_|  |_| \___| ",
]


def attributes(flags):
    value = 0
    for f in flags:
        value |= FLAGS[f]
    return value


class Theme(object):
    """Every PALETTE name is an attribute holding a curses attribute (th.err, th.win_key).
    `sym` is the symbol set, `colors` 256, 8 or 0."""

    def __init__(self, charset):
        self.sym = CHARSETS[charset]
        self.colors = 0
        for name in PALETTE:
            setattr(self, name, attributes(MONO.get(name, "")))
        try:
            if curses.has_colors():
                self._init_colors()
        except curses.error:
            pass

    def _init_colors(self):
        try:
            curses.use_default_colors()
            default = -1
        except curses.error:
            default = None
        rich = curses.COLORS >= 256 and curses.COLOR_PAIRS > len(PALETTE)
        for number, (name, specs) in enumerate(PALETTE.items(), 1):
            fg, bg, flags = specs[0] if rich else specs[1]
            fg, bg = COLOR_NAMES.get(fg, fg), COLOR_NAMES.get(bg, bg)
            if default is None:
                fg = curses.COLOR_WHITE if fg == -1 else fg
                bg = curses.COLOR_BLACK if bg == -1 else bg
            curses.init_pair(number, fg, bg)
            setattr(self, name, curses.color_pair(number) | attributes(flags))
        self.colors = 256 if rich else 8

    def status(self, state, selected=False, stale=False):
        """The attribute of a status word."""
        return getattr(self, ("age" if stale else STATUS_STYLE.get(state, "wait")) + ("_sel" if selected else ""))
