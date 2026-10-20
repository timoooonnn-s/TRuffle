"""Terminal servers: ssh to the terminal server as user:<port> (port = line + 7000), then
the switch's own login on the serial line behind it - two logins in one session (D42)."""

import re

from .search import glob_match
from .session import clean_output, is_password_prompt
from .terminal import Notes

# "Login:", "ber-core-01 login:", "Username:", "User Name:" - the switch asking, never
# "Last login: Mon ..." (that one does not end with the colon).
LOGIN_PROMPT = re.compile(r"\b(?:login|user(?:\s?name)?)\s*:\s*$", re.IGNORECASE)
LOGIN_REFUSED = re.compile(r"login incorrect|authentication failed|incorrect password|invalid password",
                           re.IGNORECASE)
CONSOLE_QUIET = 1.0          # the terminal server says nothing for this long: it let us in
CONSOLE_WAKE = 5.0           # seconds for the line to show its login prompt after Enter
CONSOLE_WAITING_NOTE = 8.0   # no answer this long after the password: say why it takes so long
MODE_TEXT = {"radius": "your login, TRuffle types it",
             "local": "the local account, TRuffle types it",
             "manual": "you type it"}


def is_console_server(cfg, dev):
    """A terminal server is recognised by its NAME (console_hosts, e.g. *-*-ts?-*)."""
    name = (dev.name or "").lower()
    return bool(name) and any(glob_match(name, pattern) for pattern in cfg.console_hosts)


def parse_console_line(cfg, text):
    """'12' -> 12, or None when it is not a line this terminal server can have."""
    text = text.strip()
    if not re.match(r"^[0-9]{1,3}$", text) or int(text) < 1:
        return None
    return int(text) if cfg.console_port_base + int(text) <= 65535 else None


def console_user(cfg, user, line):
    """The username for the terminal server: timmy + line 12 -> timmy:7012.
    str.replace, not str.format: the template cannot reach anything but these two."""
    port = cfg.console_port_base + line
    return cfg.console_login.replace("{user}", user).replace("{port}", str(port))


