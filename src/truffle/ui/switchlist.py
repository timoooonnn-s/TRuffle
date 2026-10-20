"""The main list as data: what is loaded, searched, sorted, marked and selected.
No curses here - App draws it and feeds it keys."""

from ..inventory import DataError, build_devices, data_issues, read_table
from ..results import KINDS, STATUS_COLUMNS
from ..search import default_order, filter_devices
from ..sorting import next_sort, sort_devices


class SwitchList(object):

    def __init__(self, cfg, store, results):
        self.cfg, self.store, self.results = cfg, store, results
        self.loaded = []               # CSV order, used when sorting is switched off
        self.devices = []              # sorted
        self.view = []                 # sorted and searched: what is on screen
        self.columns = list(cfg.columns)
        self.widths = []
        self.fields = {}               # lower-case header / label -> CSV header (for field:value)
        self.issues = []
        self.load_error = None
        self.found = {}                # device -> (score, {column: positions}) of fuzzy words
        self.query = ""
        self.sort_col, self.sort_desc = None, False
        self.cursor = 0
        # device key -> True, in the order you marked them.  A dict, not a set: the order
        # decides the pane order, and marks survive a new search (see marked_devices).
        self.marked = {}

    # -- loading ----------------------------------------------------------------

    def load(self):
        """(Re)read the switch list.  Returns the warnings worth a message (a list)."""
        keep = self.selected()
        warns = []
        try:
            report = {}
            headers, rows = read_table(self.cfg.data, report)
            devices, columns, warns, picked = build_devices(headers, rows, self.cfg)
        except DataError as e:
            self.load_error = str(e)
            self.loaded = []
        else:
            self.load_error = None
            self.loaded, self.columns = devices, columns
            self.fields = dict((h.lower(), h) for h in headers)
            self.fields.update((label.lower(), h) for h, label in columns)
            self.issues = data_issues(devices, report["lines"], report["issues"], picked["name"])
        self.widths = [min(40, max([len(label) + 2] + [len(d.cells[i]) for d in self.loaded]))
                       for i, (_, label) in enumerate(self.columns)]
        self.widths += [width for _, width, _ in STATUS_COLUMNS]
        if keep is not None:
            keep = next((d for d in self.loaded if d.host == keep.host and d.name == keep.name), None)
        self.apply_sort(keep)
        return warns

    # -- what is shown ------------------------------------------------------------

    def ncols(self):
        return len(self.columns) + len(STATUS_COLUMNS)

    def selected(self):
        return self.view[self.cursor] if 0 <= self.cursor < len(self.view) else None

    def column_states(self):
        """One {host: state} per status column, in STATUS_COLUMNS order."""
        return [self.results.states[kind] for kind in KINDS]

    def apply_sort(self, keep=None):
        self.devices = sort_devices(self.loaded, self.sort_col, self.sort_desc, self.column_states())
        self.refilter(keep)

    def refilter(self, keep=None):
        keep = keep or self.selected()
        self.found = {}
        view = filter_devices(self.devices, self.query, self.fields, self.results.states,
                              self.store.favorites, self.store.recent, self.found, marked=self.marked)
        if self.sort_col is None:
            view = default_order(view, self.query, self.store.favorites, self.store.recent, self.found)
        self.view = view
        self.cursor = next((i for i, d in enumerate(view) if d is keep), 0)

    def set_query(self, query):
        self.query = query
        self.refilter()

    def set_sort(self, col, desc=None):
        """col None = original order.  Without desc: ascending -> descending -> off.
        Returns False for a column that does not exist."""
        if col is not None and col >= self.ncols():
            return False
        if desc is None:
            self.sort_col, self.sort_desc = next_sort(self.sort_col, self.sort_desc, col)
        else:
            self.sort_col, self.sort_desc = col, desc
        self.apply_sort()
        return True

    def status_changed(self, keep=None, force=False):
        """New ping / ssh results: keep a status sort and ping: / ssh: searches up to
        date.  force also covers is:recent and favourites after a session."""
        if self.sort_col is not None and self.sort_col >= len(self.columns):
            self.apply_sort(keep)                       # includes a refilter
        elif force or "ping:" in self.query.lower() or "ssh:" in self.query.lower():
            self.refilter(keep)

    def move(self, delta):
        self.cursor = max(0, min(len(self.view) - 1, self.cursor + delta))

    def move_to(self, index):
        self.cursor = max(0, min(len(self.view) - 1, index))

    # -- marks --------------------------------------------------------------------

    def marked_devices(self):
        """Every marked switch in marking order - NOT filtered by the search, so a
        selection can be collected over several searches (D34)."""
        first = {}
        for d in self.loaded:
            first.setdefault(d.key, d)
        return [first[key] for key in self.marked if key in first]

    def toggle_mark(self, dev):
        if dev.key in self.marked:
            del self.marked[dev.key]
        else:
            self.marked[dev.key] = True
