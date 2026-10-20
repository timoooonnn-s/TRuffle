"""The curses screen every view shares: the frame (top bar + footer), the status
message, dialog windows, the full-screen text viewer, and handing the terminal to ssh
or tmux and taking it back."""

import curses
import textwrap
import time

from .. import terminal
from .draw import fit, put, wrap_lines
from .keys import read_key
from .theme import Theme


class Screen(object):

    def __init__(self, scr, charset):
        self.scr = scr
        self.th = Theme(charset)
        self.msg, self.msg_error, self.msg_until = "", False, 0.0
        self.backdrop = lambda: None      # draws what a dialog window sits on (the main screen)

    @property
    def sym(self):
        return self.th.sym

    def set_charset(self, charset):
        self.th = Theme(charset)          # rebuilt: the symbols change at once

    def notes(self):
        """How TRuffle talks while ssh has the terminal, in this screen's symbols."""
        return terminal.Notes(bool(self.th.colors), self.sym["gt"])

    def message(self, text, error=False, seconds=6):
        self.msg, self.msg_error, self.msg_until = text, error, time.time() + seconds

    def set_cursor(self, visible):
        try:
            curses.curs_set(1 if visible else 0)
        except curses.error:
            pass

    def sync_size(self):
        """Redraw everything, at the size the terminal has NOW (Ctrl-L, a resize)."""
        size = terminal.terminal_size()
        if size and size != self.scr.getmaxyx():
            try:
                curses.resizeterm(*size)
            except curses.error:
                pass
        self.scr.clear()

    def read_key(self, timeout_ms):
        """A key, with a resize already applied (it still comes back as 'RESIZE')."""
        key = read_key(self.scr, timeout_ms)
        if key == "RESIZE":
            self.sync_size()
        return key

    # -- handing the terminal over ----------------------------------------------

    def leave(self):
        """Give the plain terminal to ssh or tmux: our paste mode goes with it."""
        terminal.bracketed_paste(False)
        curses.endwin()

    def resume(self):
        terminal.bracketed_paste(True)
        self.scr.keypad(True)
        curses.flushinp()
        self.sync_size()
        self.scr.refresh()
        self.set_cursor(False)

    # -- the frame --------------------------------------------------------------

    def draw_frame(self, subtitle, right="", right_attr=None, hints=(), footer_right="", footer_attr=None,
                   show_message=True):
        """Top bar + rule, footer rule + key hints or the message.  Shared by all screens."""
        scr, th, sym = self.scr, self.th, self.sym
        h, w = scr.getmaxyx()
        put(scr, 0, 2, "TRuffle", th.brand)
        put(scr, 0, 11, subtitle[:max(0, w - 14 - len(right))], th.brand_sub)
        if right:
            put(scr, 0, max(0, w - len(right) - 2), right, th.info if right_attr is None else right_attr)
        put(scr, 1, 0, sym["hline"] * w, th.rule)
        put(scr, h - 2, 0, sym["hline"] * w, th.rule)

        if footer_right:
            put(scr, h - 1, max(0, w - len(footer_right) - 2), footer_right,
                th.hint if footer_attr is None else footer_attr)
        room = w - (len(footer_right) + 4 if footer_right else 2)
        if show_message and time.time() < self.msg_until:
            text = sym["dot"] + " " + self.msg
            if len(text) > room:                  # a message beats the right-hand info
                room = w - 3
                put(scr, h - 1, 0, " " * (w - 1))
            put(scr, h - 1, 2, fit(text, room, sym["more"]).rstrip(), th.err if self.msg_error else th.msg)
            return
        x = 2
        for key, label in hints:
            if x + len(key) + len(label) + 1 > room:
                break
            put(scr, h - 1, x, key, th.key)
            put(scr, h - 1, x + len(key) + 1, label, th.hint)
            x += len(key) + len(label) + 3

    def draw_window(self, title, subtitle, bh, bw):
        """The backdrop slightly faded, then an empty framed window of bh x bw, centred,
        with the title in the top frame line.  Returns its top-left corner."""
        scr, th = self.scr, self.th
        tl, tr, bl, br, hl, vl = self.sym["box"]
        self.backdrop()
        h, w = scr.getmaxyx()
        for y in range(h):                       # fade what is behind the window
            try:
                scr.chgat(y, 0, w - 1 if y == h - 1 else -1, th.backdrop)
            except curses.error:
                pass
        y0, x0 = max(0, (h - bh) // 2), max(0, (w - bw) // 2)
        put(scr, y0, x0, tl + hl * (bw - 2) + tr, th.win_frame)
        for y in range(y0 + 1, y0 + bh - 1):
            put(scr, y, x0, vl + " " * (bw - 2) + vl, th.win_frame)
            put(scr, y, x0 + 1, " " * (bw - 2), th.win)
        put(scr, y0 + bh - 1, x0, bl + hl * (bw - 2) + br, th.win_frame)
        put(scr, y0, x0 + 2, " %s " % title, th.win_title)
        if subtitle:
            put(scr, y0, x0 + 4 + len(title), "%s %s " % (self.sym["sep"], subtitle), th.win_frame)
        return y0, x0

    def draw_keys(self, y, x, keys):
        """A row of key hints inside a window: [("Enter", "OK"), ("ESC", "cancel")]."""
        for key, label in keys:
            put(self.scr, y, x, key, self.th.win_key)
            put(self.scr, y, x + len(key) + 1, label, self.th.win_hint)
            x += len(key) + len(label) + 4

    # -- standard views -----------------------------------------------------------

    def confirm(self, title, question, detail=()):
        """A y/n window: y means yes, any other key no - a resize just redraws."""
        while True:
            width = min(72, max(40, self.scr.getmaxyx()[1] - 6))
            lines = list(textwrap.wrap(question, width - 6)) + [""] + list(detail)
            y0, x0 = self.draw_window(title, "", len(lines) + 4, width)
            for i, line in enumerate(lines):
                put(self.scr, y0 + 1 + i, x0 + 3, line[:width - 6], self.th.win_hint if i else self.th.win_label)
            put(self.scr, y0 + len(lines) + 2, x0 + 3, "y", self.th.win_key)
            put(self.scr, y0 + len(lines) + 2, x0 + 5, "yes      any other key: no", self.th.win_hint)
            self.scr.refresh()
            key = self.read_key(-1)
            if key != "RESIZE":
                return key in ("y", "Y")

    def show_text(self, title, lines=None, stream=None):
        """Full-screen viewer of lines (strings, or [(text, attr)] segments) or of a live
        ping.ProcStream, stopped on close."""
        scr, th, sym = self.scr, self.th, self.sym
        offset, follow = 0, stream is not None
        try:
            while True:
                h, w = scr.getmaxyx()
                rows = self._text_rows(stream.snapshot() if stream else lines, w - 5)
                body_h = max(1, h - 5)          # top bar, rule, blank ... rule, footer
                max_off = max(0, len(rows) - body_h)
                if follow:
                    offset = max_off
                offset = max(0, min(offset, max_off))

                scr.erase()
                right, right_attr = "", None
                if stream:
                    if not stream.done:
                        right, right_attr = sym["dot"] + " running", th.wait
                    elif stream.returncode == 0:
                        right, right_attr = sym["dot"] + " done", th.up
                    else:
                        right, right_attr = "%s exit %s" % (sym["dot"], stream.returncode), th.down
                position = ""
                if len(rows) > body_h:
                    position = "%d-%d / %d" % (offset + 1, min(len(rows), offset + body_h), len(rows))
                hints = [("ESC", "close"), (sym["ud"], "scroll"), ("PgUp PgDn", "page")]
                self.draw_frame("%s %s" % (sym["gt"], title), right, right_attr, hints, position,
                                show_message=False)
                for i, segments in enumerate(rows[offset:offset + body_h]):
                    x = 3
                    for text, attr in segments:
                        put(scr, 3 + i, x, text, attr)
                        x += len(text)
                scr.refresh()

                key = self.read_key(150)
                if key in ("ESC", "ENTER", "q", "Q"):
                    break
                if key == "UP":
                    offset, follow = offset - 1, False
                elif key == "DOWN":
                    offset += 1
                    follow = stream is not None and offset >= max_off
                elif key == "PGUP":
                    offset, follow = offset - body_h, False
                elif key in ("PGDN", " "):
                    offset += body_h
                    follow = stream is not None and offset >= max_off
                elif key == "HOME":
                    offset, follow = 0, False
                elif key == "END":
                    offset, follow = max_off, stream is not None
        finally:
            if stream:
                stream.stop()
            # full repaint: a laggy link left ping lines in the switch list (D37)
            self.scr.clear()

    def _text_rows(self, content, width):
        th, rows = self.th, []
        for line in content:
            if isinstance(line, list):
                rows.append(line)
                continue
            attr = th.info if line.startswith("$ ") else th.hint if line.startswith("[finished") else th.text
            rows += [[(part, attr)] for part in wrap_lines([line], width)]
        return rows
