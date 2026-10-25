"""What the ssh command does from the main screen: one switch, a terminal-server line, or
several switches in tmux - plus the background duties that come with held logins (the
password lifetime, a pane that reported a wrong password, tmux sessions that ended)."""

import os
import time

from ..config import valid_user
from ..connect import pause_on_failure, record_attempt, ssh_flow
from ..console import ConsoleLogin, console_user
from ..credentials import minutes_text
from ..handover import Handover
from ..logs import log_note
from ..terminal import which
from ..tmux import MAX_PANES, TMUX_ERRORS, enter_session, open_panes
from .dialogs import console_dialog, login_dialog

SESSION_POLL = 3.0          # seconds between looks at our tmux sessions


class Actions(object):

    def __init__(self, cfg, screen, lst, store, results, creds, panes):
        self.cfg, self.screen, self.lst = cfg, screen, lst
        self.store, self.results, self.creds, self.panes = store, results, creds, panes
        self.authfail_seen = 0.0       # the last pane login failure already acted on

    def message(self, *args, **kw):
        self.screen.message(*args, **kw)

    # -- logins -------------------------------------------------------------------

    def ask_login(self, error=None, server=None):
        """Your own login, asked once and kept.  Returns the Login, or None on ESC.
        server: the terminal server it is asked for, so the window says what it is for."""
        if self.creds.own is None:
            entered = login_dialog(self.screen, self.creds.last_user or self.cfg.user, error=error, server=server)
            if entered is None:
                return None
            self.creds.set_own(*entered)
        return self.creds.own

    def ask_local_login(self, server):
        if self.creds.local is None:
            entered = login_dialog(self.screen, self.creds.last_local_user, local_for=server)
            if entered is None:
                return None
            self.creds.set_local(*entered)
        return self.creds.local

    def forget_logins(self, why):
        self.creds.forget()
        self.message("Password forgotten (%s) - you will be asked again." % why, seconds=15)

    # -- one switch -----------------------------------------------------------------

    def ssh(self, dev):
        self._connect(dev, dev.name, lambda own: own.user)

    def console(self, dev):
        """A terminal server: ask which line and who logs in at the switch behind it,
        then ssh as user:<port>.  The terminal server always takes your normal login."""
        line, mode = self.store.console_choice(dev.key)
        user = self.creds.own.user if self.creds.own else (self.creds.last_user or self.cfg.user or "user")
        local = self.creds.local.user if self.creds.local else None
        choice = console_dialog(self.screen, self.cfg, dev.name, line, mode, user, local)
        if choice is None:
            self.message("Console cancelled")
            return
        line, mode = choice
        self.store.save_console_choice(dev.key, line, mode)
        if self.ask_login(server=dev.name) is None or (mode == "local" and self.ask_local_login(dev.name) is None):
            self.message("Console cancelled")
            return

        def switch_login():
            """A fresh ConsoleLogin per attempt - the host-key retry starts over."""
            login = {"radius": self.creds.own, "local": self.creds.local}.get(mode)
            return ConsoleLogin(login.user if login else None, login.password if login else None, mode,
                                self.cfg.console_login_wait, notes=self.screen.notes())
        self._connect(dev, "%s line %d" % (dev.name, line), lambda own: console_user(self.cfg, own.user, line),
                      console=switch_login, mode=mode)

    def _connect(self, dev, label, ssh_user, console=None, mode=None):
        """Login, connect, record; a refused password is wiped and asked again (D3).
        ssh_user maps your login to the ssh user (terminal server: user:port)."""
        error = None
        while True:
            own = self.ask_login(error, server=dev.name if console else None)
            if own is None:
                self.message("%s cancelled" % ("Console" if console else "ssh"))
                return
            user = ssh_user(own)
            if not valid_user(user):
                self.message("'%s' is not a valid username - check console_login in truffle.conf" % user,
                             error=True, seconds=12)
                return
            result = self._run(dev, label, user, own.password, console)
            if not result.auth_failed:
                break
            self.creds.own = None             # the wrong password goes; the local account stays
            error = "Login failed for '%s' on %s - please re-enter." % (user, dev.name)
        self._report(dev, label, result, mode)

    def _run(self, dev, label, user, password, console):
        """One attempt with the terminal handed to ssh.  The outcome is recorded while
        still outside curses, before any 'press a key'."""
        notes = self.screen.notes()

        def record(result):
            record_attempt(self.store, self.results, dev.host, dev.key, result)
        self.screen.leave()
        try:
            result = ssh_flow(self.cfg, label, dev.host, user, password, notes, record, console=console)
            pause_on_failure(notes, label, result, "return to TRuffle")
        finally:
            self.screen.resume()
        self.lst.status_changed(dev, force=True)        # is:recent, ssh: searches, status sorts
        return result

    def _report(self, dev, label, result, mode=None):
        reason = self.results.why("ssh", dev.host)
        if self.store.error:
            self.message(self.store.error, error=True, seconds=10)
        elif result.prompt_missed:
            self.message("%s: no password prompt recognised - you had to type it yourself. "
                         "Run 'truffle --debug' and connect again to see what the switch sent."
                         % dev.name, error=True, seconds=20)
        elif result.hostkey_changed:
            self.message("%s: %s" % (dev.name, reason), error=True, seconds=15)
        elif reason:
            self.message("%s: ssh failed - %s" % (label, reason), error=True, seconds=10)
        elif result.switch_refused:
            self.message("%s: the switch refused the %s login, so you logged in by hand - "
                         "the password is kept%s" % (label, mode, log_note(result)), seconds=12)
        elif result.console_closed:
            self.message("Console closed: %s%s" % (label, log_note(result)))
        else:
            self.message("Disconnected from %s%s" % (label, log_note(result)))

    # -- several switches -------------------------------------------------------------

    def many(self, devices):
        """One tmux session, a pane per switch, one login.  True when it was opened."""
        if not self.cfg.tmux or not which("tmux"):
            self.message("%s - connecting to several devices at once needs it. "
                         "Marks still decide what ping checks; ESC (empty search) clears them to ssh one."
                         % ("tmux mode is off (tmux = yes in truffle.conf)" if not self.cfg.tmux
                            else "tmux is not installed"), error=True, seconds=12)
            return False
        extra = len(devices) - MAX_PANES
        devices = devices[:MAX_PANES]
        own = self.ask_login()
        if own is None:
            self.message("ssh cancelled")
            return False
        try:
            handover = Handover(lambda: (own.user, own.password))
        except OSError as e:
            self.message("cannot open the login handover for the panes: %s" % e, error=True, seconds=15)
            return False
        try:
            session, panes = open_panes(self.cfg, devices, handover)
        except TMUX_ERRORS + (ValueError,) as e:
            handover.close()
            self.message("tmux failed: %s" % e, error=True, seconds=15)
            return False
        self.panes.add(session, panes, own.user)
        self.message("Starting %d panes and logging them in ..." % len(devices), seconds=30)
        self.screen.backdrop()                         # the wait is short, but never silent
        self.screen.scr.refresh()
        got_logins = handover.wait()                   # panes fetch immediately after they start
        handover.close()                               # the socket is not needed any more
        refused = handover.take_refusals()
        error = self.enter(session)                    # also picks up what the panes wrote
        # A pane may have reported a wrong password while we were in tmux; that message
        # matters most, so it leads the line - a long one is cut off at the right edge.
        lost = self.creds.own is not own
        lead = ("Password was wrong and has been dropped - you will be asked again.  %s  "
                % self.screen.sym["sep"]) if lost else ""
        if error:
            self.message("%stmux session %s started, but could not show it: %s" % (lead, session, error),
                         error=True, seconds=15)
            return True
        note = lead + "%d device%s in tmux session %s" % (len(devices), "" if len(devices) == 1 else "s", session)
        if not got_logins:
            note += " - some panes had to ask for the password themselves"
        if extra > 0:
            note += " (%d more were not opened - %d panes at most)" % (extra, MAX_PANES)
        if refused:
            note += " - REFUSED: %s" % "; ".join(refused[:2])
        note += "  %s  Ctrl-b d comes back here, Ctrl-T goes back in, Ctrl-K closes them" % self.screen.sym["sep"]
        self.message(note, error=bool(refused or lost), seconds=20)
        return True

    def enter(self, session):
        """Hand the terminal to tmux and come back.  Returns an error text or ''."""
        self.screen.leave()
        try:
            return enter_session(session)
        finally:
            self.screen.resume()
            self.reload_results()

    def reattach(self):
        """Ctrl-T: back into the tmux session that holds the open switches."""
        if not which("tmux"):
            self.message("tmux is not installed", error=True, seconds=10)
            return
        sessions = self.panes.refresh()
        if not sessions:
            self.message("No open tmux session - mark 2 or more devices with Tab, then run ssh", seconds=10)
            return
        session = sessions[-1]              # the newest one
        if self.panes.foreign and not self.screen.confirm(
                "Go into another window's session",
                "%s was not started by this TRuffle window. Go into it anyway?" % session,
                detail=["  another TRuffle of yours is probably using it"]):
            self.message("Nothing opened")
            return
        error = self.enter(session)
        if error:
            self.message("Could not go back to %s: %s" % (session, error), error=True, seconds=15)
            return
        left = self.panes.refresh()
        if os.environ.get("TMUX"):
            self.message("Switched to %s (Ctrl-b L switches back here)" % session, seconds=10)
        elif len(left) > 1:
            self.message("Back from %s - still running: %s"
                         % (session, ", ".join(s for s in left if s != session)), seconds=15)
        else:
            self.message("Back from %s" % session if session in left else "%s has ended" % session)

    def close_sessions(self):
        """Ctrl-K: close the switch sessions without hunting for a tmux key."""
        sessions = self.panes.refresh()
        if not sessions:
            self.message("No open tmux session", seconds=8)
            return
        detail = ["  " + s for s in sessions]
        if self.panes.foreign:           # not ours: say so before logging anyone out
            detail += ["", "  NOT started by this TRuffle window - another", "  TRuffle of yours may be using them."]
        if not self.screen.confirm("Close tmux sessions",
                                   "Close %d tmux session%s and log out of every device in them?"
                                   % (len(sessions), "" if len(sessions) == 1 else "s"), detail=detail):
            self.message("Nothing closed")
            return
        self.panes.close(sessions)
        self.reload_results()
        self.message("Closed %d tmux session%s" % (len(sessions), "" if len(sessions) == 1 else "s"))

    def record_panes(self, on):
        return self.panes.record(self.cfg, on)

    # -- background duties ------------------------------------------------------------

    def reload_results(self):
        """Pick up results another TRuffle - or one of our tmux panes - has written."""
        self.results.merge_newer(self.store.load_results())
        self.store.load()                   # the recent list too
        self.check_pane_auth_failure()
        self.lst.status_changed(force=True)

    def check_pane_auth_failure(self):
        """A tmux pane could not log in: drop the password instead of spending it on
        switch after switch (a central TACACS+/RADIUS account would lock out)."""
        stamp, host = self.store.load_auth_failure()
        if stamp <= self.authfail_seen:
            return
        self.authfail_seen = stamp
        if self.creds.forget_if_older(stamp):          # it was THIS password that failed
            self.message("Password forgotten (a tmux pane could not log in to %s) - "
                         "you will be asked again." % host, seconds=15)

    def check_sessions(self):
        """Poll our tmux sessions; when one ended (noticed here or elsewhere), load what its
        panes wrote."""
        if self.panes.mine and time.time() - self.panes.checked_at >= SESSION_POLL:
            # Do not wait for the session to end: a pane that could not log in has already
            # said so, and the password it used must go now, not in an hour.
            self.check_pane_auth_failure()
            self.panes.refresh()
        ended = self.panes.take_ended()
        if ended:
            self.reload_results()
            self.message("tmux session %s ended" % ", ".join(ended))

    def check_password_lifetime(self):
        """Forget the password `password_lifetime` after it was typed - in TRuffle only (D28)."""
        gone = self.creds.expire()
        if gone:
            self.message("%s forgotten (typed %s ago) - you will be asked again."
                         % (" and ".join(gone).capitalize(), minutes_text(self.cfg.password_lifetime)),
                         seconds=15)

