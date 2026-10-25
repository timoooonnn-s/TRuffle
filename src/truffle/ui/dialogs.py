"""The dialog windows: login, terminal-server line, settings.  Each one draws on a
Screen, reads keys until it is done and returns what was chosen - no TRuffle state."""

import textwrap

from ..config import valid_user
from ..console import console_user, parse_console_lines
from ..state import CONSOLE_MODES
from .draw import fit, put


def edit_field(text, key, keep=None, limit=None):
    """A one-line text field after one key: the new text, or None when the key is not an
    edit.  A paste adds its first line only; `keep` filters what may be typed."""
    if key == "BACKSPACE":
        return text[:-1]
    if key == "CTRL_U":
        return ""
    if key == "PASTE":
        added = key.as_text(multiline=False)
    elif key is not None and len(key) == 1:
        added = key
    else:
        return None
    added = "".join(c for c in added if keep is None or keep(c))
    return (text + added)[:limit] if limit else text + added


def login_dialog(screen, user, local_for=None, error=None, server=None):
    """Ask user + password.  Returns (user, password or None) or None on ESC.
    local_for: the terminal server name - then it asks for a switch's local account.
    server: the terminal server this RADIUS login is asked for - it always takes that
    one, there is no local login on a terminal server."""
    entry = [user or "", ""]
    field = 1 if entry[0] else 0
    scr, th, sym = screen.scr, screen.th, screen.sym
    which = ("Only the switch - the terminal server always takes RADIUS." if local_for
             else "For the terminal server %s, always RADIUS." % server if server else "")
    while True:
        bw, bh = min(66, scr.getmaxyx()[1] - 6), 14 if which else 13
        if local_for:
            y0, x0 = screen.draw_window("Local account", "switch behind %s" % local_for, bh, bw)
        elif server:
            y0, x0 = screen.draw_window("Login", "your RADIUS login", bh, bw)
        else:
            y0, x0 = screen.draw_window("Login", "asked once per session", bh, bw)
        fw = max(6, bw - 18)
        values = [entry[0], sym["mask"] * len(entry[1])]
        for i, label in enumerate(("Username", "Password")):
            y = y0 + 2 + i * 2
            active = field == i
            put(scr, y, x0 + 3, label, th.win_label if active else th.win)
            shown = values[i][-(fw - 2):]
            put(scr, y, x0 + 14, " " + shown.ljust(fw - 1), th.field if active else th.field_idle)
            if active:
                put(scr, y, x0 + 15 + len(shown), " ", th.cursor)
        if error:
            for i, line in enumerate(textwrap.wrap(sym["dot"] + " " + error, bw - 6, subsequent_indent="  ")[:2]):
                put(scr, y0 + 6 + i, x0 + 3, line, th.win_err)
        put(scr, y0 + 8, x0 + 3, ("Kept in memory only %s forgotten when TRuffle exits" % sym["sep"])[:bw - 6],
            th.win_hint)
        put(scr, y0 + 9, x0 + 3, ("Empty password: you type it at the switch" if local_for
                                  else "Empty password: ssh asks at every login")[:bw - 6], th.win_hint)
        if which:
            put(scr, y0 + 10, x0 + 3, which[:bw - 6], th.win_hint)
        screen.draw_keys(y0 + bh - 2, x0 + 3, (("Enter", "OK"), ("Tab", "next field"), ("ESC", "cancel")))
        scr.refresh()

        key = screen.read_key(-1)
        if key == "ESC":
            return None
        if key in ("TAB", "BTAB", "UP", "DOWN"):
            field = 1 - field
        elif key == "ENTER":
            if field == 0:
                field = 1
            elif not valid_user(entry[0]):
                error, field = "Please enter a valid username.", 0
            else:
                return entry[0], (entry[1] or None)
        else:
            edited = edit_field(entry[field], key)
            entry[field] = entry[field] if edited is None else edited


