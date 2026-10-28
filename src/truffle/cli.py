"""The command line: `truffle`, `truffle --check`, `truffle --logs`, and the two internal
entry points tmux starts (--pane, --log-sink)."""

import argparse
import curses
import locale
import os
import signal
import sys

from . import CREDIT, TITLE, VERSION
from .config import ConfigError, load_config
from .console import is_console_server
from .credentials import minutes_text
from .export import exports_since
from .inventory import DataError, build_devices, data_issues, read_table
from .logs import keep_text, list_logs, log_sink, logs_since
from .pane import pane_main
from .session import raw_mode_visible
from .state import CONSOLE_MODES, SERVER_MODES
from .terminal import bracketed_paste, harden_process, which
from .tmux import truffle_sessions
from .ui.app import App


def check(cfg):
    """--check: validate config and switch list without starting the UI.  Exit code
    0 = fine, 1 = warnings only (so a cron check can gate on it), 2 = cannot run."""
    ok, no_warnings = True, True
    print("%s v%s  %s" % (TITLE, VERSION, CREDIT))
    print("config files : %s" % (", ".join(cfg.files) or "none (defaults)"))
    print("device list  : %s" % cfg.data)
    try:
        report = {}
        headers, rows = read_table(cfg.data, report)
        devices, columns, warns, picked = build_devices(headers, rows, cfg)
        print("devices      : %d" % len(devices))
        print("columns      : %s" % ", ".join("%s (%s)" % c for c in columns))
        # Which column is which is the thing you cannot see from the table, so say it.
        print("device name  : %s" % picked["name"])
        print("ssh target   : %s" % picked["host"])
        print("headers found: %s" % ", ".join(headers))
        if devices:
            first = devices[0]
            print("first device : name %r  ssh to %r" % (first.values.get(picked["name"], ""), first.host))
        consoles = [d for d in devices if is_console_server(cfg, d)]
        print("term. servers: %d  (console_hosts = %s)%s" % (
            len(consoles), " ".join(cfg.console_hosts) or "off",
            "  e.g. %s" % consoles[0].name if consoles else ""))
        issues = warns + data_issues(devices, report["lines"], report["issues"], picked["name"])
        no_warnings = not issues
        print("data check   : %s" % ("ok" if no_warnings else "%d warning(s)" % len(issues)))
        for w in issues[:50]:
            print("  warning: %s" % w)
        if len(issues) > 50:
            print("  ... and %d more" % (len(issues) - 50))
    except DataError as e:
        print("  ERROR: %s" % e)
        ok = False
    for name, path in (("ssh", which(cfg.ssh_command[0])), ("ping", which("ping"))):
        print("%-13s: %s" % (name, path or "NOT FOUND"))
        ok = ok and path is not None
    # The SSH column knows a login worked only by seeing ssh switch the pty to raw mode.
    if raw_mode_visible():
        print("ssh results  : ok (a started session is recognised)")
    else:
        no_warnings = False
        print("ssh results  : NOT RELIABLE - this system does not show TRuffle when ssh starts a\n"
              "               session, so every login would be recorded as failed")
    print("state dir    : %s" % cfg.state_dir)
    print("session log  : %s" % (cfg.log_dir if cfg.session_log else "off"))
    print("old logs     : %s" % keep_text(cfg))
    print("password     : %s" % ("forgotten %s after you type it, sessions untouched"
                                 % minutes_text(cfg.password_lifetime) if cfg.password_lifetime
                                 else "kept until TRuffle exits (password_lifetime = 0)"))
    if not ok:
        return 2
    return 0 if no_warnings else 1


