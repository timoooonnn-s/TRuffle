"""The switch list: a CSV file -> Device objects, plus the plausibility check."""

import csv
import io
import os
import re

from . import INSTALL_DIR

CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
IPV4_LIKE = re.compile(r"^[0-9.]+$")
HOST_RE = re.compile(r"^[A-Za-z0-9_.:%-]+$")
# Where a search word may be split (see search.anchored_positions).
BOUNDARY = " -_./:@"


class DataError(Exception):
    pass


def clean(value):
    """A CSV value as text for the screen: control characters become spaces."""
    return CONTROL_CHARS.sub(" ", value or "").strip()


def valid_host(host):
    """Hosts come from a shared CSV: never let one look like a command line option."""
    return bool(host) and len(host) <= 253 and not host.startswith("-") and HOST_RE.match(host) is not None


def segments_of(text):
    """The text cut at the separators, as (offset, part) - 'ab-12-s34' becomes
    (0,'ab') (3,'12') (6,'s34').  A search word may only jump between these."""
    parts, start = [], 0
    for i, ch in enumerate(text):
        if ch in BOUNDARY:
            if i > start:
                parts.append((start, text[start:i]))
            start = i + 1
    if len(text) > start:
        parts.append((start, text[start:]))
    return parts


class Device(object):
    """One row of the switch list.  The lower-case cells and their segments are worked
    out once here, so the search does no per-keystroke preparation."""
    __slots__ = ("values", "host", "name", "cells", "lcells", "lsegments", "search")

    def __init__(self, values, host, name, cells):
        self.values = values                  # every CSV column, header -> value
        self.host = host                      # the ssh / ping target
        self.name = name                      # the switch name, or the host without one
        self.cells = cells                    # the visible columns, in table order
        self.lcells = [c.lower() for c in cells]
        self.lsegments = [segments_of(c) for c in self.lcells]
        self.search = "\x00".join(self.lcells)          # \x00: a word never matches across two columns

    @property
    def key(self):
        """Identity for favourites, history and marks - the seam between who a switch is
        and how it is displayed (D30 was an identity bug)."""
        return self.name or self.host


def read_text(path):
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as e:
        raise DataError("cannot read %s: %s" % (path, e.strerror or e))
    # UTF-8 (with or without BOM) first, then what Excel on Windows writes.  latin-1
    # last: cp1252 cannot decode five byte values.
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            pass
    return raw.decode("latin-1")


def detect_delimiter(header_line):
    best, count = ";", 0
    for d in (";", ",", "\t", "|"):
        c = header_line.count(d)
        if c > count:
            best, count = d, c
    return best


def read_table(path, report=None):
    """(headers, rows of {header: value}); the delimiter is guessed from the header line,
    blank and '#' lines are skipped.  `report` receives the delimiter, each row's CSV
    line and field-count problems."""
    if not os.path.isfile(path):
        hint = ""
        if os.path.isfile(os.path.join(INSTALL_DIR, "data.example.csv")):
            hint = " - copy data.example.csv to data.csv to start"
        raise DataError("device list not found: %s%s" % (path, hint))
    text = read_text(path)
    first = next((line for line in text.splitlines() if line.strip()), None)
    if first is None:
        raise DataError("device list is empty: %s" % path)
    delimiter = detect_delimiter(first)
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    headers, rows = None, []
    report = {} if report is None else report
    report.update(delimiter=delimiter, lines=[], issues=[])
    try:
        for record in reader:
            if not any(cell.strip() for cell in record) or record[0].lstrip().startswith("#"):
                continue
            if headers is None:
                headers = unique_headers(record)
                continue
            rows.append(dict((h, clean(record[i]) if i < len(record) else "") for i, h in enumerate(headers)))
            report["lines"].append(reader.line_num)
            if len(record) != len(headers):
                report["issues"].append("line %d: %d fields, the header has %d%s" % (
                    reader.line_num, len(record), len(headers),
                    " (a '%s' inside a value?)" % delimiter if len(record) > len(headers) else ""))
    except csv.Error as e:
        raise DataError("%s, line %d: %s" % (path, reader.line_num, e))
    if headers is None:
        raise DataError("device list has no header line: %s" % path)
    return headers, rows


def unique_headers(record):
    """Header names, cleaned; an empty one is named columnN, a repeated one gets a '_'."""
    headers, seen = [], set()
    for i, h in enumerate(record):
        h = clean(h) or "column%d" % (i + 1)
        while h.lower() in seen:
            h += "_"
        seen.add(h.lower())
        headers.append(h)
    return headers


