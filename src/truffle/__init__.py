"""TRuffle: Device Manager - a curses manager for network devices for use over plain SSH sessions.

Python 3.8+, standard library only (R1).  The `truffle` file next to `src/` starts it.

How the package is cut, from the bottom up - a module only imports the ones above it:

    config        truffle.conf -> Config
    inventory     the switch list (CSV) -> Device
    search        the search language            sorting      column sort
    results       PING / SSH results in memory   state        the per-user files (locked)
    credentials   the password and how long it is kept
    terminal      the plain terminal outside curses
    ping          ping, its verdict, ping several at once
    session       ssh in a pseudo-terminal       console      the terminal-server login
    logs          session and debug logs         connect      one ssh attempt and its outcome
    handover      the login for tmux panes       tmux         tmux sessions and panes
    pane          what runs inside one tmux pane
    ui/           the curses screens
    cli           the command line
"""

import os

VERSION = "2.3.0"           # bump before building a bundle
TITLE = "TRuffle: Device Manager"
CREDIT = "by Timmy & Ruffy"

# The install folder: the one holding the `truffle` launcher, truffle.conf and data.csv.
INSTALL_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
LAUNCHER = os.path.join(INSTALL_DIR, "truffle")          # what tmux panes and the recorder run
