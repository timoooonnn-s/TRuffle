"""ping: one switch with live output, or the marked ones at once into the PING column."""

import codecs
import os
import pty
import re
import shlex
import signal
import subprocess
import sys
import threading
import time

from .inventory import CONTROL_CHARS
from .results import CHECKED_STATES, PING_DOWN, PING_UP, WAIT
from .terminal import which

# Only "time=" proves an echo reply - an ICMP error also prints "bytes from" (D32).
REPLY_RE = re.compile(r"\btime[=<]\s*[0-9]", re.IGNORECASE)

# The exit code of a ping that ran fine and heard nothing back.  Linux (iputils): 1 = no
# reply, 2 = an error.  macOS: 2 = no reply, anything else non-zero = an error.
NO_REPLY_EXIT = 2 if sys.platform == "darwin" else 1
# LC_ALL=C because the reply line is parsed - on a German server the translated output
# broke the old " bytes from " test and every switch showed "down" (D17).
PING_ENV = dict(os.environ, LC_ALL="C")


def ping_argv(host, count, timeout):
    wait = timeout * 1000 if sys.platform == "darwin" else timeout   # Linux: -W in s, macOS: in ms
    return [which("ping") or "ping", "-n", "-c", str(count), "-W", str(wait), host]


def ping_replied(text):
    """True when ping's output contains a real echo reply."""
    return REPLY_RE.search(text or "") is not None


def ping_verdict(replied, returncode, killed=False):
    """PING_UP, PING_DOWN, or None = no verdict, keep what was known (D32, D44).
    A reply is "up" whatever the exit code.  "down" only for a ping that ran to its end
    and heard nothing (macOS exits 0 on "Net Unreachable") - not one we killed (ESC) or
    one that could not run at all.  returncode None = still running."""
    if replied:
        return PING_UP
    if not killed and returncode in (0, NO_REPLY_EXIT):
        return PING_DOWN
    return None


def ping_once(host, timeout):
    """One ping -> PING_UP, PING_DOWN or None (no verdict)."""
    try:
        proc = subprocess.run(ping_argv(host, 1, timeout), stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              timeout=timeout + 5, env=PING_ENV)
    except (OSError, subprocess.SubprocessError):
        return None
    return ping_verdict(ping_replied(proc.stdout.decode("utf-8", "replace")), proc.returncode)


class BatchPing(object):
    """Pings the marked switches at once, straight into `results`.  No rate limit: it only
    covers the handful you marked (D35)."""

    MAX_THREADS = 16

    def __init__(self, hosts, timeout, results):
        self.hosts, self.timeout, self.results = hosts, timeout, results
        self.counts = {}               # PING_UP / PING_DOWN / None -> how many
        self.cancelled = self.reported = False
        self.previous = {}             # results from before, restored on cancel
        self._next = 0
        self._lock = threading.Lock()
        states = results.states["ping"]
        for host in hosts:
            if states.get(host) in CHECKED_STATES:
                self.previous[host] = states[host]
            states[host] = WAIT
        self.threads = [threading.Thread(target=self._work, daemon=True)
                        for _ in range(min(len(hosts), self.MAX_THREADS))]
        for t in self.threads:
            t.start()

    def _work(self):
        while True:
            with self._lock:
                if self.cancelled or self._next >= len(self.hosts):
                    return
                host = self.hosts[self._next]
                self._next += 1
            verdict = ping_once(host, self.timeout)
            with self._lock:
                self.counts[verdict] = self.counts.get(verdict, 0) + 1
                if self.cancelled or verdict is None:      # nobody asked any more / proves nothing
                    self._restore(host)
                else:
                    self.results.set("ping", host, verdict, time.time())

    @property
    def running(self):
        return any(t.is_alive() for t in self.threads)

    @property
    def percent(self):
        return 100 * sum(self.counts.values()) // max(1, len(self.hosts))

    def summary(self):
        text = "%d up, %d down" % (self.counts.get(PING_UP, 0), self.counts.get(PING_DOWN, 0))
        if self.counts.get(None):
            text += ", %d could not be pinged (ping failed - try one with live output)" % self.counts[None]
        return text

    def _restore(self, host):
        states = self.results.states["ping"]
        if states.get(host) == WAIT:
            if host in self.previous:
                states[host] = self.previous[host]
            else:
                del states[host]

    def cancel(self):
        with self._lock:
            self.cancelled = True
            for host in self.hosts[self._next:]:
                self._restore(host)


class ProcStream(object):
    """Runs a command in a pseudo-terminal (so its output is line buffered)
    and collects the output lines in a background thread."""

    def __init__(self, argv, env=None):
        self.lines = ["$ " + " ".join(shlex.quote(a) for a in argv), ""]
        self.partial = ""
        self.done = False
        self.returncode = None
        self.killed = False          # WE stopped it (ESC), so its exit code means nothing
        self.proc = None
        self._lock = threading.Lock()
        master = slave = None
        try:
            master, slave = pty.openpty()
            self.proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=slave, stderr=slave,
                                         start_new_session=True, env=env)
        except OSError as e:
            for fd in (master, slave):
                if fd is not None:
                    os.close(fd)
            self.lines.append("cannot run %s: %s" % (argv[0], e.strerror or e))
            self.returncode, self.done = 127, True
            return
        os.close(slave)
        self._master = master
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        decoder = codecs.getincrementaldecoder("utf-8")("replace")
        while True:
            try:
                data = os.read(self._master, 4096)
            except OSError:
                break                # Linux: EIO once the child has closed its side
            if not data:
                break
            self._feed(decoder.decode(data))
        os.close(self._master)
        rc = self.proc.wait()
        with self._lock:
            if self.partial:
                self.lines.append(self.partial)
                self.partial = ""
            self.lines += ["", "[finished, exit code %d]" % rc]
            self.returncode = rc
            self.done = True

    def _feed(self, text):
        with self._lock:
            parts = (self.partial + text.replace("\r\n", "\n")).split("\n")
            self.partial = parts.pop()
            for line in parts:
                # keep only what a terminal would show after a carriage return
                self.lines.append(CONTROL_CHARS.sub(" ", line.split("\r")[-1]).rstrip())

    def snapshot(self):
        with self._lock:
            return self.lines + ([self.partial] if self.partial else [])

    def stop(self):
        if self.proc is not None and self.proc.poll() is None:
            self.killed = True
            for sig in (signal.SIGTERM, signal.SIGKILL):
                try:
                    os.killpg(self.proc.pid, sig)
                    self.proc.wait(timeout=1)
                    break
                except (OSError, subprocess.TimeoutExpired):
                    pass


def stream_verdict(stream):
    """The verdict of a live ping once its window was closed."""
    return ping_verdict(ping_replied("\n".join(stream.snapshot())), stream.returncode, stream.killed)
