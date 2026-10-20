"""PING / SSH results: a word per host and kind, when it was taken, why ssh failed.
The SSH column is your last REAL attempt - TRuffle never probes (D20)."""

PING_UP, PING_DOWN, WAIT = "up", "down", "wait"
SSH_OK, SSH_FAILED = "ok", "failed"

# The columns after the CSV columns: (label, width, kind), wide enough for "● failed 12h".
STATUS_COLUMNS = [("Ping", 10, "ping"), ("SSH", 12, "ssh")]
KINDS = [kind for _, _, kind in STATUS_COLUMNS]
CHECKED_STATES = (PING_UP, PING_DOWN, SSH_OK, SSH_FAILED)       # results worth keeping ("wait" is not)
STATUS_RANK = {PING_DOWN: 0, SSH_FAILED: 0, PING_UP: 2, SSH_OK: 2, WAIT: 3}     # problems sort first
# A result this old is shown faded: "down" from three days ago says little about today.
STALE_SECONDS = 24 * 3600


class Results(object):
    """Results by kind and host.  `states[kind]` is {host: word} - the shape the search
    and the sort read; `checked` and `detail` are keyed by (kind, host)."""

    def __init__(self):
        self.states = dict((kind, {}) for kind in KINDS)
        self.checked = {}          # (kind, host) -> time the result was taken
        self.detail = {}           # (kind, host) -> why a ssh attempt failed

    def get(self, kind, host):
        return self.states[kind].get(host)

    def taken(self, kind, host):
        return self.checked.get((kind, host))

    def why(self, kind, host):
        return self.detail.get((kind, host), "")

    def set(self, kind, host, state, when, detail=""):
        """Record one result.  An empty detail removes an older one, so a reason never
        outlives the failure it explained."""
        self.states[kind][host] = state
        self.checked[(kind, host)] = when
        if detail:
            self.detail[(kind, host)] = detail
        else:
            self.detail.pop((kind, host), None)

    def entries(self):
        """Every kept result as (kind, host, state, time, detail).  Iterates copies: a
        batch ping's worker threads change the ping dict while this runs."""
        for kind in KINDS:
            for host, state in list(self.states[kind].items()):
                if state in CHECKED_STATES:
                    yield kind, host, state, self.checked.get((kind, host), 0), self.why(kind, host)

    def merge_newer(self, other):
        """Take every result of `other` that is at least as new as ours (another TRuffle
        window or one of our tmux panes wrote it)."""
        for kind, host, state, when, detail in other.entries():
            if when >= self.checked.get((kind, host), 0):
                self.set(kind, host, state, when, detail)

    def newest(self):
        return max(self.checked.values(), default=0)
