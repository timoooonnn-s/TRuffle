"""The dialog windows: login, terminal-server line, your own devices, settings.  Each one draws on a
Screen, reads keys until it is done and returns what was chosen - no TRuffle state."""

import os
import textwrap

from ..config import valid_user
from ..console import console_user, parse_console_lines
from ..credentials import minutes_text
from ..inventory import DEVICE_LOGINS, clean
from ..state import CONSOLE_MODES, SERVER_MODES
from .draw import fit, put, short_path


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


def wrapped(text, width):
    """A hint as the lines it needs.  These texts are sentences: a window WRAPS them and
    grows for them instead of cutting the end off, which is what the save and console
    windows did on any terminal under ~74 columns (user, 2026-11-18, on the local-account
    line of a manually added host: "This looks cut off")."""
    # break_on_hyphens: a device or account name (ber-core-ts1-a) must not be torn apart
    # at its hyphens; a word longer than the window is still broken, never drawn over it.
    return textwrap.wrap(text, max(10, width), break_on_hyphens=False) or [""]


# The sentences the save and console windows print under their fields.  They live here,
# next to login_hints(), so a test can measure every one of them against the room its
# window has without a terminal.
SAVE_LOGIN_TEXT = {"radius": "your RADIUS login, like the devices in the list",
                   "local": "the devices' local account, asked once and kept",
                   "manual": "ssh as the user below, you type the password"}
SAVE_CONSOLE_TEXT = "terminal server - the console window asks"
SAVE_NOTE = "Only for you - the device list stays as it is."


def server_login_text(server_mode, who, sep="·"):
    """The line under the console window's Terminal server field.  who: the user it logs
    in as ("timmy:7012"), or "" when no login is held yet."""
    return "%s  %s  %s" % ("your RADIUS login" if server_mode == "radius" else "its local account",
                           sep, who or "asked once and kept")


def device_login_text(mode, user, local_user=None):
    """The line under the console window's Device login field."""
    if mode == "radius":
        return "RADIUS (%s), TRuffle types it" % user
    if mode == "local":
        return ("its local account %s, TRuffle types it" % local_user if local_user
                else "its local account, asked once and kept")
    return "you log in at the device yourself"


def login_hints(lifetime=0, local_for=None, which=""):
    """The lines under the two fields of the login window.  Separate from the drawing so
    their length can be checked against the window without a terminal: every one of them
    has to fit, and the window wraps them instead of cutting them off."""
    return ["In memory only, never written to disk",
            "Forgotten %s after you typed it, or when you quit" % minutes_text(lifetime)
            if lifetime else "Forgotten when TRuffle exits",
            "Empty password: you type it at the device" if local_for
            else "Empty password: ssh asks at every login"] + ([which] if which else [])


def login_dialog(screen, user, local_for=None, error=None, server=None, local_server=None, local_device=None,
                 lifetime=0):
    """Ask user + password.  Returns (user, password or None) or None on ESC.
    local_for: the terminal server name - then it asks for a device's local account.
    server: the terminal server this RADIUS login is asked for.
    local_server: the terminal server whose OWN local account it asks for (D54).
    local_device: the same local account, for your devices set to it (D56).
    lifetime: password_lifetime in minutes, for the line that says how long it is kept."""
    entry = [user or "", ""]
    field = 1 if entry[0] else 0
    scr, th, sym = screen.scr, screen.th, screen.sym
    which = ("Only the device - not the terminal server in front of it." if local_for
             else "Only the terminal server, not the device behind it." if local_server
             else "Your devices set to local, and consoles that take it." if local_device
             else "For the terminal server %s." % server if server else "")
    while True:
        bw = min(66, scr.getmaxyx()[1] - 6)
        # The hints are WRAPPED to the window and the window grows for them.  They used to
        # be cut off mid-word on every screen, however wide (user: "the message from the
        # local account doesn\'t fit on my macbook\'s screen, the scalability fails").
        hints = [line for hint in login_hints(lifetime, local_for, which)
                 for line in (textwrap.wrap(hint, max(10, bw - 6)) or [""])]
        while hints and 11 + len(hints) > scr.getmaxyx()[0]:
            hints.pop()          # a short screen keeps the fields and the keys, not the last hint
        bh = 11 + len(hints)
        if local_for:
            y0, x0 = screen.draw_window("Local account", "device behind %s" % local_for, bh, bw)
        elif local_server:
            y0, x0 = screen.draw_window("Local account", "terminal server %s" % local_server, bh, bw)
        elif local_device:
            y0, x0 = screen.draw_window("Local account", local_device, bh, bw)
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
        for i, line in enumerate(hints):
            put(scr, y0 + 8 + i, x0 + 3, line, th.win_hint)
        screen.draw_keys(y0 + bh - 2, x0 + 3, (("Enter", "OK"), ("Tab", "next field"), ("ESC", "cancel")),
                         right=x0 + bw - 2)
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


