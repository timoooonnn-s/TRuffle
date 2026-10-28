"""The logins TRuffle holds in memory: your own, a switch's local account for the console
behind a terminal server, and a terminal server's own local account (lab terminal servers
without RADIUS, D54).  Never written anywhere, gone when TRuffle exits."""

import time


def creds_expired(now, entered_at, minutes):
    """Typed more than `minutes` ago (0 = never)?  Absolute, not idle time (D28)."""
    return bool(minutes) and now - entered_at > minutes * 60


def minutes_text(minutes):
    """'10 h', '1 h 30 min', '45 min' - never a rounded-off lie like '2 h' for 90."""
    if minutes >= 60 and minutes % 60 == 0:
        return "%d h" % (minutes // 60)
    if minutes > 60:
        return "%d h %d min" % (minutes // 60, minutes % 60)
    return "%d min" % minutes


class Login(object):
    """One user name and password (None = you type it at the prompt), and when it was typed."""

    def __init__(self, user, password):
        self.user, self.password = user, password
        self.typed_at = time.time()


class Credentials(object):
    """`own` logs you in everywhere; `local` is a switch's local account (console only);
    `server` a terminal server's local account.  Each expires `lifetime` minutes after it
    was typed (0 = when TRuffle exits)."""

    def __init__(self, lifetime):
        self.lifetime = lifetime
        self.own = None
        self.local = None
        self.server = None
        self.last_user = ""            # pre-filled in the login dialog after a wipe
        self.last_local_user = ""
        self.last_server_user = ""

    def set_own(self, user, password):
        self.own = Login(user, password)
        self.last_user = user

    def set_local(self, user, password):
        self.local = Login(user, password)
        self.last_local_user = user

    def set_server(self, user, password):
        self.server = Login(user, password)
        self.last_server_user = user

    @property
    def held(self):
        return self.own is not None or self.local is not None or self.server is not None

    def forget(self):
        self.own = self.local = self.server = None

    def forget_server_if_older(self, stamp):
        """forget_if_older for a pane on a terminal server that took its local account."""
        if self.server is not None and stamp >= self.server.typed_at:
            self.server = None
            return True
        return False

    def forget_if_older(self, stamp):
        """A tmux pane reported a wrong password at `stamp`: forget ours if it was typed
        before that - then it was THIS password that failed.  Returns True if forgotten."""
        if self.own is not None and stamp >= self.own.typed_at:
            self.forget()
            return True
        return False

    def expire(self, now=None):
        """Forget what is older than the lifetime.  Returns the names of what went:
        a subset of ["password", "local account", "terminal server account"]."""
        now = time.time() if now is None else now
        gone = []
        if self.own is not None and creds_expired(now, self.own.typed_at, self.lifetime):
            self.forget()                      # the local account goes with the password
            gone.append("password")
        if self.local is not None and creds_expired(now, self.local.typed_at, self.lifetime):
            self.local = None
            gone.append("local account")
        if self.server is not None and creds_expired(now, self.server.typed_at, self.lifetime):
            self.server = None
            gone.append("terminal server account")
        return gone
