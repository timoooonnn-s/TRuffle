"""The read-only pages: help, details of one switch, the log files.  Each builds the
lines Screen.show_text draws; the help page is plain data first, so tests can check it."""

import os
import textwrap
import time

from .. import CREDIT, TITLE, VERSION
from ..console import ConsoleLogin
from ..credentials import minutes_text
from ..logs import keep_text
from ..tmux import MAX_PANES
from .theme import BANNER

COMMANDS = ["ssh", "ping", "details", "help", "exit"]


def help_sections(cfg, ncols, switches):
    """The help page as plain data, so it renders and tests the same: ("section", title)
    and ("item", key, text).  Short on purpose - the README explains."""
    lifetime = ("%s after you typed it" % minutes_text(cfg.password_lifetime)
                if cfg.password_lifetime else "when TRuffle exits")
    return [
        ("section", "Keys"),
        ("item", "Up Down PgUp PgDn Home End", "select a device"),
        ("item", "Left Right  Enter", "choose a command, run it"),
        ("item", "type  Backspace ^W ^U", "search; delete a character / word / all"),
        ("item", "ESC", "clear step by step: search, running ping, marks, sort"),
        ("item", "Tab  Shift-Tab", "mark / unmark for several at once (kept across searches)"),
        ("item", "F1..F%d" % ncols, "sort by column: up, down, off"),
        ("item", "^A", "mark all devices of this search (again: unmark them)"),
        ("item", "^E", "export this search with its results to a CSV in your home folder"),
        ("item", "^G  ^R  ^L  ^C", "settings, reload list, redraw, quit"),
        ("section", "Search"),
        ("item", "bc01", "letters may skip only at - . _ / : @ (ber-core-01)"),
        ("item", "'10.1.2  *-l1  w3|w4", "exact text; pattern over a whole column; either"),
        ("item", "type:core  location:", "a CSV column contains / is empty"),
        ("item", "-test  -type:edge", "exclude"),
        ("item", "ping:down  ssh:failed", "results: up down wait / ok failed, or none"),
        ("item", "is:recent  is:marked", "connected to (newest first), marked"),
        ("section", "Commands"),
        ("item", "ssh", "connect; with 2+ marked: one tmux pane each (max %d)" % MAX_PANES),
        ("item", "", "the password is kept in memory only, forgotten %s" % lifetime),
        ("item", "ping", "live ping; with 2+ marked: all at once into the PING column"),
        ("item", "details", "every field, and why the last ssh failed"),
        ("item", "help", "this page"),
        ("item", "exit", "quit and forget the credentials"),
        ("item", "SSH column", "ok = you got logged in; Ctrl-C while connecting = failed"),
        ("section", "tmux (%s)" % ("on" if cfg.tmux else "off: tmux = yes in truffle.conf")),
        ("item", "Ctrl-b d  ^T  ^K", "back here, back into tmux, close the sessions"),
        ("item", "^G l", "session log on/off, also for running panes"),
        ("section", "Terminal servers (%s)" % (", ".join(cfg.console_hosts) or "off")),
        ("item", "Enter (ssh)", "asks the line (12 = port %d) and who logs in at the switch"
                                % (cfg.console_port_base + 12)),
        ("item", ConsoleLogin.EXIT_NAME, "back to TRuffle - log out of the switch FIRST"),
        ("section", "Setup"),
        ("item", "Device list", "%s  (%d devices)" % (cfg.data, switches)),
        ("item", "Config files", ", ".join(cfg.files) or "none (defaults)"),
        ("item", "State / results", cfg.state_dir),
        ("item", "Logs", "%s  (^G f lists them)" % cfg.log_dir),
    ]


def help_lines(th, cfg, ncols, switches):
    lines = [[(b, getattr(th, "banner%d" % (i + 1)))] for i, b in enumerate(BANNER)]
    lines += [[], [(TITLE, th.brand), ("   v" + VERSION, th.hint)], []]
    for entry in help_sections(cfg, ncols, switches):
        if entry[0] == "section":
            lines += [[], [(entry[1].upper(), th.head)]]
        else:
            lines.append([("  " + entry[1].ljust(30), th.key), (entry[2], th.text)])
    lines += [[], [(CREDIT, th.brand_sub), ("  %s  Inspired by V-Li: Switch Manager (Franz, 2025)."
                                               % th.sym["sep"], th.hint)]]
    return lines


def when(stamp):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(stamp))


def details_lines(th, dev, results, last_connected, width):
    """Every CSV field of one switch, its results with their time, and why the last ssh
    attempt failed - wrapped onto its own lines, it is why the reason is kept at all."""
    def result(kind):
        stamp = results.taken(kind, dev.host)
        text = results.get(kind, dev.host) or "not checked"
        return text + ("   (%s)" % when(stamp) if stamp else "")
    values = list(dev.values.items()) + [("Ping", result("ping")), ("SSH (last try)", result("ssh"))]
    for i, line in enumerate(textwrap.wrap(results.why("ssh", dev.host), max(20, width - 24))[:4]):
        values.append(("why it failed" if i == 0 else "", line))
    values += [("Last connected", when(last_connected) if last_connected else "never")]
    label_w = max(len(k) for k, _ in values)
    return [[(k.ljust(label_w), th.head), ("   ", th.text), (v, th.text)] for k, v in values]


def log_lines(th, cfg, files):
    """Ctrl-G f: the log files of this TRuffle session with their whole path - the
    footer is far too short for one.  Grouped by folder, so a name fits on a line."""
    lines = [] if files else ["No log file written since TRuffle started."]
    folder = None
    for path in files:
        if os.path.dirname(path) != folder:
            folder = os.path.dirname(path)
            lines += [[], [(folder + os.sep, th.key)]]
        lines.append("    " + os.path.basename(path))
    lines += [[], [("Session logs ", th.hint), (cfg.log_dir, th.text),
                   ("  (%s)" % ("on" if cfg.session_log else "off - Ctrl-G l"), th.hint)],
              [("Debug log    ", th.hint), (cfg.debug_log, th.text),
               ("  (%s)" % ("on" if cfg.debug else "off - Ctrl-G d"), th.hint)],
              [("Old logs     ", th.hint), (keep_text(cfg), th.text)],
              [],
              "TRuffle prints this list with the full paths when it exits.",
              "From any shell: truffle --logs"]
    return lines
