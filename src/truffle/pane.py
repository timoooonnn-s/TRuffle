"""`truffle --pane ...`: what runs inside one tmux pane.  Fetch the login once, connect,
record the outcome, then the pane closes."""

import json
import os

from .connect import pause_on_failure, record_attempt, ssh_flow
from .handover import handover_request
from .inventory import valid_host
from .results import Results
from .state import UserState
from .terminal import CHARSETS, Notes
from .tmux import record_pane


def fetch_login(socket_path, ticket):
    """(user, password or None) from TRuffle, or raises OSError / ValueError / KeyError."""
    answer = handover_request(socket_path, "GET %s" % ticket)
    if not answer.startswith("OK "):
        raise ValueError(answer)
    login = json.loads(answer[3:])
    return login["user"], login["password"] or None


def pane_main(cfg, socket_path, ticket, host, name):
    notes = Notes(os.environ.get("TERM", "dumb") not in ("", "dumb"), CHARSETS[cfg.charset]["gt"])
    close = "close this pane"
    if not valid_host(host):
        notes.ask("'%s' is not a usable host." % host, "Press any key to %s ..." % close)
        return 1
    # A pane is recorded through tmux (pipe-pane), never by ssh_flow, so TRuffle can switch
    # the log on and off while it runs - and it is never written twice.
    record, cfg.session_log = cfg.session_log, False
    user, password, problems = cfg.user, None, []
    try:
        user, password = fetch_login(socket_path, ticket)
    except (OSError, ValueError, KeyError) as e:
        problems += ["Could not get the login from TRuffle (%s)." % e,
                     "Connecting anyway - ssh will ask you for the password."]
    if record:                     # before anything is shown, so nothing is missed
        error = record_pane(cfg, os.environ.get("TMUX_PANE", ""), name, host, user)
        problems = ([error] if error else []) + problems
    if problems:
        notes.say(*problems)
    # The status file is shared and merges by time, so TRuffle picks the result up when
    # it comes back, however long this ran.
    store = UserState(cfg.state_dir)
    result = ssh_flow(cfg, name, host, user, password, notes,
                      lambda r: record_attempt(store, Results(), host, name or host, r), back=close)
    password = None                # the only copy of the login this pane holds
    if result.auth_failed:
        # Tell TRuffle too, so it drops the password instead of spending it on the
        # next switch as well - the socket is already closed by now.
        store.note_auth_failure(host)
        notes.ask("Login failed on %s - wrong password?" % name,
                  "TRuffle will ask for the password again.", "Press any key to %s ..." % close)
    elif result.prompt_missed:
        notes.ask("No password prompt recognised on %s - you had to type it." % name,
                  "Run TRuffle with --debug and connect again to see what the switch sent.",
                  "Press any key to %s ..." % close)
    else:
        pause_on_failure(notes, name, result, close)
    return 0
