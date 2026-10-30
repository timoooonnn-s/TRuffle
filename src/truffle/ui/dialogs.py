"""The dialog windows: login, terminal-server line, saving a typed address, settings.  Each one draws on a
Screen, reads keys until it is done and returns what was chosen - no TRuffle state."""

import textwrap

from ..config import valid_user
from ..console import console_user, parse_console_lines
from ..inventory import clean
from ..state import CONSOLE_MODES, SERVER_MODES
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


def login_dialog(screen, user, local_for=None, error=None, server=None, local_server=None, account_for=None):
    """Ask user + password.  Returns (user, password or None) or None on ESC.
    local_for: the terminal server name - then it asks for a switch's local account.
    server: the terminal server this RADIUS login is asked for.
    local_server: the terminal server whose OWN local account it asks for (D54).
    account_for: the user@host this login is for - not your RADIUS login (D55)."""
    entry = [user or "", ""]
    field = 1 if entry[0] else 0
    scr, th, sym = screen.scr, screen.th, screen.sym
    which = ("Only the switch - not the terminal server in front of it." if local_for
             else "Only the terminal server - the switch behind it has its own login." if local_server
             else "For %s only - not your RADIUS login." % account_for if account_for
             else "For the terminal server %s." % server if server else "")
    while True:
        bw, bh = min(66, scr.getmaxyx()[1] - 6), 14 if which else 13
        if local_for:
            y0, x0 = screen.draw_window("Local account", "switch behind %s" % local_for, bh, bw)
        elif local_server:
            y0, x0 = screen.draw_window("Local account", "terminal server %s" % local_server, bh, bw)
        elif account_for:
            y0, x0 = screen.draw_window("Login", "as %s" % entry[0], bh, bw)
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


def save_dialog(screen, address, name, error=None):
    """The name for an address you typed in the search, saved to your own list (D55).
    Returns the name, or None on ESC."""
    scr, th, sym = screen.scr, screen.th, screen.sym
    while True:
        bw, bh = min(66, scr.getmaxyx()[1] - 6), 12
        y0, x0 = screen.draw_window("Save device", "your own list", bh, bw)
        fw = max(6, bw - 18)
        put(scr, y0 + 2, x0 + 3, "Address", th.win)
        put(scr, y0 + 2, x0 + 15, address[:fw], th.win_label)
        put(scr, y0 + 4, x0 + 3, "Name", th.win_label)
        shown = name[-(fw - 2):]
        put(scr, y0 + 4, x0 + 14, " " + shown.ljust(fw - 1), th.field)
        put(scr, y0 + 4, x0 + 15 + len(shown), " ", th.cursor)
        if error:
            put(scr, y0 + 6, x0 + 3, (sym["dot"] + " " + error)[:bw - 6], th.win_err)
        put(scr, y0 + 7, x0 + 3, "Only for you - the device list stays as it is."[:bw - 6], th.win_hint)
        put(scr, y0 + 8, x0 + 3, ("Search finds it by its name %s ^N on it forgets it" % sym["sep"])[:bw - 6],
            th.win_hint)
        screen.draw_keys(y0 + bh - 2, x0 + 3, (("Enter", "save"), ("ESC", "cancel")))
        scr.refresh()

        key = screen.read_key(-1)
        if key == "ESC":
            return None
        if key == "ENTER":
            if clean(name):
                return clean(name)
            error = "Please enter a name."
        else:
            edited = edit_field(name, key, limit=64)
            name = name if edited is None else edited


