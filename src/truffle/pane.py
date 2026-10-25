"""`truffle --pane ...`: what runs inside one tmux pane.  Fetch the login once, connect,
record the outcome, then the pane closes.  With --pane-console LINE LOGIN the pane is one
line of a terminal server (D51): ssh as user:<port>, then the switch's login behind it."""

import json
import os

from .connect import pause_on_failure, record_attempt, ssh_flow
from .console import ConsoleLogin, console_user
from .handover import handover_request
from .inventory import valid_host
from .results import Results
from .state import UserState
from .terminal import CHARSETS, Notes
from .tmux import record_pane


def fetch_login(socket_path, ticket):
    """The login from TRuffle: {"user", "password"} and, for a console pane, "switch_user" /
    "switch_password" (empty = you type it).  Raises OSError / ValueError / KeyError."""
    answer = handover_request(socket_path, "GET %s" % ticket)
    if not answer.startswith("OK "):
        raise ValueError(answer)
    login = json.loads(answer[3:])
    login["user"]                       # KeyError: not a login at all
    return login


def pane_main(cfg, socket_path, ticket, host, name, console=None):
    """console: (line, login) - this pane is that line of the terminal server `name`."""
    notes = Notes(os.environ.get("TERM", "dumb") not in ("", "dumb"), CHARSETS[cfg.charset]["gt"])
    close = "close this pane"
    if not valid_host(host):
        notes.ask("'%s' is not a usable host." % host, "Press any key to %s ..." % close)
        return 1
    # A pane is recorded through tmux (pipe-pane), never by ssh_flow, so TRuffle can switch
    # the log on and off while it runs - and it is never written twice.
    record, cfg.session_log = cfg.session_log, False
    login, problems = {"user": cfg.user}, []
    try:
        login = fetch_login(socket_path, ticket)
    except (OSError, ValueError, KeyError) as e:
        problems += ["Could not get the login from TRuffle (%s)." % e,
                     "Connecting anyway - ssh will ask you for the password."]
    user, password = login["user"], login.get("password") or None
    label, ssh_user, switch_login = name, user, None
    if console:
        line, mode = int(console[0]), console[1]
        label, ssh_user = "%s line %d" % (name, line), console_user(cfg, user, line)
        switch = (login.get("switch_user") or None, login.get("switch_password") or None)
        if mode != "manual" and switch[0] is None:
            problems.append("No %s login for the switch - you log in at the switch yourself." % mode)

        def switch_login():
            return ConsoleLogin(switch[0], switch[1], mode, cfg.console_login_wait, notes=notes)
    if record:                     # before anything is shown, so nothing is missed
        error = record_pane(cfg, os.environ.get("TMUX_PANE", ""), label, host, ssh_user)
        problems = ([error] if error else []) + problems
    if problems:
        notes.say(*problems)
    # The status file is shared and merges by time, so TRuffle picks the result up when
    # it comes back, however long this ran.
    store = UserState(cfg.state_dir)
    result = ssh_flow(cfg, label, host, ssh_user, password, notes,
                      lambda r: record_attempt(store, Results(), host, name or host, r), back=close,
                      console=switch_login)
    password = login = None        # the only copies of the logins this pane holds
    if result.auth_failed:
        # Tell TRuffle too, so it drops the password instead of spending it on the
        # next switch as well - the socket is already closed by now.
        store.note_auth_failure(host)
        notes.ask("Login failed on %s - wrong password?" % label,
                  "TRuffle will ask for the password again.", "Press any key to %s ..." % close)
    elif result.prompt_missed:
        notes.ask("No password prompt recognised on %s - you had to type it." % label,
                  "Run TRuffle with --debug and connect again to see what the switch sent.",
                  "Press any key to %s ..." % close)
    else:
        pause_on_failure(notes, label, result, close)
    return 0
