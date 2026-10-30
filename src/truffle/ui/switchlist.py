"""The main list as data: what is loaded, searched, sorted, marked and selected.
No curses here - App draws it and feeds it keys."""

from ..inventory import IPV4_LIKE, DataError, Device, build_devices, data_issues, read_table, typed_target
from ..results import KINDS, STATUS_COLUMNS
from ..search import Fields, default_order, filter_devices
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
        self.headers, self.delimiter = [], ";"     # of the CSV, for the export
        self.picked = {"name": "Name", "host": "IP"}     # the name and address columns
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
            # Your own devices and a typed address still work without the list (D55).
            self.load_error = str(e)
            self.columns, self.picked = [("Name", "Name"), ("IP", "IP")], {"name": "Name", "host": "IP"}
            self.fields = Fields(["Name", "IP"], self.columns)
            self.loaded = []
        else:
            self.load_error = None
            self.loaded, self.columns, self.picked = devices, columns, picked
            self.headers, self.delimiter = headers, report["delimiter"]
            self.fields = Fields(headers, columns)
            self.issues = data_issues(devices, report["lines"], report["issues"], picked["name"])
        self.loaded += [self.make_device(name, host, "saved", user) for host, name, user in self.store.load_saved()]
        self.measure()
        if keep is not None:
            keep = next((d for d in self.loaded if d.host == keep.host and d.name == keep.name), None)
        self.apply_sort(keep)
        return warns

    def measure(self):
        self.widths = [min(40, max([len(label) + 2] + [len(d.cells[i]) for d in self.loaded]))
                       for i, (_, label) in enumerate(self.columns)]
        self.widths += [width for _, width, _ in STATUS_COLUMNS]

    def add_saved(self, host, name, user):
        """A typed address was just saved: it joins the list, found by its name."""
        dev = self.make_device(name, host, "saved", user)
        self.loaded.append(dev)
        self.measure()
        self.query = name
        self.apply_sort(dev)
        return dev

    def remove_saved(self, dev):
        self.loaded = [d for d in self.loaded if d is not dev]
        self.marked.pop(dev.key, None)
        self.measure()
        self.apply_sort()

    def make_device(self, name, host, origin, user=None):
        """A device that is not in the CSV: your saved one, or the address you typed."""
        values = {self.picked["name"]: name, self.picked["host"]: host}
        return Device(values, host, name, [values.get(h, "") for h, _ in self.columns], origin, user)

    def typed_device(self, view):
        """The search as an address to connect to, or None (D55): a whole IPv4 address
        that no device has (it may still be part of one: 10.1.2.3 in 10.1.2.30), a
        hostname nothing matches, or anything with user@ in front."""
        target = typed_target(self.query)
        if target is None:
            return None
        user, host = target
        if user is None and not IPV4_LIKE.match(host) and view:
            return None
        if any(d.host.lower() == host.lower() and d.user == user for d in self.loaded):
            return None                          # there it is already: that row is the one
        return self.make_device("%s@%s" % (user, host) if user else host, host, "typed", user)

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
                              self.store.recent, self.found, marked=self.marked)
        if self.sort_col is None:
            view = default_order(view, self.query, self.store.recent, self.found)
        typed = self.typed_device(view)
        if typed is not None:
            if keep is not None and keep.origin == "typed" and keep.name == typed.name:
                typed = keep                    # the same row: a refresh keeps it selected
            view.insert(0, typed)
        self.view = view
        self.cursor = next((i for i, d in enumerate(view) if d is keep), 0)

    def set_query(self, query):
        self.query = query
        self.refilter()
        if self.view and self.view[0].origin == "typed":
            self.cursor = 0        # what you just typed - never the 10.1.2.30 that was selected

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
        date.  force also covers is:recent after a session."""
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
