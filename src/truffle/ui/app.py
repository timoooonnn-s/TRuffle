"""The main screen: the switch list, its keys, and the commands of the command bar.

 TRuffle  Device Manager                          timmy · 2/29 devices    top bar
───────────────────────────────────────────────────────────────────────  rule
  ssh   ping   details   help   exit                                      commands
  ›  ber core                                                              search
   NAME          IP           ...                        PING     SSH     table head
   ─────────────────────────────────────────────────────────────────      rule
 ▌+ ber-core-01  192.0.2.1    ...                        ● up 5m  ● ok 2h rows
───────────────────────────────────────────────────────────────────────  rule
 ESC clear search  Enter run  ←→ command  Tab mark  ^A all  F1-F7 sort   footer
"""

import os
import re
import time

from .. import CREDIT
from ..credentials import Credentials
from ..inventory import valid_host
from ..logs import logs_since, prune_logs
from ..ping import PING_ENV, BatchPing, ProcStream, ping_argv, stream_verdict
from ..console import is_console_server
from ..export import export_csv, export_path
from ..results import KINDS, STATUS_COLUMNS
from ..search import field_hint, known_field
from ..state import UserState
from ..terminal import which
from ..tmux import PaneSessions
from .actions import Actions
from .dialogs import settings_window
from .draw import fit, fit_widths, put, status_cell
from .pages import COMMANDS, details_lines, help_lines, log_lines
from .screen import Screen
from .switchlist import SwitchList

TABLE_X = 4          # column 1: selection marker, 2: the + of a marked device
KEY_BATCH = 30       # queued keys handled per screen update (see run)
SCREEN_POLL_MS = 250

PING_CONFIRM = 200    # pinging more devices than this at once asks first (D50)

# Ctrl-G: what you may want to flip mid-day - (key, label, Config attribute).  tmux and the
# screen symbols are set in truffle.conf only (D50: nobody switched them for an hour).
TOGGLES = [("l", "Session log", "session_log"),
           ("d", "Debug log", "debug")]