def parse_args(argv):
    parser = argparse.ArgumentParser(prog="truffle", description=TITLE + " - connect to your network devices over SSH.")
    parser.add_argument("--data", metavar="CSV",
                        help="device list (default: 'data' in truffle.conf, else data.csv next to truffle)")
    parser.add_argument("--config", metavar="FILE", help="additional config file")
    parser.add_argument("--log", action="store_true", help="record ssh sessions to log files")
    parser.add_argument("--debug", action="store_true",
                        help="write what happens around each ssh login to debug.log in the state "
                             "directory (truffle --check prints the path)")
    parser.add_argument("--ascii", action="store_true", help="plain ASCII screen (if lines/symbols look garbled)")
    parser.add_argument("--check", action="store_true", help="check config and device list, then exit")
    parser.add_argument("--logs", action="store_true",
                        help="show where the log files are and the newest ones, then exit")
    parser.add_argument("--pane", nargs=4, metavar=("SOCKET", "TICKET", "HOST", "NAME"),
                        help=argparse.SUPPRESS)        # internal: one device inside a tmux pane
    parser.add_argument("--pane-console", nargs=2, metavar=("LINE", "LOGIN"),
                        help=argparse.SUPPRESS)        # internal: ... that is a terminal-server line
    parser.add_argument("--pane-server-login", choices=SERVER_MODES, default="radius",
                        help=argparse.SUPPRESS)        # internal: ... reached with its local account
    parser.add_argument("--log-sink", nargs=2, metavar=("FILE", "HEADER"),
                        help=argparse.SUPPRESS)        # internal: tmux records one pane into FILE
    parser.add_argument("--version", action="version", version="%(prog)s " + VERSION)
    return parser.parse_args(argv)


def run_ui(cfg):
    os.environ.setdefault("ESCDELAY", "50")       # before initscr: fast ESC key
    signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(143))
    # Closing the PuTTY window or killing the tmux session sends SIGHUP.  Its default
    # kills TRuffle on the spot - a ping running or still on screen was then never saved,
    # and after a restart ping:down could not find those switches (D48).  As an exit, the
    # results are saved on the way out like after Ctrl-C.
    signal.signal(signal.SIGHUP, lambda signum, frame: sys.exit(129))
    try:
        curses.wrapper(lambda scr: App(scr, cfg).run())
    except KeyboardInterrupt:
        pass
    except curses.error as e:
        print("truffle: terminal error: %s (TERM=%s)" % (e, os.environ.get("TERM", "")), file=sys.stderr)
        return 1
    finally:
        # Every way out - a normal exit, a failed startup, a curses error: the
        # terminal must not keep a mode we switched on.
        bracketed_paste(False)
    print("TRuffle closed - credentials forgotten.")
    written = logs_since(cfg, cfg.started) + exports_since(cfg.started)
    if written:
        print("Files written while TRuffle was open (logs, exports):")
        for path in written:
            print("  %s" % path)
    for session in truffle_sessions():
        print("  note: tmux session %s is still running (logged-in devices):  tmux attach -t %s"
              % (session, session))
    return 0


def main(argv=None):
    args = parse_args(argv)
    if args.log_sink:                             # started by tmux pipe-pane, needs no config
        return log_sink(*args.log_sink)
    try:
        cfg = load_config(args)
    except ConfigError as e:
        print("truffle: config error: %s" % e, file=sys.stderr)
        return 2
    if args.check:
        return check(cfg)
    if args.logs:
        return list_logs(cfg)
    harden_process()                              # before the password can ever be in memory
    try:
        locale.setlocale(locale.LC_ALL, "")
    except locale.Error:
        pass
    if args.pane:                                 # started by TRuffle inside a tmux pane
        # Only what TRuffle passed counts - not truffle.conf, which a Ctrl-G change in
        # TRuffle (log off, other symbols) does not touch.
        cfg.session_log, cfg.charset_setting = args.log, "ascii" if args.ascii else "unicode"
        console = args.pane_console
        if console and not (console[0].isdigit() and console[1] in CONSOLE_MODES):
            print("truffle: --pane-console wants LINE and one of %s" % ", ".join(CONSOLE_MODES), file=sys.stderr)
            return 2
        return pane_main(cfg, *args.pane, console=console, server_mode=args.pane_server_login)
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("truffle: must be run in an interactive terminal", file=sys.stderr)
        return 2
    return run_ui(cfg)