class ConsoleLogin(object):
    """The switch's login behind a terminal server, as a step machine (testable without
    a pty).  It returns actions for run_session: ("send", bytes) to the switch, ("show",
    text) to your screen only.

    Steps: ts (server password) -> quiet (Enter wakes the line) -> login -> user -> pass
    -> watch (types nothing more; points at Ctrl-Q after you log out of the switch).

    Warden (D42): it types ONLY at a prompt it recognises - a console still logged in
    would otherwise get the password into its CLI history.  Anything unexpected hands
    over to you; a refused login is never typed twice.  user None = manual."""

    # Ctrl-Q ends the session, because logging out of the switch does not.
    # Not Ctrl-]: that is AltGr on a Swiss keyboard.
    EXIT_KEY, EXIT_NAME = b"\x11", "Ctrl-Q"

    def __init__(self, user=None, password=None, mode="manual", wait=240,
                 quiet=CONSOLE_QUIET, wake=CONSOLE_WAKE, notes=None):
        self.user, self.password, self.mode = user, password, mode
        self.wait, self.quiet, self.wake = wait, quiet, wake
        self.notes = notes or Notes()
        self.step, self.at, self.wakes = "ts", 0.0, 0
        self.tail = ""
        self.answered = False        # the switch said something after the password
        self.waiting_shown = False
        self.refused = False         # the switch turned the login down
        self.you_typed = False
        self.hinted = False
        self.prompts = 0             # login prompts (or a logged-in CLI) the line has shown so far
        self.events = []

    def note(self, *lines):
        return self.notes.text(*lines) + "\r\n"

    def _last(self):
        return clean_output(re.split(r"[\r\n]", self.tail)[-1]).strip()

    def _hand_over(self, why, show=True):
        self.events.append("over to you: %s" % why)
        self.step, self.tail = "watch", ""
        return [("show", self.note(why))] if show else []

    def no_password(self):
        """No stored password: you type both logins, TRuffle only watches."""
        self.step = "watch"

    def password_sent(self, now):
        self.step, self.at = "quiet", now

    def typed(self):
        """You pressed a key: from now on everything is yours."""
        if self.step != "watch":
            self._hand_over("you typed", show=False)
        self.you_typed, self.hinted = True, False

    def output(self, text, now):
        if not text:
            return []
        self.tail = (self.tail + text)[-1024:]
        last = self._last()
        if self.step == "ts":
            return []
        if self.step == "quiet":
            if not LOGIN_PROMPT.search(last):
                self.at = now                 # still talking: not quiet yet
                return []
            self.step = "login"               # the line showed its prompt by itself
        if self.step == "login":
            return self._at_login(last, now)
        if self.step == "user":
            return self._after_user(last, now)
        if self.step == "pass":
            return self._after_password(text, last)
        return self._watch(last)

    def _at_login(self, last, now):
        if LOGIN_PROMPT.search(last):
            self.prompts += 1
            self.events.append("switch login prompt seen: %r" % last)
            if self.user is None:
                return self._hand_over("manual login", show=False)
            self.step, self.at, self.tail = "user", now, ""
            self.events.append("username typed (%s)" % self.mode)
            return [("send", self.user.encode("utf-8") + b"\r")]
        if is_password_prompt(last):
            return self._hand_over("The switch asks for a password without asking for a "
                                   "username first - TRuffle typed nothing, over to you.")
        return []

    def _after_user(self, last, now):
        if is_password_prompt(last):
            self.events.append("switch password prompt seen: %r" % last)
            if self.password is None:
                return self._hand_over("no password stored", show=False)
            self.step, self.at, self.tail = "pass", now, ""
            self.events.append("password typed (once)")
            return [("send", self.password.encode("utf-8") + b"\r")]
        if LOGIN_PROMPT.search(last):
            self.refused, self.prompts = True, self.prompts + 1
            return self._hand_over("The switch did not take the %s username - log in by hand." % self.mode)
        return []

    def _after_password(self, text, last):
        if clean_output(text).strip():
            self.answered = True
        if LOGIN_REFUSED.search(clean_output(self.tail)) or LOGIN_PROMPT.search(last) \
                or is_password_prompt(last):
            self.refused, self.prompts = True, self.prompts + 1
            return self._hand_over("The switch refused the %s login - log in by hand "
                                   "(TRuffle keeps the password)." % self.mode)
        return []

    def _watch(self, last):
        # You logged out of the switch, and its login prompt is BACK - not the first one,
        # which is simply the switch asking.  tail is cleared, so one prompt counts once.
        if LOGIN_PROMPT.search(last):
            self.tail = ""
            earlier, self.prompts = self.prompts, self.prompts + 1
            if earlier and self.you_typed and not self.hinted:
                self.hinted = True
                return [("show", self.note("Logged out? %s goes back to TRuffle." % self.EXIT_NAME) + last + " ")]
        return []

    def tick(self, now):
        """Called about every 0.2 s: the steps that move on because NOTHING came."""
        if self.step == "quiet" and now - self.at >= self.quiet:
            self.step, self.at, self.wakes = "login", now, 1
            self.events.append("terminal server quiet -> Enter to wake the line")
            return [("send", b"\r")]
        if self.step == "login" and now - self.at >= self.wake:
            if self.wakes < 2:
                self.wakes, self.at = self.wakes + 1, now
                self.events.append("no login prompt yet -> Enter once more")
                return [("send", b"\r")]
            self.prompts += 1                 # whatever is on the line, it is a session already
            if self.user is None:
                return self._hand_over("no login prompt (manual login)", show=False)
            return self._hand_over("No login prompt on the line (still logged in, or busy?) - "
                                   "TRuffle typed nothing, over to you.")
        if self.step == "user" and now - self.at >= self.wait:
            return self._hand_over("No password prompt from the switch - over to you.")
        if self.step == "pass":
            if not self.waiting_shown and not self.answered and now - self.at >= CONSOLE_WAITING_NOTE:
                self.waiting_shown = True
                return [("show", self.note("Waiting for the switch - one that cannot reach its RADIUS "
                                           "server can take a few minutes.", "Any key takes over."))]
            if now - self.at >= self.wait:
                self.events.append("no refusal within %ds -> logged in" % self.wait)
                self.step = "watch"
        return []