class App(object):

    def __init__(self, scr, cfg):
        self.cfg = cfg
        self.screen = Screen(scr, cfg.charset)
        self.screen.backdrop = lambda: self.draw(refresh=False)
        self.store = UserState(cfg.state_dir)
        self.results = self.store.load_results()          # the last check's results
        self.creds = Credentials(cfg.password_lifetime)
        self.panes = PaneSessions()
        self.list = SwitchList(cfg, self.store, self.results)
        self.actions = Actions(cfg, self.screen, self.list, self.store, self.results, self.creds, self.panes)
        self.batch = None
        self.cmd = 0                   # the selected command
        self.top = 0                   # first row on screen
        self.body_h = 1                # rows the table has room for
        self.screen.set_cursor(False)
        self.screen.resume()           # bracketed paste on
        self.load()
        pruned, prune_error = prune_logs(cfg)
        if self.store.error or prune_error:
            self.message(self.store.error or prune_error, error=True, seconds=15)
        elif pruned and not self.list.load_error and not self.list.issues:
            self.message("Deleted %d session log%s older than %d days (log_keep_days in truffle.conf)"
                         % (pruned, "" if pruned == 1 else "s", cfg.log_keep_days), seconds=10)
        elif self.results.checked and not self.list.load_error and not self.list.issues:
            self.message("Ping / SSH results from the last check (%s) - ping refreshes them"
                         % time.strftime("%Y-%m-%d %H:%M", time.localtime(self.results.newest())), seconds=8)

    def message(self, *args, **kw):
        self.screen.message(*args, **kw)

    def load(self):
        warns = self.list.load()
        if self.list.load_error:
            self.message(self.list.load_error, error=True, seconds=30)
        elif warns:
            self.message("; ".join(warns), error=True, seconds=15)
        elif self.list.issues:
            n = len(self.list.issues)
            self.message("%d warning%s in the device list - run: truffle --check" % (n, "" if n == 1 else "s"),
                         error=True, seconds=15)

    def save_results(self):
        self.store.save_results(self.results)
        if self.store.error:
            self.message(self.store.error, error=True, seconds=10)

    # -- drawing --------------------------------------------------------------------

    def layout(self):
        h, w = self.screen.scr.getmaxyx()
        gap = 2 if h >= 22 else 1         # blank rows between the blocks when there is room
        y_tabs = 1 + gap
        y_search = y_tabs + gap
        return h, w, y_tabs, y_search, y_search + gap

    def draw(self, refresh=True):
        scr, th = self.screen.scr, self.screen.th
        scr.erase()
        h, w, y_tabs, y_search, y_head = self.layout()
        if h < 10 or w < 40:
            put(scr, 0, 1, "TRuffle", th.brand)
            put(scr, 1, 1, "Terminal too small", th.err)
            put(scr, 2, 1, "min. 40 x 10", th.hint)
        else:
            self.draw_frame()
            self.draw_commands(y_tabs, w)
            self.draw_search(y_search, w)
            self.draw_table(y_head, h, w)
        if refresh:
            scr.refresh()

    def draw_frame(self):
        th, sym, lst = self.screen.th, self.screen.sym, self.list
        right = "%d/%d devices" % (len(lst.view), len(lst.devices))
        if self.creds.own:
            right = "%s %s %s" % (self.creds.own.user, sym["sep"], right)
        if self.creds.local:
            right = "local: %s %s %s" % (self.creds.local.user, sym["sep"], right)
        if self.creds.server:
            right = "ts local: %s %s %s" % (self.creds.server.user, sym["sep"], right)
        if lst.marked:
            right = "%d marked %s %s" % (len(lst.marked), sym["sep"], right)
        if self.panes.mine:
            right = "%d tmux %s %s" % (len(self.panes.mine), sym["sep"], right)
        hints = [("Enter", "run"), (sym["lr"], "command"), ("Tab", "mark"), ("^A", "all"), ("^E", "export"),
                 ("^G", "settings"), ("F1-F%d" % lst.ncols(), "sort"), ("^C", "quit")]
        if self.panes.mine:
            hints[3:3] = [("^T", "back to tmux"), ("^K", "close tmux")]
        esc = self.escape_step()
        if esc:                    # what the next ESC does - it depends on what is set (D50)
            hints.insert(0, ("ESC", esc[1]))
        if self.ping_running():
            footer, attr = "ping %d%%" % self.batch.percent, th.wait
        else:
            # the credit only where it costs no key hint
            room = self.screen.scr.getmaxyx()[1] - 2 - sum(len(k) + len(t) + 3 for k, t in hints)
            footer, attr = (CREDIT if room >= len(CREDIT) + 2 else ""), th.placeholder
        self.screen.draw_frame("Device Manager", right, hints=hints, footer_right=footer, footer_attr=attr)

    def draw_commands(self, y, w):
        scr, th, sym = self.screen.scr, self.screen.th, self.screen.sym
        if 2 + sum(len(c) + 3 for c in COMMANDS) <= w:
            x = 2
            for i, name in enumerate(COMMANDS):
                put(scr, y, x, " %s " % name, th.tab_active if i == self.cmd else th.tab)
                x += len(name) + 3
        else:                                       # narrow terminal: only the selected command
            name = COMMANDS[self.cmd]
            put(scr, y, 2, sym["lt"], th.tab)
            put(scr, y, 4, " %s " % name, th.tab_active)
            put(scr, y, 7 + len(name), sym["gt"], th.tab)

    def draw_search(self, y, w):
        """The search line: "-" and "field:" parts of terms are highlighted."""
        scr, th, sym, query = self.screen.scr, self.screen.th, self.screen.sym, self.list.query
        put(scr, y, 2, sym["prompt"], th.prompt)
        x = 5
        for part in re.split(r"(\s+)", query[-(w - 9):]):
            neg = part[:1] if len(part) > 1 and part[0] in "-'" else ""
            body = part[len(neg):]
            name, sep, value = body.partition(":")
            neg_attr = th.err if neg == "-" else th.key
            if known_field(body.lower(), self.list.fields):
                pieces = [(neg, neg_attr), (name + sep, th.key), (value, th.text)]
            else:
                pieces = [(neg, neg_attr), (body, th.text)]
            for text, attr in pieces:
                put(scr, y, x, text, attr)
                x += len(text)
        put(scr, y, x, " ", th.cursor)
        if not query:
            put(scr, y, 7, "type to search %s bc01  *-w4  w3|w4  type:core  ping:down  -test" % sym["sep"],
                th.placeholder)

    def draw_table(self, y_head, h, w):
        scr, th, sym, lst = self.screen.scr, self.screen.th, self.screen.sym, self.list
        widths = fit_widths(lst.widths, w - TABLE_X - 3 - 2 * (len(lst.widths) - 1))
        labels = [label for _, label in lst.columns] + [label for label, _, _ in STATUS_COLUMNS]
        x = TABLE_X
        for i, label in enumerate(labels):
            label = label.upper()
            put(scr, y_head, x, fit(label, widths[i], sym["more"]), th.head)
            if i == lst.sort_col and len(label) + 2 <= widths[i]:
                put(scr, y_head, x + len(label) + 1, sym["down"] if lst.sort_desc else sym["up"], th.sort)
            x += widths[i] + 2
        put(scr, y_head + 1, TABLE_X, sym["hline"] * (sum(widths) + 2 * (len(widths) - 1)), th.rule)

        y_body = y_head + 2
        self.body_h = body_h = max(1, h - 2 - y_body)
        self.scroll_to_cursor()
        if not lst.view:
            if lst.load_error:
                text, attr = lst.load_error, th.err
            elif lst.devices:
                hint = field_hint(lst.query, lst.fields)
                text, attr = "No device matches '%s'  %s  %s" % (
                    lst.query, sym["sep"], "%s is a column - did you mean  %s ?" % (hint.partition(":")[0], hint)
                    if hint else "ESC clears the search"), th.placeholder
            else:
                text, attr = "The device list is empty", th.placeholder
            put(scr, y_body + 1, TABLE_X, text, attr)
        now = time.time()
        for row, d in enumerate(lst.view[self.top:self.top + body_h]):
            self.draw_row(y_body + row, w, d, widths, self.top + row == lst.cursor, now)
        if len(lst.view) > body_h:
            self.draw_scrollbar(y_body, body_h, w)

    def scroll_to_cursor(self):
        lst, body_h = self.list, self.body_h
        if lst.cursor < self.top:
            self.top = lst.cursor
        elif lst.cursor >= self.top + body_h:
            self.top = lst.cursor - body_h + 1
        self.top = max(0, min(self.top, len(lst.view) - body_h))

    def draw_row(self, y, w, d, widths, sel, now):
        scr, th, sym = self.screen.scr, self.screen.th, self.screen.sym
        if sel:
            put(scr, y, 1, sym["marker"], th.marker)
            put(scr, y, 2, " " * (w - 4), th.sel)
        if d.key in self.list.marked:
            put(scr, y, 2, "+", th.mark_sel if sel else th.mark)
        x = TABLE_X
        marks = self.list.found.get(d, (0, {}))[1]
        for i, value in enumerate(d.cells):
            put(scr, y, x, fit(value, widths[i], sym["more"]), th.sel if sel else th.text)
            visible = len(value) if len(value) <= widths[i] else widths[i] - 1
            if len(d.lcells[i]) != len(value):     # lower() changed the length: positions unreliable
                visible = 0
            for pos in marks.get(i, ()):           # letters that matched the search
                if pos < visible:
                    put(scr, y, x + pos, value[pos], th.match_sel if sel else th.match)
            x += widths[i] + 2
        for k, kind in enumerate(KINDS):
            state = self.results.get(kind, d.host)
            width = widths[len(d.cells) + k]
            if state:
                word, age, stale = status_cell(state, self.results.taken(kind, d.host), now, width, sym["dot"])
                put(scr, y, x, fit(word, width), th.status(state, sel, stale))
                if age:
                    put(scr, y, x + len(word) + 1, age, th.age_sel if sel else th.age)
            x += width + 2

    def draw_scrollbar(self, y_body, body_h, w):
        scr, th, sym, n = self.screen.scr, self.screen.th, self.screen.sym, len(self.list.view)
        thumb = max(1, body_h * body_h // n)
        pos = self.top * (body_h - thumb) // max(1, n - body_h)
        for row in range(body_h):
            inside = pos <= row < pos + thumb
            put(scr, y_body + row, w - 1, sym["thumb"] if inside else sym["track"], th.marker if inside else th.rule)

    # -- main loop ----------------------------------------------------------------------

    def run(self):
        try:
            while self.step():
                pass
        except KeyboardInterrupt:
            pass                                      # Ctrl-C: still save what we have
        finally:
            # also on a hang-up or SIGTERM (SystemExit, see cli.run_ui): finished pings
            # of a batch are not thrown away
            if self.batch:
                self.batch.cancel()
                self.save_results()

    def step(self):
        """One screen update; keys already waiting are handled before the next draw, up
        to KEY_BATCH (D43: a held arrow key over ssh).  False = quit."""
        self.background()
        self.draw()
        timeout = SCREEN_POLL_MS
        for _ in range(KEY_BATCH):
            key = self.screen.read_key(timeout)
            if key is None:
                break
            if self.handle(key) is False:
                return False
            timeout = 0
        return True

    def background(self):
        """What moves on by itself: held logins, tmux sessions, a finished ping."""
        self.actions.check_sessions()
        self.actions.check_password_lifetime()
        if self.batch and not self.batch.running and not self.batch.reported:
            self.batch.reported = True
            if not self.batch.cancelled:
                self.message("Ping done: %s" % self.batch.summary(), seconds=20)
            self.save_results()
            self.list.status_changed()

    def ping_running(self):
        return self.batch is not None and self.batch.running and not self.batch.cancelled

    # -- keys ---------------------------------------------------------------------------

    def handle(self, key):
        """One key on the main screen.  Returns False to quit."""
        lst = self.list
        moves = {"UP": -1, "DOWN": 1, "PGUP": -self.body_h, "PGDN": self.body_h}
        if key == "PASTE":
            # Pasted text is text: no Enter runs a command, no Tab marks a switch.
            if key.as_text():
                lst.set_query(lst.query + key.as_text())
        elif key in moves:
            lst.move(moves[key])
        elif key == "HOME":
            lst.move_to(0)
        elif key == "END":
            lst.move_to(len(lst.view) - 1)
        elif key in ("LEFT", "RIGHT"):
            self.cmd = (self.cmd + (1 if key == "RIGHT" else -1)) % len(COMMANDS)
        elif key == "ENTER":
            return self.execute()
        elif key in ("TAB", "BTAB"):
            self.mark(key)
        elif key.startswith("F") and key[1:].isdigit():
            if lst.set_sort(int(key[1:]) - 1) and lst.sort_col is None:
                self.message("Original order")
        elif key == "BACKSPACE":
            if lst.query:
                lst.set_query(lst.query[:-1])
        elif key == "CTRL_U":
            lst.set_query("")
        elif key == "CTRL_W":
            words = lst.query.split()
            lst.set_query(" ".join(words[:-1]) + (" " if len(words) > 1 else ""))
        elif key == "ESC":
            self.escape()
        elif key == "CTRL_A":
            self.mark_all()
        elif key == "CTRL_E":
            self.export()
        elif key == "CTRL_T":
            self.actions.reattach()
        elif key == "CTRL_K":
            self.actions.close_sessions()
        elif key == "CTRL_G":
            self.settings()
        elif key == "CTRL_R":
            self.load()
            if not lst.load_error:
                self.message("Device list reloaded: %d devices" % len(lst.devices))
        elif key == "CTRL_L":
            self.screen.sync_size()
        elif len(key) == 1:
            lst.set_query(lst.query + key)
        return True

    def mark(self, key):
        """Tab marks and moves down, Shift-Tab moves up and marks."""
        lst = self.list
        if key == "BTAB":
            lst.move(-1)
        dev = lst.selected()
        if dev is None:
            return
        at = lst.cursor
        lst.toggle_mark(dev)
        if "is:marked" in lst.query.lower():
            # the list IS the marks: an unmarked row leaves it, the next slides up (D29)
            lst.refilter()
            lst.move_to(at)
        elif key == "TAB":
            lst.move(1)

    def escape_step(self):
        """What the next ESC does, as (step, footer text), or None: search, running ping,
        marks, sort - one step per ESC.  The ping comes before the marks: a ping needs 2+
        marks, so they are ALWAYS set while one runs, and clearing them first made the
        footer's "ESC cancels" a lie."""
        lst = self.list
        if lst.query:
            return "search", "clear search"
        if self.ping_running():
            return "ping", "cancel ping"
        if lst.marked:
            return "marks", "clear %d mark%s" % (len(lst.marked), "" if len(lst.marked) == 1 else "s")
        if lst.sort_col is not None:
            return "sort", "clear sort"
        return None

    def escape(self):
        step = self.escape_step()
        lst = self.list
        if step is None:
            return
        if step[0] == "search":
            lst.set_query("")
        elif step[0] == "ping":
            self.batch.cancel()
            self.message("Ping cancelled")
        elif step[0] == "marks":
            lst.marked.clear()
            self.message("Marks cleared")
        else:
            lst.set_sort(None, desc=False)
            self.message("Original order")

    def mark_all(self):
        """Ctrl-A: mark every device in the current view - or, when they all are marked
        already, unmark them (D50: the sweep was done by holding Tab).  Marks elsewhere stay."""
        lst = self.list
        if not lst.view:
            self.message("Nothing to mark - the search shows no device")
            return
        if all(d.key in lst.marked for d in lst.view):
            for d in lst.view:
                lst.marked.pop(d.key, None)
            self.message("Unmarked the %d devices of this view - %d still marked" % (len(lst.view), len(lst.marked)))
        else:
            for d in lst.view:
                lst.marked.setdefault(d.key, True)
            self.message("Marked the %d devices of this view - %d marked, ESC clears them"
                         % (len(lst.view), len(lst.marked)))
        if "is:marked" in lst.query.lower():
            lst.refilter()

    def export(self):
        """Ctrl-E: the devices in the current view, with their results, as a CSV in your
        home folder (D50)."""
        lst = self.list
        if not lst.view:
            self.message("Nothing to export - the search shows no device")
            return
        try:
            path = export_csv(export_path(), lst.view, lst.headers, lst.delimiter, self.results)
        except OSError as e:
            self.message("cannot write the export: %s" % (e.strerror or e), error=True, seconds=12)
            return
        home = os.path.expanduser("~")
        shown = "~" + path[len(home):] if path.startswith(home + os.sep) else path
        self.message("Exported %d devices to %s" % (len(lst.view), shown), seconds=15)

    # -- commands -----------------------------------------------------------------------

    def execute(self):
        command = COMMANDS[self.cmd]
        if command == "exit":
            return False
        if command == "help":
            self.screen.show_text("help", lines=help_lines(self.screen.th, self.cfg, self.list.ncols(),
                                                           len(self.list.devices)))
            return True
        if command in ("ssh", "ping") and self.run_on_marks(command):
            return True
        dev = self.list.selected()
        if dev is None:
            self.message("No device selected", error=True)
        elif command == "details":
            self.show_details(dev)
        elif not valid_host(dev.host):
            self.message("'%s' has no usable IP/host ('%s')" % (dev.name, dev.host), error=True)
        elif command == "ping":
            self.ping(dev)
        elif is_console_server(self.cfg, dev):
            self.actions.console(dev)
        else:
            self.actions.ssh(dev)
        return True

    def run_on_marks(self, command):
        """With 2+ usable marks ssh / ping act on them, whatever is selected (D38).  False =
        the selected row is meant."""
        marked = [d for d in self.list.marked_devices() if valid_host(d.host)]
        if len(marked) < 2:
            return False
        if command == "ping":
            self.start_batch(marked)
            return True
        servers = [d for d in marked if is_console_server(self.cfg, d)]
        if servers:           # terminal servers among the marks: ask their lines (D51)
            opened = self.actions.with_consoles(servers, [d for d in marked if d not in servers])
        else:
            opened = self.actions.many(marked)
        if opened:
            self.list.marked.clear()
        return True

    def ping(self, dev):
        stream = ProcStream(ping_argv(dev.host, 4, max(2, self.cfg.ping_timeout)), env=PING_ENV)
        try:
            self.screen.show_text("ping %s (%s)" % (dev.name, dev.host), stream=stream)
        finally:
            # also when TRuffle is closed with the ping still on screen (D48): the
            # replies that came are a verdict, and it is saved before TRuffle goes
            self.record_ping(dev, stream)

    def record_ping(self, dev, stream):
        verdict = stream_verdict(stream)
        if verdict is None:
            if stream.done and not stream.killed:     # cancelled early proves nothing and says nothing
                self.message("ping could not check %s (exit %s) - the PING column is unchanged"
                             % (dev.name, stream.returncode), error=True, seconds=10)
            return
        self.results.set("ping", dev.host, verdict, time.time())
        self.save_results()
        self.list.status_changed(dev)

    def start_batch(self, devices):
        """ping the marked switches at once, into the PING column (D35)."""
        if self.ping_running():
            self.message("A ping is already running (ESC cancels it once the search is empty)")
            return
        if not which("ping"):
            self.message("'ping' is not installed", error=True)
            return
        hosts = list(dict.fromkeys(d.host for d in devices))     # each address once, in order
        if len(hosts) > PING_CONFIRM and not self.screen.confirm(
                "Ping", "Ping %d devices at once?" % len(hosts),
                ("About %d s with %d at a time. ESC with an empty search cancels it."
                 % (len(hosts) // BatchPing.MAX_THREADS * (self.cfg.ping_timeout + 1) + 1, BatchPing.MAX_THREADS),)):
            self.message("Ping not started - %d devices stay marked" % len(devices))
            return
        self.batch = BatchPing(hosts, self.cfg.ping_timeout, self.results)
        self.message("Pinging %d marked devices - ESC cancels" % len(hosts))

    def show_details(self, dev):
        lines = details_lines(self.screen.th, dev, self.results, self.store.recent.get(dev.key),
                              self.screen.scr.getmaxyx()[1])
        self.screen.show_text("details %s %s" % (self.screen.sym["sep"], dev.name), lines=lines)

    def show_logs(self):
        files = logs_since(self.cfg, self.cfg.started)
        self.screen.show_text("log files", lines=log_lines(self.screen.th, self.cfg, files))

    # -- settings -----------------------------------------------------------------------

    def settings(self):
        """Ctrl-G: settings for this session only - never written back to truffle.conf.
        Not Ctrl-O: the tty driver eats ^O (VDISCARD) before curses sees it (D29)."""
        while True:
            key = settings_window(self.screen, self.settings_rows())
            if key in ("ESC", "ENTER", "q", "Q", "CTRL_G"):
                return
            option = next((option for k, _, option in TOGGLES if k == key), None)
            if option:
                self.toggle(option)
            elif key == "p":
                if self.creds.held:
                    self.actions.forget_logins("you asked")
                else:
                    self.message("No password is stored")
            elif key == "f":
                self.show_logs()

    def settings_rows(self):
        cfg = self.cfg
        rows = []
        for key, label, option in TOGGLES:
            on = getattr(cfg, option)
            extra = {"session_log": cfg.log_dir, "debug": cfg.debug_log}.get(option, "") if on else ""
            rows.append((key, label, "on" if on else "off", extra))
        rows.append(("p", "Forget the stored password now", "held" if self.creds.held else "not held",
                     " + ".join(["+ local account"] * bool(self.creds.local)
                                + ["terminal server account"] * bool(self.creds.server))))
        written = logs_since(cfg, cfg.started)
        rows.append(("f", "Log files of this session", "%d" % len(written), "f shows the full paths"))
        return rows

    def toggle(self, option):
        on = not getattr(self.cfg, option)
        setattr(self.cfg, option, on)
        label = next(label for _, label, o in TOGGLES if o == option)
        text, error = "%s %s" % (label, "on" if on else "off"), None
        if option == "session_log":
            n, error, others = self.actions.record_panes(on)
            if n:
                text += " - %s %d running tmux pane%s" % (
                    "recording" if on else "stopped recording", n, "" if n == 1 else "s")
            if others:
                text += " - NOT %s: %s (another TRuffle window's, or from before a restart)" % (
                    "recorded" if on else "changed", ", ".join(others))
            if error:                # leads: a long message is cut at the right edge
                text = "%s - %s" % (error, text)
        self.message(text, error=bool(error), seconds=15 if error else 6)
