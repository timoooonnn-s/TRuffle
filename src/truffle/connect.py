"""One ssh attempt outside curses - from the main screen or inside a tmux pane - and
the ONE place that turns its outcome into the SSH column, the reason and the history."""

import os
import subprocess
import time

from .console import MODE_TEXT, ConsoleLogin
from .logs import open_session_log, write_debug_report
from .results import SSH_FAILED, SSH_OK
from .session import SSH_FAILURE, build_ssh_argv, run_session
from .terminal import write


def ssh_failure_reason(result):
    """Why an attempt failed, short enough for details and a ticket (D28)."""
    if result.hostkey_changed:
        return "host key changed - not connected"
    if result.auth_failed:
        return "login refused (wrong password?)"
    if result.cancelled:
        return "cancelled while connecting (exit %s)" % result.exit_code
    line = result.last_line                      # already cleaned by run_session
    m = SSH_FAILURE.search(line)
    if m:
        return "%s (exit %s)" % (line[max(0, m.start() - 40):][:120].strip(), result.exit_code)
    if line:
        return "%s (exit %s)" % (line[:120], result.exit_code)
    return "exit code %s" % result.exit_code


def attempt_outcome(result):
    """(state, reason) of one ssh attempt for the SSH column.  A refused password and a
    changed host key are failures too: you did not get in."""
    if result.failed or result.hostkey_changed or result.auth_failed:
        return SSH_FAILED, ssh_failure_reason(result)
    return SSH_OK, ""


def record_attempt(store, results, host, key, result):
    """Put one attempt into `results` and the shared status file, and into the history
    when it got in.  Returns (state, reason)."""
    state, reason = attempt_outcome(result)
    results.set("ssh", host, state, time.time(), reason)
    store.save_results(results)
    if state == SSH_OK:
        store.touch(key)
    return state, reason


def remove_host_key(host, known_hosts):
    """ssh-keygen -R; returns (removed, output).  ssh-keygen exits 0 even when
    the host was not in the file, so that case is detected from its output."""
    try:
        proc = subprocess.run(["ssh-keygen", "-R", host, "-f", known_hosts], stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except OSError as e:
        return False, "cannot run ssh-keygen: %s" % e
    output = proc.stdout.decode("utf-8", "replace").strip()
    if proc.returncode != 0 or "not found" in output:
        return False, output or "ssh-keygen exit code %d" % proc.returncode
    return True, output


def ssh_flow(cfg, name, host, user, password, notes, record, back="return to TRuffle", console=None):
    """Connect, offering to replace a changed host key; returns the last SessionResult.
    record(result) runs after every attempt BEFORE any question - a pane killed while it
    waits must not lose it (D45).  console: makes a fresh ConsoleLogin per attempt."""
    key_removed = False
    while True:
        argv = build_ssh_argv(cfg, user, host, inject_password=bool(password))
        login = console() if console else None
        if login is None:
            notes.say("Connecting to %s (%s) as %s" % (name, host, user),
                      "log out to %s, ~. force-disconnects" % back)
        else:
            notes.say("Connecting to %s (%s) as %s" % (name, host, user),
                      "switch login: %s" % MODE_TEXT[login.mode],
                      "log out of the switch FIRST, then %s to %s" % (ConsoleLogin.EXIT_NAME, back),
                      "(%s while logged in leaves the console logged in for the next person)"
                      % ConsoleLogin.EXIT_NAME)
        write("\r\n\r\n")
        log = None
        if cfg.session_log:
            log, error = open_session_log(cfg, name, host, user)
            if error:
                notes.say(error)
        try:
            result = run_session(argv, password, log, console=login)
        finally:
            if log is not None:
                log.close()
        result.log_path = log.path if log is not None else None
        if cfg.debug:
            error = write_debug_report(cfg, name, host, argv, password, result)
            if error:
                notes.say(error)
        record(result)
        if not result.hostkey_changed or result.auth_failed:
            return result
        known_hosts = result.known_hosts or os.path.join(os.path.expanduser("~"), ".ssh", "known_hosts")
        if key_removed:
            notes.ask("The host key is still reported as changed.",
                      "Please check %s by hand." % known_hosts, "Press any key to %s ..." % back)
            return result
        answer = notes.ask("The host key of %s (%s) has CHANGED." % (name, host),
                           "Expected if the switch was replaced - otherwise do NOT continue.",
                           "Remove the old key from %s and connect again? [y/N] " % known_hosts)
        if answer not in (b"y", b"Y"):
            return result
        removed, text = remove_host_key(host, known_hosts)
        write(text.replace("\n", "\r\n") + "\r\n")
        if not removed:
            notes.ask("Could not remove the old key.", "Press any key to %s ..." % back)
            return result
        key_removed = True


def pause_on_failure(notes, name, result, back):
    """Keep a failure's error on screen until a key (D5) - unless the password was refused,
    the host key was asked about, or you pressed Ctrl-C."""
    if result.failed and not (result.auth_failed or result.hostkey_changed or result.cancelled):
        notes.ask("Connection to %s ended (exit code %d)." % (name, result.exit_code),
                  "Press any key to %s ..." % back)
