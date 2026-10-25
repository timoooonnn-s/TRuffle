"""Ctrl-E: the devices on screen and their results as a CSV in your home folder (D50) -
the dead-host list for the IPAM owners.  Every CSV column, then PING / SSH with when they
were taken and why ssh failed.  0600, never over an existing file, with a BOM so Excel
opens the umlauts right, in the switch list's own delimiter."""

import csv
import glob
import os
import time

EXTRA_HEADERS = ["Ping", "Ping checked", "SSH last try", "SSH tried", "SSH reason"]
PREFIX = "truffle-export-"
# Excel runs a cell that starts with one of these as a formula.  The CSV comes from the
# IPAM and the ssh reason from a switch's output, so neither is trusted (Warden).  "-" is
# left alone: it is the usual "empty" in an inventory, and Excel shows "-x" as text.
FORMULA_START = ("=", "+", "@")


def export_folder():
    return os.path.expanduser("~")


def export_path(folder=None, now=None):
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(now))
    return os.path.join(folder or export_folder(), "%s%s.csv" % (PREFIX, stamp))


def safe_cell(value):
    return "'" + value if value.startswith(FORMULA_START) else value


def when(stamp):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(stamp)) if stamp else ""


def export_csv(path, devices, headers, delimiter, results):
    """Write devices to a NEW file at path (path-2.csv, path-3.csv, ... if it exists).
    Returns the path actually written.  Raises OSError."""
    base, ext = os.path.splitext(path)
    n = 1
    while True:
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            break
        except FileExistsError:
            n += 1
            path = "%s-%d%s" % (base, n, ext)
    with os.fdopen(fd, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=delimiter)
        writer.writerow(list(headers) + EXTRA_HEADERS)
        for d in devices:
            row = [d.values.get(h, "") for h in headers] + [
                results.get("ping", d.host) or "", when(results.taken("ping", d.host)),
                results.get("ssh", d.host) or "", when(results.taken("ssh", d.host)),
                results.why("ssh", d.host)]
            writer.writerow([safe_cell(v) for v in row])
    return path


def exports_since(since, folder=None):
    """The exports written since `since` - listed with the log files when TRuffle exits."""
    found = []
    for path in glob.glob(os.path.join(folder or export_folder(), PREFIX + "*.csv")):
        try:
            if os.stat(path).st_mtime >= since:
                found.append(path)
        except OSError:
            pass
    return sorted(found)
