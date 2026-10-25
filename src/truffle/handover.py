"""Handing the login to tmux panes without a command line ever carrying it: each pane gets
a one-time ticket and fetches the login over a Unix socket in a 0700 directory, answered
only for our uid and the exact process tmux started (TMUX-SECURITY.md, D23)."""

import json
import os
import secrets
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time

MAX_CLIENTS = 11
TICKET_LIFETIME = 15                     # seconds: a pane fetches its login immediately


def peer_identity(conn):
    """(uid, pid) of the other end of a Unix socket, from the kernel.  Linux: SO_PEERCRED,
    macOS: LOCAL_PEERCRED + LOCAL_PEERPID.  (None, None) elsewhere - the caller refuses."""
    try:
        if sys.platform.startswith("linux"):
            pid, uid, _ = struct.unpack("3i", conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED,
                                                              struct.calcsize("3i")))
            return uid, pid
        if sys.platform == "darwin":
            sol_local, peercred, peerpid = 0, 0x001, 0x002
            xucred = conn.getsockopt(sol_local, peercred, 100)        # version, uid, ...
            uid = struct.unpack("2I", xucred[:8])[1]
            pid = struct.unpack("i", conn.getsockopt(sol_local, peerpid, 4))[0]
            return uid, pid
    except (OSError, struct.error):
        pass
    return None, None


def parent_pid(pid):
    """The parent of pid, or None (a shell may not exec the pane command).
    Linux: /proc/<pid>/stat; macOS: ps."""
    try:
        if sys.platform.startswith("linux"):
            with open("/proc/%d/stat" % pid, encoding="utf-8", errors="replace") as f:
                return int(f.read().rsplit(")", 1)[1].split()[1])
        out = subprocess.run(["ps", "-o", "ppid=", "-p", str(pid)], stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, timeout=5).stdout
        return int(out.strip() or 0) or None
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return None


class Handover(object):
    """A ticket is answered once: our uid, the process tmux started for it, younger than
    TICKET_LIFETIME.  A console pane's ticket also carries the login for the switch behind
    the terminal server (D51) - only that ticket, never an ssh pane's."""

    def __init__(self, credentials, switch_credentials=None):
        self.credentials = credentials        # callable -> (user, password or None)
        self.switch_credentials = switch_credentials    # callable -> (user or None, password or None)
        self.dir = tempfile.mkdtemp(prefix="truffle-", dir=os.environ.get("XDG_RUNTIME_DIR") or None)
        self.path = os.path.join(self.dir, "handover.sock")
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        old = os.umask(0o177)
        try:
            self.server.bind(self.path)       # 0600, inside a 0700 directory
        finally:
            os.umask(old)
        self.server.listen(MAX_CLIENTS)
        self.tickets = {}                     # ticket -> {host, pid, created, fetched}
        self.refused = []                     # connections we turned away, shown to the user
        self.lock = threading.Lock()
        self.closed = False
        threading.Thread(target=self._serve, daemon=True).start()

    def issue(self, host, switch=False):
        """A ticket for one pane.  bind() must follow once tmux reports the pane's pid.
        switch: a console pane - its answer includes the switch login."""
        ticket = secrets.token_hex(16)
        with self.lock:
            self.tickets[ticket] = {"host": host, "pid": None, "created": time.time(), "fetched": False,
                                    "switch": switch}
        return ticket

    def bind(self, ticket, pid):
        with self.lock:
            if ticket in self.tickets:
                self.tickets[ticket]["pid"] = pid

    def _serve(self):
        while True:
            try:
                conn, _ = self.server.accept()
            except OSError:
                return                        # closed
            # one thread per connection: a client that connects and then says nothing
            # must not keep the other panes waiting for their login
            threading.Thread(target=self._client, args=(conn,), daemon=True).start()

    def _client(self, conn):
        with conn:
            try:
                conn.settimeout(3)
                conn.sendall(self._handle(conn).encode("utf-8") + b"\n")
            except (OSError, ValueError, TypeError, struct.error):
                pass

    def _refuse(self, why, answer):
        with self.lock:
            self.refused.append(why)
        return answer

    def _handle(self, conn):
        uid, pid = peer_identity(conn)
        if uid is None or uid != os.getuid():
            return self._refuse("connection from uid %s" % uid, "ERR refused")
        request = conn.recv(4096).decode("utf-8", "replace").strip()
        kind, _, ticket = request.partition(" ")
        ticket = ticket.strip()
        if kind != "GET":
            return "ERR refused"
        with self.lock:
            entry = self.tickets.get(ticket)
            if entry is None:
                return "ERR unknown ticket"
            if entry["fetched"]:
                self.refused.append("ticket for %s used twice" % entry["host"])
                return "ERR already used"
            if time.time() - entry["created"] > TICKET_LIFETIME:
                return "ERR ticket expired"
            expected, host, switch = entry["pid"], entry["host"], entry["switch"]
        # An unbound ticket is refused, never waited for (D29).  Outside the lock: the
        # parent lookup runs `ps` on macOS.
        if pid != expected and parent_pid(pid) != expected:    # ps only when it is needed
            return self._refuse("pid %s is not the pane for %s" % (pid, host), "ERR wrong process")
        with self.lock:
            entry = self.tickets.get(ticket)
            if entry is None or entry["fetched"]:     # checked again: single use must be exact
                return "ERR already used"
            entry["fetched"] = True
        user, password = self.credentials()
        login = {"user": user, "password": password or ""}
        if switch and self.switch_credentials is not None:
            switch_user, switch_password = self.switch_credentials()
            login.update(switch_user=switch_user or "", switch_password=switch_password or "")
        return "OK " + json.dumps(login)

    @property
    def pending(self):
        with self.lock:
            return any(not e["fetched"] for e in self.tickets.values())

    def wait(self, deadline=TICKET_LIFETIME):
        """Give the panes their short window to fetch the login.  Returns True if all
        of them did; after this the socket is no longer needed."""
        end = time.time() + deadline
        while self.pending and time.time() < end:
            time.sleep(0.05)
        return not self.pending

    def take_refusals(self):
        with self.lock:
            refused, self.refused = self.refused, []
        return refused

    def close(self):
        """Stop listening and remove the socket; panes that still hold a ticket can no
        longer fetch a login (they ask the user instead) and cannot report back."""
        if self.closed:
            return
        self.closed = True
        try:
            self.server.close()
        except OSError:
            pass
        shutil.rmtree(self.dir, ignore_errors=True)      # the socket and its 0700 directory


def handover_request(path, line):
    """The pane's side: send one request line, return the answer line."""
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.settimeout(5)
    try:
        conn.connect(path)
        conn.sendall(line.encode("utf-8") + b"\n")
        answer = b""
        while not answer.endswith(b"\n") and len(answer) < 65536:
            chunk = conn.recv(4096)
            if not chunk:
                break
            answer += chunk
        return answer.decode("utf-8", "replace").strip()
    finally:
        conn.close()