def console_dialog(screen, cfg, servers, mode, user, local_user, others=0, server_mode="radius",
                   server_user=None):
    """Lines and both logins for one or more terminal servers (D51, D54).  servers: [(name,
    lines text)]; others: marked devices that get an ssh pane next to them.  Up / Down / Tab
    move between the lines, the terminal-server login and the switch login; Left / Right
    change the login in focus (on a line: the switch login, as before D54); digits type
    the lines ("3 7 12", "3-5").  Returns ([[line, ...] per server], mode, server_mode)
    or None on ESC."""
    texts = [text for _, text in servers]
    mi = CONSOLE_MODES.index(mode) if mode in CONSOLE_MODES else 0
    si = SERVER_MODES.index(server_mode) if server_mode in SERVER_MODES else 0
    field = lines_field = 0              # 0..n-1 a server's lines, n the server login, n+1 the switch's
    error = None
    scr, th, sym = screen.scr, screen.th, screen.sym
    n, many = len(servers), len(servers) > 1
    while True:
        mode, server_mode = CONSOLE_MODES[mi], SERVER_MODES[si]
        bw = min(74, scr.getmaxyx()[1] - 6)
        bh = 13 + n
        title = "Consoles" if many else "Console"
        y0, x0 = screen.draw_window(title, "%d terminal servers" % n if many else servers[0][0], bh, bw)
        parsed = [parse_console_lines(cfg, t)[0] if t.strip() else None for t in texts]
        for i, (name, _) in enumerate(servers):
            y = y0 + 2 + i
            put(scr, y, x0 + 3, fit(name if many else "Lines", 17).rstrip(), th.win_label if i == field else th.win)
            put(scr, y, x0 + 21, " " + texts[i][-22:].ljust(23), th.field if i == field else th.field_idle)
            if i == field:
                put(scr, y, x0 + 22 + len(texts[i][-22:]), " ", th.cursor)
            if parsed[i] and len(parsed[i]) > 1:
                put(scr, y, x0 + 46, ("%d panes" % len(parsed[i]))[:bw - 49], th.win_hint)
        # The two logins, in the order they happen (D47); the terminal server's is a choice
        # since D54 - lab terminal servers have a local account instead of RADIUS.
        y = y0 + 3 + n
        first = next((ls[0] for ls in parsed if ls), None)
        ts_user = user if server_mode == "radius" else server_user
        put(scr, y, x0 + 3, "Terminal server", th.win_label if field == n else th.win)
        put(scr, y, x0 + 21, "%s %s %s" % (sym["lt"], server_mode.ljust(6), sym["gt"]),
            th.field if field == n else th.field_idle)
        what = ("your RADIUS login  %s  " % sym["sep"] if server_mode == "radius"
                else "its local account  %s  " % sym["sep"])
        what += (console_user(cfg, ts_user, first) if ts_user and first else
                 "%s:<port>" % ts_user if ts_user else "asked once, then kept")
        put(scr, y + 1, x0 + 21, what[:bw - 24], th.win_hint)
        put(scr, y + 2, x0 + 3, "Switch login", th.win_label if field == n + 1 else th.win)
        put(scr, y + 2, x0 + 21, "%s %s %s" % (sym["lt"], mode.ljust(6), sym["gt"]),
            th.field if field != n else th.field_idle)
        what = {"radius": "RADIUS (%s), TRuffle types it" % user,
                "local": ("its local account %s, TRuffle types it" % local_user) if local_user
                         else "its local account - asked once, then kept",
                "manual": "you log in at the switch yourself"}[mode]
        put(scr, y + 3, x0 + 21, what[:bw - 24], th.win_hint)
        panes = sum(len(ls) for ls in parsed if ls) + others
        if error:
            info, attr = sym["dot"] + " " + error, th.win_err
        elif panes > 1:
            info, attr = "%d tmux panes%s, the same two logins for all consoles" % (
                panes, " (%d of them ssh)" % others if others else ""), th.win_hint
        else:
            info, attr = "Line = the port on the terminal server: 12 -> %d. Several: 3 7 12" % (
                cfg.console_port_base + 12), th.win_hint
        put(scr, y + 5, x0 + 3, info[:bw - 6], attr)
        screen.draw_keys(y + 7, x0 + 3, (("Enter", "connect"), ("Tab", "next"),
                                         (sym["lr"], "login"), ("ESC", "cancel")))
        scr.refresh()

        key = screen.read_key(-1)
        if key == "ESC":
            return None
        if key in ("LEFT", "RIGHT"):
            step = -1 if key == "LEFT" else 1
            if field == n:
                si = (si + step) % len(SERVER_MODES)
            else:
                mi = (mi + step) % len(CONSOLE_MODES)
        elif key in ("TAB", "DOWN", "BTAB", "UP"):
            field = (field + (-1 if key in ("BTAB", "UP") else 1)) % (n + 2)
            if field < n:
                lines_field = field
        elif key == "ENTER":
            chosen = []
            for i, text in enumerate(texts):
                lines, why = parse_console_lines(cfg, text)
                if lines is None:
                    field = lines_field = i
                    error = ("%s: %s" % (servers[i][0], why)) if many else why
                    break
                chosen.append(lines)
            else:
                return chosen, CONSOLE_MODES[mi], SERVER_MODES[si]
        else:
            edited = edit_field(texts[lines_field], key, keep=lambda c: c.isdigit() or c in " ,-", limit=40)
            if edited is not None:
                field = lines_field          # typing on a login row goes back to the lines
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