def console_dialog(screen, cfg, servers, mode, user, local_user, others=0):
    """Lines and switch login for one or more terminal servers (D51).  servers: [(name,
    lines text)]; others: marked devices that get an ssh pane next to them.  Digits type
    the lines ("3 7 12", "3-5"), Tab / Up / Down move between the servers, Left / Right
    choose the login.  Returns ([[line, ...] per server], mode) or None on ESC."""
    texts = [text for _, text in servers]
    field, mi, error = 0, (CONSOLE_MODES.index(mode) if mode in CONSOLE_MODES else 0), None
    scr, th, sym = screen.scr, screen.th, screen.sym
    many = len(servers) > 1
    while True:
        mode = CONSOLE_MODES[mi]
        bw = min(74, scr.getmaxyx()[1] - 6)
        bh = 12 + len(servers)
        title = "Consoles" if many else "Console"
        y0, x0 = screen.draw_window(title, "%d terminal servers" % len(servers) if many else servers[0][0], bh, bw)
        parsed = [parse_console_lines(cfg, t)[0] if t.strip() else None for t in texts]
        for i, (name, _) in enumerate(servers):
            y = y0 + 2 + i
            put(scr, y, x0 + 3, fit(name if many else "Lines", 17).rstrip(), th.win_label if i == field else th.win)
            put(scr, y, x0 + 21, " " + texts[i][-22:].ljust(23), th.field if i == field else th.field_idle)
            if i == field:
                put(scr, y, x0 + 22 + len(texts[i][-22:]), " ", th.cursor)
            if parsed[i] and len(parsed[i]) > 1:
                put(scr, y, x0 + 46, ("%d panes" % len(parsed[i]))[:bw - 49], th.win_hint)
        y = y0 + 3 + len(servers)
        # The two logins, in the order they happen; the first one is no choice (D47).
        first = next((ls[0] for ls in parsed if ls), None)
        put(scr, y, x0 + 3, "Terminal server", th.win_label)
        put(scr, y, x0 + 21, ("RADIUS, always  %s  %s" % (sym["sep"], console_user(cfg, user, first) if first
                                                         else "%s:<port>" % user))[:bw - 24], th.win_hint)
        put(scr, y + 2, x0 + 3, "Switch login", th.win_label)
        put(scr, y + 2, x0 + 21, "%s %s %s" % (sym["lt"], mode.ljust(6), sym["gt"]), th.field)
        what = {"radius": "RADIUS as well (%s), TRuffle types it" % user,
                "local": ("its local account %s, TRuffle types it" % local_user) if local_user
                         else "its local account - asked once, then kept",
                "manual": "you log in at the switch yourself"}[mode]
        put(scr, y + 3, x0 + 21, what[:bw - 24], th.win_hint)
        panes = sum(len(ls) for ls in parsed if ls) + others
        if error:
            info, attr = sym["dot"] + " " + error, th.win_err
        elif panes > 1:
            info, attr = "%d tmux panes%s, one switch login for all consoles" % (
                panes, " (%d of them ssh)" % others if others else ""), th.win_hint
        else:
            info, attr = "Line = the port on the terminal server: 12 -> %d. Several: 3 7 12" % (
                cfg.console_port_base + 12), th.win_hint
        put(scr, y + 5, x0 + 3, info[:bw - 6], attr)
        keys = (("Enter", "connect"), (sym["lr"], "switch login"), ("ESC", "cancel"))
        if many:
            keys = (("Enter", "connect"), ("Tab", "next server"), (sym["lr"], "login"), ("ESC", "cancel"))
        screen.draw_keys(y + 7, x0 + 3, keys)
        scr.refresh()

        key = screen.read_key(-1)
        if key == "ESC":
            return None
        if key in ("LEFT", "RIGHT"):
            mi = (mi + (-1 if key == "LEFT" else 1)) % len(CONSOLE_MODES)
        elif key in ("TAB", "DOWN", "BTAB", "UP"):
            if many:
                field = (field + (-1 if key in ("BTAB", "UP") else 1)) % len(servers)
            elif key in ("TAB", "BTAB"):     # one server: Tab still cycles the login, as before
                mi = (mi + (-1 if key == "BTAB" else 1)) % len(CONSOLE_MODES)
        elif key == "ENTER":
            chosen = []
            for i, text in enumerate(texts):
                lines, why = parse_console_lines(cfg, text)
                if lines is None:
                    field, error = i, ("%s: %s" % (servers[i][0], why)) if many else why
                    break
                chosen.append(lines)
            else:
                return chosen, CONSOLE_MODES[mi]
        else:
            edited = edit_field(texts[field], key, keep=lambda c: c.isdigit() or c in " ,-", limit=40)
            if edited is not None:
                texts[field], error = edited, None


def settings_window(screen, rows):
    """Draw the settings window once and return the key pressed.  rows are
    (key, label, value, extra); a value of "on" is highlighted."""
    scr, th = screen.scr, screen.th
    width = min(80, max(56, scr.getmaxyx()[1] - 6))
    label_w, value_x = 34, 3 + 4 + 34 + 2
    y0, x0 = screen.draw_window("Settings", "for this TRuffle only", len(rows) + 7, width)
    for i, (key, label, value, extra) in enumerate(rows):
        y = y0 + 2 + i
        put(scr, y, x0 + 3, key, th.win_key)
        put(scr, y, x0 + 7, fit(label, label_w).rstrip(), th.win_label)
        text = value if not extra else "%s  %s" % (value, extra)
        put(scr, y, x0 + value_x, fit(text, width - value_x - 3, screen.sym["more"]).rstrip(),
            th.win_key if value == "on" else th.win_hint)
    put(scr, y0 + len(rows) + 3, x0 + 3, "Not saved - put it in truffle.conf to keep it"[:width - 6], th.win_hint)
    screen.draw_keys(y0 + len(rows) + 5, x0 + 3, (("ESC", "close"),))
    scr.refresh()
    return screen.read_key(-1)
