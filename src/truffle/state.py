"""The per-user files in ~/.local/state/truffle (0600 in 0700, replaced atomically):

    recent      time TAB key
    status      host TAB kind TAB state TAB time [TAB detail]
    console     server TAB lines TAB login [TAB server login]
    authfail    time TAB host (from a tmux pane)
    saved       host TAB name [TAB user]   (your own devices, not in the list: D55)

All TRuffle windows and tmux panes write here, so each read-change-write holds a lock (D45).
"""

import contextlib
import fcntl
import os
import time

from .results import CHECKED_STATES, KINDS, Results
from .inventory import clean, typed_target

CONSOLE_MODES = ("radius", "local", "manual")      # the switch behind a terminal server
SERVER_MODES = ("radius", "local")                 # the terminal server itself (D54)


class UserState(object):
    """History, saved results and console choices of the current user.
    A file that cannot be read or written sets `error`; TRuffle keeps working in memory."""

    MAX_RECENT = 200
    MAX_CONSOLE = 500
    MAX_SAVED = 1000

    def __init__(self, directory):
        self.dir = directory
        self.recent = {}               # device key -> time of the last successful connection
        self.error = None
        self.load()

    # -- files ------------------------------------------------------------------

    def _path(self, name):
        return os.path.join(self.dir, name)

    @contextlib.contextmanager
    def _locked(self):
        """The state lock for one read-change-write - best effort: where locks are refused
        (NFS without a lock manager) it goes ahead unlocked instead of failing."""
        fd = None
        try:
            os.makedirs(self.dir, mode=0o700, exist_ok=True)
            fd = os.open(self._path(".lock"), os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            fcntl.flock(fd, fcntl.LOCK_EX)
        except OSError:
            pass
        try:
            yield
        finally:
            if fd is not None:
                os.close(fd)                   # closing releases the lock

    def _read(self, name):
        try:
            with open(self._path(name), encoding="utf-8") as f:
                return f.readlines()
        except FileNotFoundError:
            return []
        except (OSError, UnicodeDecodeError) as e:
            self.error = "cannot read %s: %s" % (self._path(name), e)
            return []

    def _write(self, name, lines):
        path = self._path(name)
        tmp = "%s.%d.tmp" % (path, os.getpid())
        try:
            os.makedirs(self.dir, mode=0o700, exist_ok=True)
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write("".join(line + "\n" for line in lines))
            os.replace(tmp, path)          # atomic: a crash never leaves half a file
            self.error = None
        except OSError as e:
            self.error = "cannot save %s: %s" % (path, e.strerror or e)
            try:
                os.unlink(tmp)
            except OSError:
                pass

    # -- history (is:recent) - favourites were cut in the feature review (D50) ----------

    def load(self):
        self.recent = {}
        for line in self._read("recent"):
            stamp, _, key = line.rstrip("\n").partition("\t")
            try:
                if key:
                    self.recent[key] = max(float(stamp), self.recent.get(key, 0))
            except ValueError:
                pass

    def touch(self, key):
        """`key` was just connected to."""
        with self._locked():
            self.load()
            self.recent[key] = time.time()
            newest = sorted(self.recent.items(), key=lambda item: item[1], reverse=True)[:self.MAX_RECENT]
            self.recent = dict(newest)
            self._write("recent", ["%d\t%s" % (stamp, k) for k, stamp in reversed(newest)])

    # -- results ------------------------------------------------------------------

    def load_results(self):
        """The saved results.  4 or 5 fields are both read, so an older TRuffle sharing
        the file keeps working (D29)."""
        results = Results()
        for line in self._read("status"):
            parts = line.rstrip("\n").split("\t")
            if len(parts) not in (4, 5) or parts[1] not in KINDS or parts[2] not in CHECKED_STATES:
                continue
            host, kind, state, stamp = parts[:4]
            try:
                stamp = float(stamp)
            except ValueError:
                continue
            if stamp >= (results.taken(kind, host) or 0):
                results.set(kind, host, state, stamp, parts[4].strip() if len(parts) == 5 else "")
        return results

    def save_results(self, results):
        """Merge our results into the saved ones - newest wins, another TRuffle or a tmux
        pane may have checked other switches meanwhile - and write them back."""
        with self._locked():
            merged = self.load_results()
            merged.merge_newer(results)
            lines = []
            for kind, host, state, when, detail in sorted(merged.entries()):
                row = [host, kind, state, "%d" % when]
                detail = clean(detail)
                lines.append("\t".join(row + [detail] if detail else row))   # 4 fields when empty
            self._write("status", lines)

    # -- terminal servers -----------------------------------------------------------

    def console_choice(self, key):
        """([lines], switch login, server login) you used last on this terminal server, or
        ([], "radius", "radius").  Only a suggestion: lines get re-cabled, so the dialog
        always lets you change it.  A line is `server TAB lines TAB login [TAB server
        login]`, lines space-separated ("12" before D51, no server login before D54)."""
        for row in reversed(self._read("console")):
            parts = row.rstrip("\n").split("\t")
            if len(parts) == 3:
                parts.append("radius")
            numbers = parts[1].split() if len(parts) == 4 else []
            if (numbers and parts[0] == key and all(n.isdigit() for n in numbers)
                    and parts[2] in CONSOLE_MODES and parts[3] in SERVER_MODES):
                return [int(n) for n in numbers], parts[2], parts[3]
        return [], "radius", "radius"

    def save_console_choice(self, key, lines, mode, server_mode="radius"):
        with self._locked():
            rows = [row.rstrip("\n") for row in self._read("console") if row.split("\t", 1)[0] != key]
            entry = "%s\t%s\t%s\t%s" % (key, " ".join(str(n) for n in lines), mode, server_mode)
            self._write("console", (rows + [entry])[-self.MAX_CONSOLE:])

    # -- your own devices (D55) -----------------------------------------------------

    def load_saved(self):
        """[(host, name, user or None)] in the order you saved them; a row TRuffle cannot
        use is skipped, never fixed up."""
        out = []
        for row in self._read("saved"):
            parts = [clean(p) for p in row.rstrip("\n").split("\t")]
            if len(parts) not in (2, 3) or not parts[1] or typed_target(parts[0]) != (None, parts[0]):
                continue
            user = parts[2] if len(parts) == 3 and parts[2] else None
            if user is not None and typed_target("%s@%s" % (user, parts[0])) is None:
                continue
            out.append((parts[0], parts[1], user))
        return out

    def save_device(self, host, name, user=None):
        """Add one - a device saved before under the same name is replaced."""
        with self._locked():
            rows = [r for r in (r.rstrip("\n") for r in self._read("saved")) if r.split("\t")[1:2] != [name]]
            entry = "\t".join([host, clean(name)] + ([user] if user else []))
            self._write("saved", (rows + [entry])[-self.MAX_SAVED:])

    def forget_device(self, name):
        with self._locked():
            self._write("saved", [r.rstrip("\n") for r in self._read("saved")
                                  if r.rstrip("\n").split("\t")[1:2] != [name]])

    # -- a wrong password seen by a tmux pane: TRuffle then wipes its copy (D26) --------

    def note_auth_failure(self, host):
        # sub-second: a pane can fail in the same second the password was typed
        self._write("authfail", ["%.3f\t%s" % (time.time(), host)])

    def load_auth_failure(self):
        """(time, host) of the last login failure reported by a pane, or (0, "")."""
        for line in self._read("authfail"):
            stamp, _, host = line.rstrip("\n").partition("\t")
            try:
                return float(stamp), host
            except ValueError:
                pass
        return 0.0, ""