def save_dialog(screen, address, name, login, user, saved=False, error=None, is_console=lambda name: False):
    """One of your own devices (D55, D56): its name and who logs in - your RADIUS login,
    the devices' local account, or manual (ssh as `user`, you type the password).  Up /
    Down / Tab move, Left / Right change the login, typing on it edits the name.  saved:
    it is in your list already, ^D forgets it.  A name is_console() calls a terminal
    server has no login line - the console window asks who logs in there.  Returns
    (name, login, user or None), "forget", or None on ESC."""
    li = DEVICE_LOGINS.index(login) if login in DEVICE_LOGINS else 0
    field = 0                            # 0 name, 1 login, 2 user (manual only)
    entry = [name, user or ""]
    scr, th, sym = screen.scr, screen.th, screen.sym
    while True:
        console = is_console(clean(entry[0]))
        login = "radius" if console else DEVICE_LOGINS[li]
        manual = login == "manual"
        bw = min(66, scr.getmaxyx()[1] - 6)
        # The line under Login is a whole sentence, so it is wrapped to the window and the
        # window grows for it; only a screen too SHORT to grow falls back to a marked cut.
        what = SAVE_CONSOLE_TEXT if console else SAVE_LOGIN_TEXT[login]
        note = SAVE_NOTE
        hints, foot = wrapped(what, bw - 18), wrapped(note, bw - 6)
        if 15 + (len(hints) - 1) + (len(foot) - 1) > scr.getmaxyx()[0]:
            foot = [fit(note, max(0, bw - 6), sym["more"]).rstrip()]
        if 15 + (len(hints) - 1) > scr.getmaxyx()[0]:
            hints = [fit(what, max(0, bw - 18), sym["more"]).rstrip()]
        hs = len(hints) - 1
        bh = 15 + hs + len(foot) - 1
        y0, x0 = screen.draw_window("Device" if saved else "Save device", "your own list", bh, bw)
        fw = max(6, bw - 18)
        put(scr, y0 + 2, x0 + 3, "Address", th.win)
        put(scr, y0 + 2, x0 + 15, address[:fw], th.win_label)
        for i, (label, y) in enumerate((("Name", 4), ("User", 8 + hs))):
            if i and not manual:
                continue
            active = field == i * 2
            put(scr, y0 + y, x0 + 3, label, th.win_label if active else th.win)
            shown = entry[i][-(fw - 2):]
            put(scr, y0 + y, x0 + 14, " " + shown.ljust(fw - 1), th.field if active else th.field_idle)
            if active:
                put(scr, y0 + y, x0 + 15 + len(shown), " ", th.cursor)
        if console:
            put(scr, y0 + 6, x0 + 3, "Login", th.win)
            hy = y0 + 6
        else:
            put(scr, y0 + 6, x0 + 3, "Login", th.win_label if field == 1 else th.win)
            put(scr, y0 + 6, x0 + 14, " %s %s %s" % (sym["lt"], login.ljust(6), sym["gt"]),
                th.field if field == 1 else th.field_idle)
            hy = y0 + 7
        for i, line in enumerate(hints):
            put(scr, hy + i, x0 + 15, line, th.win_hint)
        if error:
            put(scr, y0 + 10 + hs, x0 + 3, fit(sym["dot"] + " " + error, max(0, bw - 6), sym["more"]).rstrip(),
                th.win_err)
        for i, line in enumerate(foot):
            put(scr, y0 + 11 + hs + i, x0 + 3, line, th.win_hint)
        keys = [("Enter", "save")] + ([] if console else [("Tab", "next"), (sym["lr"], "login")])
        screen.draw_keys(y0 + bh - 2, x0 + 3, keys + ([("^D", "forget")] if saved else []) + [("ESC", "cancel")],
                         right=x0 + bw - 2)
        scr.refresh()

        key = screen.read_key(-1)
        if key == "ESC":
            return None
        if key == "CTRL_D" and saved:
            return "forget"
        if key in ("LEFT", "RIGHT") and field == 1:
            li = (li + (-1 if key == "LEFT" else 1)) % len(DEVICE_LOGINS)
        elif key in ("TAB", "DOWN", "BTAB", "UP"):
            field = 0 if console else (field + (-1 if key in ("BTAB", "UP") else 1)) % (3 if manual else 2)
        elif key == "ENTER":
            if not clean(entry[0]):
                error, field = "Please enter a name.", 0
            elif manual and not valid_user(entry[1]):
                error, field = "Please enter the user ssh logs in as.", 2
            else:
                return clean(entry[0]), login, entry[1] if manual else None
        else:
            # typing on the login row goes to the name, like on the console window's (D54)
            edited = edit_field(entry[field // 2 if field != 1 else 0], key, limit=64)
            if edited is not None:
                field = field if field != 1 else 0
                entry[field // 2], error = edited, None


def console_dialog(screen, cfg, servers, mode, user, local_user, others=0, server_mode="radius",
                   server_user=None):
    """Lines and both logins for one or more terminal servers (D51, D54).  servers: [(name,
    lines text)]; others: marked devices that get an ssh pane next to them.  Up / Down / Tab
    move between the lines, the terminal-server login and the device login; Left / Right
    change the login in focus (on a line: the device login, as before D54); digits type
    the lines ("3 7 12", "3-5").  Returns ([[line, ...] per server], mode, server_mode)
    or None on ESC."""
    texts = [text for _, text in servers]
    mi = CONSOLE_MODES.index(mode) if mode in CONSOLE_MODES else 0
    si = SERVER_MODES.index(server_mode) if server_mode in SERVER_MODES else 0
    field = lines_field = 0              # 0..n-1 a server's lines, n the server login, n+1 the device's
    error = None
    scr, th, sym = screen.scr, screen.th, screen.sym
    n, many = len(servers), len(servers) > 1
    while True:
        mode, server_mode = CONSOLE_MODES[mi], SERVER_MODES[si]
        bw = min(74, scr.getmaxyx()[1] - 6)
        parsed = [parse_console_lines(cfg, t)[0] if t.strip() else None for t in texts]
        first = next((ls[0] for ls in parsed if ls), None)
        ts_user = user if server_mode == "radius" else server_user
        # The three sentences under the fields, wrapped to the window, which grows for them
        # (they were cut off on any terminal under 80 columns).
        who = (console_user(cfg, ts_user, first) if ts_user and first else
               "%s:<port>" % ts_user if ts_user else "")
        server_what = server_login_text(server_mode, who, sym["sep"])
        device_what = device_login_text(mode, user, local_user)
        panes = sum(len(ls) for ls in parsed if ls) + others
        if error:
            info_text, attr = sym["dot"] + " " + error, th.win_err
        elif panes > 1:
            info_text, attr = "%d tmux panes%s, the same two logins for all consoles" % (
                panes, " (%d of them ssh)" % others if others else ""), th.win_hint
        else:
            info_text, attr = "Line = the port on the terminal server: 12 -> %d. Several: 3 7 12" % (
                cfg.console_port_base + 12), th.win_hint
        blocks = [wrapped(server_what, bw - 24), wrapped(device_what, bw - 24), wrapped(info_text, bw - 6)]
        if 13 + n + sum(len(b) - 1 for b in blocks) > scr.getmaxyx()[0]:
            blocks = [[fit(t, max(0, bw - w), sym["more"]).rstrip()]        # too short to grow: mark the cut
                      for t, w in ((server_what, 24), (device_what, 24), (info_text, 6))]
        server_hint, device_hint, info = blocks
        sh, dh = len(server_hint) - 1, len(device_hint) - 1
        bh = 13 + n + sh + dh + len(info) - 1
        title = "Consoles" if many else "Console"
        y0, x0 = screen.draw_window(title, "%d terminal servers" % n if many else servers[0][0], bh, bw)
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
        put(scr, y, x0 + 3, "Terminal server", th.win_label if field == n else th.win)
        put(scr, y, x0 + 21, "%s %s %s" % (sym["lt"], server_mode.ljust(6), sym["gt"]),
            th.field if field == n else th.field_idle)
        for i, line in enumerate(server_hint):
            put(scr, y + 1 + i, x0 + 21, line, th.win_hint)
        put(scr, y + 2 + sh, x0 + 3, "Device login", th.win_label if field == n + 1 else th.win)
        put(scr, y + 2 + sh, x0 + 21, "%s %s %s" % (sym["lt"], mode.ljust(6), sym["gt"]),
            th.field if field != n else th.field_idle)
        for i, line in enumerate(device_hint):
            put(scr, y + 3 + sh + i, x0 + 21, line, th.win_hint)
        for i, line in enumerate(info):
            put(scr, y + 5 + sh + dh + i, x0 + 3, line, attr)
        screen.draw_keys(y + 7 + sh + dh + len(info) - 1, x0 + 3,
                         (("Enter", "connect"), ("Tab", "next"),
                          (sym["lr"], "login"), ("ESC", "cancel")), right=x0 + bw - 2)
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


def row_text(value, extra, room=None, more="\u2026"):
    """One settings row's right-hand side: the value, and after it the extra - a path
    shortened to `room` from its end, anything else as it is."""
    if not extra:
        return value
    return "%s  %s" % (value, short_path(extra, room, more) if os.path.isabs(extra) else extra)


def settings_window(screen, rows):
    """Draw the settings window once and return the key pressed.  rows are
    (key, label, value, extra); a value of "on" is highlighted.  An `extra` that is an
    absolute path is written with `~` for $HOME and, if the column is still too narrow,
    kept from its END - the log directory is the one value in here that says nothing at
    all when it is cut from the right."""
    scr, th, sym = screen.scr, screen.th, screen.sym
    room = max(40, scr.getmaxyx()[1] - 6)
    # As wide as the longest row needs (paths with $HOME as ~), between 56 and 96 columns,
    # and never wider than the screen.  3 for the key, 4 + 2 of gaps, 3 of right margin.
    texts = [row_text(value, extra) for _, _, value, extra in rows]
    label_w = min(34, max(len(label) for _, label, _, _ in rows))
    width = min(room, max(56, min(96, 12 + label_w + max(len(t) for t in texts))))
    label_w = min(label_w, max(10, width - 12 - 12))      # a narrow screen pays from the labels
    value_x = 3 + 4 + label_w + 2
    budget = max(0, width - value_x - 3)
    note = wrapped("Not saved - put it in truffle.conf to keep it", width - 6)
    if len(rows) + 7 + len(note) - 1 > scr.getmaxyx()[0]:
        note = [fit(note[0], width - 6, sym["more"]).rstrip()]
    y0, x0 = screen.draw_window("Settings", "for this TRuffle only", len(rows) + 7 + len(note) - 1, width)
    for i, (key, label, value, extra) in enumerate(rows):
        y = y0 + 2 + i
        put(scr, y, x0 + 3, key, th.win_key)
        put(scr, y, x0 + 7, fit(label, label_w, sym["more"]).rstrip(), th.win_label)
        text = row_text(value, extra, max(0, budget - len(value) - 2), sym["more"])
        put(scr, y, x0 + value_x, fit(text, budget, sym["more"]).rstrip(),
            th.win_key if value == "on" else th.win_hint)
    for i, line in enumerate(note):
        put(scr, y0 + len(rows) + 3 + i, x0 + 3, line, th.win_hint)
    screen.draw_keys(y0 + len(rows) + 4 + len(note), x0 + 3, (("ESC", "close"),), right=x0 + width - 2)
    scr.refresh()
    return screen.read_key(-1)
