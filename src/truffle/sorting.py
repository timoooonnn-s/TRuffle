"""Sorting the switch list by a column: F1, F2, ... (ascending -> descending -> off)."""

import re

from .results import STATUS_RANK


def natural_key(text):
    """'sw2' < 'sw10', '10.0.1.2' < '10.0.1.10'."""
    key = []
    for i, part in enumerate(re.split(r"([0-9]+)", text.lower())):
        if i % 2:
            key.append((0, int(part), ""))
        elif part:
            key.append((1, 0, part))
    return key


def next_sort(sort_col, sort_desc, col):
    """Pressing a column's sort key: ascending -> descending -> off (original order)."""
    if sort_col != col:
        return col, False
    if not sort_desc:
        return col, True
    return None, False


def sort_devices(devices, col, desc, status=()):
    """col indexes the visible columns, then the status columns (status holds one
    {host: state} per status column; problems sort first).  Empty values always go last."""
    if col is None or not devices:
        return list(devices)
    if col >= len(devices[0].cells):
        states = status[col - len(devices[0].cells)]

        def value(d):
            return states.get(d.host, "")
        key = lambda d: STATUS_RANK.get(value(d), 9)
    else:
        def value(d):
            return d.cells[col]
        key = lambda d: natural_key(value(d))
    filled = [d for d in devices if value(d) != ""]
    empty = [d for d in devices if value(d) == ""]
    return sorted(filled, key=key, reverse=desc) + empty
