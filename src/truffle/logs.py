"""Session logs (what a switch showed you), the debug log (what happened around a login),
and finding them again.  Every file is created 0600 in a 0700 folder (D8)."""

import os
import re
import shlex
import stat
import time

from .session import EscapeStripper


# What session_log_path names a file - the only files the cleanup ever deletes.
SESSION_LOG_NAME = re.compile(r"^[0-9]{8}-[0-9]{6}_[A-Za-z0-9_.-]+\.log$")
DEBUG_LOG_MAX = 1 << 20      # debug.log is support data: over 1 MB it moves to debug.log.1


def session_log_path(cfg, name, host):
    """Where a new session log goes; creates the 0700 log folder.  Raises OSError."""
    os.makedirs(cfg.log_dir, mode=0o700, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", name or host)[:60]
    return os.path.join(cfg.log_dir, "%s_%s.log" % (time.strftime("%Y%m%d-%H%M%S"), safe))


def log_header(name, host, user):
    return "# TRuffle session log: %s (%s) as %s, %s\n" % (name, host, user, time.strftime("%Y-%m-%d %H:%M:%S"))


def open_log_file(path):
    """Open (or create, 0600) a log file for appending.  O_NOFOLLOW: never through a symlink."""
    return os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600), "ab")


class SessionLog(object):
    """--log: one 0600 log file for one session; written by run_session."""

    def __init__(self, cfg, name, host, user):
        self.path = session_log_path(cfg, name, host)
        self.file = open_log_file(self.path)
        try:
            self.file.write(log_header(name, host, user).encode("utf-8"))
        except OSError:
            self.file.close()
            raise

    def write(self, data):
        self.file.write(data)

    def flush(self):
        self.file.flush()

    def close(self):
        self.file.close()


def open_session_log(cfg, name, host, user):
    """Returns (SessionLog or None, error text or None)."""
    try:
        return SessionLog(cfg, name, host, user), None
    except OSError as e:
        return None, "cannot write session log: %s" % e


def log_sink(path, header):
    """`truffle --log-sink FILE HEADER` (tmux pipe-pane): header, then stdin without escape
    sequences, into FILE (0600).  tmux pipes what a pane SHOWS, never what is typed."""
    try:
        out = open_log_file(path)
    except OSError:
        return 1
    strip = EscapeStripper()
    with out:
        out.write(header.encode("utf-8"))
        for chunk in iter(lambda: os.read(0, 65536), b""):
            out.write(strip.feed(chunk))
            out.flush()
        out.write(strip.flush())
    return 0


def write_debug_report(cfg, name, host, argv, password, result):
    """--debug: append this login's command, events and output BEFORE the login to
    debug.log (0600) - never the password, never the session.  Returns an error or None."""
    lines = [
        "=== %s  %s (%s)" % (time.strftime("%Y-%m-%d %H:%M:%S"), name, host),
        "command      : %s" % " ".join(shlex.quote(a) for a in argv),
        "password     : %s" % ("stored, TRuffle types it" if password else "none stored, you type it"),
    ] + ["event        : %s" % e for e in result.events] + [
        "exit code    : %s   session started: %s   failed: %s   auth failed: %s   host key changed: %s" % (
            result.exit_code, result.started, result.failed, result.auth_failed, result.hostkey_changed),
        "last line    : %s" % result.last_line,
        "before login :",
    ] + ["  | " + line for line in result.pre_login.strip("\n").split("\n")[-40:]] + [""]
    path = cfg.debug_log
    try:
        os.makedirs(cfg.state_dir, mode=0o700, exist_ok=True)
        rotate_debug_log(path)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return None
    except OSError as e:
        return "cannot write %s: %s" % (path, e.strerror or e)


def rotate_debug_log(path, limit=DEBUG_LOG_MAX):
    """debug.log over `limit` becomes debug.log.1 (replacing the previous one), so it never
    grows without end - one rotation is plenty for a support file (D50)."""
    try:
        if os.lstat(path).st_size > limit:
            os.replace(path, path + ".1")
    except FileNotFoundError:
        pass


def prune_logs(cfg, now=None):
    """Delete the session logs nobody has written to for log_keep_days (D50; 0 = never).
    Only files named like a session log, directly in log_dir, plain files (a symlink is left
    alone); a log a running tmux pane still writes is fresh and stays.  A log you want to
    keep goes out of the folder.  Returns (deleted, error text or None)."""
    if not cfg.log_keep_days:
        return 0, None
    cutoff = (time.time() if now is None else now) - cfg.log_keep_days * 86400
    try:
        names = os.listdir(cfg.log_dir)
    except FileNotFoundError:
        return 0, None
    except OSError as e:
        return 0, "cannot clean up %s: %s" % (cfg.log_dir, e.strerror or e)
    deleted, error = 0, None
    for name in names:
        if not SESSION_LOG_NAME.match(name):
            continue
        path = os.path.join(cfg.log_dir, name)
        try:
            st = os.lstat(path)
            if stat.S_ISREG(st.st_mode) and st.st_mtime < cutoff:
                os.unlink(path)
                deleted += 1
        except OSError as e:
            error = "cannot delete the old log %s: %s" % (path, e.strerror or e)
    return deleted, error


def keep_text(cfg):
    if not cfg.log_keep_days:
        return "kept forever (log_keep_days = 0)"
    return "deleted after %d days without a change (log_keep_days)" % cfg.log_keep_days


def log_note(result):
    """' - session log NAME' for the footer: the file name only, Ctrl-G f has the path."""
    if not result.log_path:
        return ""
    return " - session log %s (Ctrl-G f: full path)" % os.path.basename(result.log_path)


def logs_since(cfg, since):
    """Session logs (panes' too) and the debug log written since `since`, oldest first."""
    candidates = [cfg.debug_log]
    try:
        candidates += [os.path.join(cfg.log_dir, n) for n in os.listdir(cfg.log_dir) if n.endswith(".log")]
    except OSError:
        pass
    found = []
    for path in candidates:
        try:
            mtime = os.stat(path).st_mtime
        except OSError:
            continue
        if mtime >= since:
            found.append((mtime, path))
    return [path for _, path in sorted(found)]


def list_logs(cfg, newest=10):
    """truffle --logs: where the logs are, and the newest ones - from any shell."""
    print("session logs : %s  (%s)" % (cfg.log_dir, "on" if cfg.session_log else "off unless --log / Ctrl-G l"))
    print("debug log    : %s" % cfg.debug_log)
    print("old logs     : %s" % keep_text(cfg))
    files = logs_since(cfg, 0)[-newest:]
    if files:
        print("newest       :")
        for path in files:
            print("  %s" % path)
    else:
        print("newest       : none yet")
    return 0