def find_header(headers, wanted):
    wanted = wanted.strip().lower()
    return next((h for h in headers if h.lower() == wanted), None)


def build_devices(headers, rows, cfg):
    """(devices, columns [(header, label)], warnings, picked {"name": h, "host": h}).
    The column LABELLED Name / IP in `columns` is the name / ssh target, before any header
    called so (D30) - that is what makes an Infoblox export work with one config line."""
    warns = []
    columns, by_label = [], {}
    for key, label in cfg.columns:
        h = find_header(headers, key)
        if h is None:
            warns.append("column '%s' not found in the device list" % key)
        else:
            columns.append((h, label))
            by_label.setdefault(label.strip().lower(), h)

    host_h = by_label.get("ip")
    for alt in ("ip", "host", "hostname", "address", "ip address"):
        host_h = host_h or find_header(headers, alt)
    if host_h is None:
        raise DataError("no 'IP' column in the device list (found: %s)"
                        "  - label one with  columns = <header>:IP" % ", ".join(headers))
    name_h = by_label.get("name") or find_header(headers, "name")
    if name_h is None:
        # Said out loud: silently, a SUBNET first column gave a whole subnet one identity.
        name_h = headers[0]
        warns.append("no 'Name' column: using '%s' as the device name"
                     " - set it with  columns = <header>:Name" % name_h)
    # Under two columns found: `columns` is for another list - show name and address (D32).
    if len(columns) < 2:
        if columns:
            warns.append("only %d of the configured columns exist in this list, so the table "
                         "falls back to the device name and its address - set 'columns' to "
                         "match your list" % len(columns))
        columns = [(name_h, "Name"), (host_h, "IP")]

    devices = []
    for row in rows:
        host = row.get(host_h, "")
        devices.append(Device(row, host, row.get(name_h, "") or host, [row.get(h, "") for h, _ in columns]))
    return devices, columns, warns, {"name": name_h, "host": host_h}


def name_hint(devices, name_header):
    """Which other column could be the hostname?  Guessing wrong once cost a round trip,
    so the warning names the candidates: filled in, not an address, not a date."""
    for d in devices[:20]:
        found = [h for h, v in d.values.items()
                 if v and h != name_header and " " not in v and not IPV4_LIKE.match(v)]
        if found:
            return (" Columns that do have a value here: %s. Point 'Name' at the right one:"
                    "  columns = %s:Name" % (", ".join(found[:4]), found[0]))
    return " Point 'Name' at the column that holds the hostname:  columns = <header>:Name"


def address_issue(host):
    """Why this host cannot be used as an address, or None."""
    if not host:
        return "has no IP"
    if not valid_host(host):
        return "has an unusable IP/host '%s'" % host
    if IPV4_LIKE.match(host):
        parts = host.split(".")
        if len(parts) != 4 or not all(p and int(p) <= 255 for p in parts):
            return "- '%s' is not a valid IPv4 address" % host
        if any(len(p) > 1 and p.startswith("0") for p in parts):
            return "- '%s' has leading zeros (ping may read them as octal)" % host
    return None


def data_issues(devices, lines, issues=(), name_header=None):
    """Plausibility checks for the switch list -> warnings with CSV line numbers."""
    out = list(issues)
    names, hosts, nameless = {}, {}, []
    for d, line in zip(devices, lines):
        # An empty name column shows an empty NAME cell while the switch itself falls back
        # to its IP, so the row looks half-broken without anything saying why.
        if name_header and not d.values.get(name_header, ""):
            nameless.append(line)
        problem = address_issue(d.host)
        if problem:
            out.append("line %d: '%s' %s" % (line, d.name, problem))
        names.setdefault(d.name.lower(), []).append(line)
        if d.host:
            hosts.setdefault(d.host, []).append("%s (line %d)" % (d.name, line))
    if nameless:
        out.append("%d row(s) have nothing in the name column '%s' (line%s %s%s) - their NAME "
                   "column stays empty and they fall back to the IP.%s"
                   % (len(nameless), name_header, "" if len(nameless) == 1 else "s",
                      ", ".join(str(n) for n in nameless[:8]), ", ..." if len(nameless) > 8 else "",
                      name_hint(devices, name_header)))
    for name, where in names.items():
        if len(where) > 1:
            out.append("name '%s' appears %d times: lines %s" % (name, len(where), ", ".join(map(str, where))))
    for host, who in hosts.items():
        if len(who) > 1:
            out.append("IP %s is used %d times: %s" % (host, len(who), ", ".join(who)))
    return out
