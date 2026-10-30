"""The screen helpers that need no terminal: help page, theme, keys, paste, cells."""

import glob
import os
import re
import unittest

from support import SRC, FakeWin, TempDir, args
from truffle import config, results, state, tmux
from truffle.results import Results
from truffle.ui import draw, keys, pages, switchlist, theme


START, END = "\x1b[200~", "\x1b[201~"


class TestHelpPage(TempDir):
    """The about / help page is data, so it can be checked against the real feature set."""

    def sections(self):
        cfg = config.load_config(args())
        return pages.help_sections(cfg, 7, 42)

    def text(self):
        return "\n".join(" ".join(e[1:]) for e in self.sections())

    def test_every_command_is_documented(self):
        documented = [e[1] for e in self.sections() if e[0] == "item"]
        for command in pages.COMMANDS:
            self.assertIn(command, documented, "help page does not document the '%s' command" % command)

    def test_the_esc_chain_names_every_step_it_does(self):
        """The ESC key walks search -> running ping -> marks -> sort.  The help page used
        to skip the marks step, which is exactly the kind of drift this page is data for."""
        items = [e for e in self.sections() if e[0] == "item"]
        index = next(i for i, e in enumerate(items) if e[1] == "ESC")
        esc = items[index][2]
        for entry in items[index + 1:]:                 # wrapped continuation lines
            if entry[1]:
                break
            esc += " " + entry[2]
        esc = esc.lower()
        for step in ("search", "mark", "ping", "sort"):
            self.assertIn(step, esc, "the help page's ESC entry (%r) does not mention '%s'" % (esc, step))

    def test_no_removed_feature_is_still_advertised(self):
        text = self.text().lower()
        for gone in ("ssh check", "traceroute", "tracepath", "no-answer", "ping + ssh",
                     "next / previous sort column",      # Tab sorts no longer, it marks
                     "batch ping",                       # merged into ping (D35)
                     "^f", "favourite", "is:fav",          # favourites cut (D50)
                     "screen symbols",                     # Ctrl-G c cut (D50)
                     "round-trip", "slowest"):           # MS column removed (D36)
            self.assertNotIn(gone, text, "help page still mentions the removed '%s'" % gone)

    def test_shows_the_paths_in_use(self):
        cfg = config.load_config(args())
        text = self.text()
        self.assertIn(cfg.data, text)
        self.assertIn(cfg.state_dir, text)
        self.assertIn("42 devices", text)


class TestTheme(unittest.TestCase):
    """Theme names are looked up as attributes, so a typo only shows on a rare screen.
    This checks every name the source uses against the palette."""

    def palette(self):
        return set(theme.PALETTE)

    def test_every_theme_attribute_exists(self):
        source = ""
        for path in glob.glob(os.path.join(SRC, "truffle", "**", "*.py"), recursive=True):
            with open(path, encoding="utf-8") as f:
                source += f.read()
        used = set(re.findall(r"\bth\.(\w+)\b", source)) - {"sym", "colors", "status"}
        self.assertTrue(used)
        self.assertEqual(sorted(used - self.palette()), [], "theme attribute used but not defined")

    def test_status_and_banner_styles_exist(self):
        palette = self.palette()
        for state in (results.PING_UP, results.PING_DOWN, results.SSH_OK, results.SSH_FAILED, results.WAIT):
            style = theme.STATUS_STYLE[state]
            self.assertIn(style, palette)
            self.assertIn(style + "_sel", palette)       # built as style + "_sel" when selected
        for i in range(1, len(theme.BANNER) + 1):
            self.assertIn("banner%d" % i, palette)

    def test_mono_fallback_covers_only_real_names(self):
        self.assertEqual(sorted(set(theme.MONO) - self.palette()), [])


class TestPaste(unittest.TestCase):
    """A pasted newline used to arrive as Enter, which ran ssh on whatever switch
    happened to be selected.  Pasted text must be text."""

    def text(self, raw, multiline=True):
        return keys.Paste(raw).as_text(multiline)

    def test_control_characters_never_become_keys(self):
        self.assertEqual(self.text("ber-core-01\n"), "ber-core-01")
        self.assertEqual(self.text("a\tb"), "ab")                  # a tab would mark a switch
        self.assertEqual(self.text("10.0.0.1\r\n10.0.0.2\n"), "10.0.0.1 10.0.0.2")
        self.assertEqual(self.text(""), "")
        self.assertEqual(self.text(None), "")

    def test_a_password_field_takes_only_the_first_line(self):
        self.assertEqual(self.text("secret\n", multiline=False), "secret")
        self.assertEqual(self.text("secret\nmore", multiline=False), "secret")

    def test_long_pastes_are_capped(self):
        self.assertEqual(len(self.text("x" * 5000)), keys.MAX_PASTE)

    def test_the_paste_travels_with_its_key(self):
        """D44: the text used to wait in a global for whoever read it next."""
        key = self.drain(START + "ber core" + END)[0]
        self.assertEqual(key, "PASTE")
        self.assertEqual(key.as_text(), "ber core")

    def test_the_markers_are_parsed_as_keys(self):
        self.assertEqual(keys.parse_escape_sequence("[200~"), "PASTE_START")
        self.assertEqual(keys.parse_escape_sequence("[201~"), "PASTE_END")

    def test_an_oversized_paste_is_fully_drained(self):
        """The cap limits what we KEEP, never what we consume.  Stopping early left the
        rest of the paste in the input queue, where its newlines became Enter again -
        and Enter runs ssh on the selected switch."""
        got = self.drain(START + "10.0.0.1\n" * 200 + END)
        self.assertEqual([k for k in got if k != "PASTE"], [],
                         "characters leaked out of the paste and were read as keys")
        self.assertEqual(got.count("PASTE"), 1)

    def test_a_paste_without_an_end_marker_still_terminates(self):
        got = self.drain(START + "abc")             # terminal stops mid-paste
        self.assertEqual(got, ["PASTE"])

    def drain(self, text):
        """Every key read_key reports for this character stream, as the app sees it."""
        win, out = FakeWin(text), []
        while win.buf:
            key = keys.read_key(win, 250)
            if key is not None:
                out.append(key)
        return out


class TestKeys(unittest.TestCase):
    def test_escape_sequences(self):
        cases = {"": "ESC", "[A": "UP", "OA": "UP", "[11~": "F1", "OP": "F1", "[[E": "F5",
                 "[17~": "F6", "[1;5A": "UP", "[15;2~": "F5", "[5~": "PGUP", "[Z": "BTAB", "[999~": None}
        for seq, key in cases.items():
            self.assertEqual(keys.parse_escape_sequence(seq), key, seq)


class TestDrawingHelpers(unittest.TestCase):
    def test_fit(self):
        self.assertEqual(draw.fit("abc", 5), "abc  ")
        self.assertEqual(draw.fit("abcdef", 4), "abc~")
        self.assertEqual(draw.fit("abcdef", 4, "\u2026"), "abc\u2026")

    def test_fit_widths(self):
        self.assertEqual(sum(draw.fit_widths([40, 20, 6], 50)), 50)
        self.assertEqual(draw.fit_widths([10, 10], 50), [10, 10])

    def test_wrap(self):
        self.assertEqual(draw.wrap_lines(["a" * 25, ""], 10), ["a" * 10, "a" * 10, "a" * 5, ""])


class TestStatusAge(unittest.TestCase):
    """The PING / SSH cells carry how old the result is."""

    def test_age_text(self):
        for seconds, text in ((0, "now"), (59, "now"), (60, "1m"), (3599, "59m"), (3600, "1h"),
                              (47 * 3600, "47h"), (48 * 3600, "2d"), (30 * 86400, "30d")):
            self.assertEqual(draw.age_text(seconds), text, seconds)

    def test_cell(self):
        now = 100000.0
        self.assertEqual(draw.status_cell("down", now - 7200, now, 12, "*"), ("* down", "2h", False))
        self.assertEqual(draw.status_cell("failed", now - 3 * 86400, now, 12, "*"), ("* failed", "3d", True))
        self.assertEqual(draw.status_cell("wait", now - 5, now, 12, "*"), ("* wait", "", False))
        self.assertEqual(draw.status_cell("up", None, now, 12, "*"), ("* up", "", False))
        # a column squeezed by a narrow terminal keeps the word and drops the age
        self.assertEqual(draw.status_cell("failed", now - 7200, now, 8, "*"), ("* failed", "", False))
        self.assertEqual(draw.status_cell("up", now + 30, now, 12, "*")[1], "now")   # clock skew between windows

    def test_the_columns_fit_the_longest_cell(self):
        widths = dict((kind, width) for _, width, kind in results.STATUS_COLUMNS)
        self.assertGreaterEqual(widths["ssh"], len("● failed 47h"))
        self.assertGreaterEqual(widths["ping"], len("● down 47h"))


class TestSwitchList(TempDir):
    """The main list as data: marks, the is:marked search, sorting off and on."""

    def make(self):
        csv = self.write("sw.csv", "Name;IP\nab-1;10.0.0.1\nab-2;10.0.0.2\ncd-1;10.0.0.3\n")
        conf = self.write("c.conf", "[truffle]\ndata = %s\ncolumns = Name, IP\n" % csv)
        cfg = config.load_config(args(config=conf))
        lst = switchlist.SwitchList(cfg, state.UserState(os.path.join(self.tmp, "st")), Results())
        self.assertEqual(lst.load(), [])
        return lst

    def test_marks_survive_a_new_search_and_keep_their_order(self):
        lst = self.make()
        lst.set_query("cd")
        lst.toggle_mark(lst.selected())
        lst.set_query("ab-2")
        lst.toggle_mark(lst.selected())
        lst.set_query("zzz")
        self.assertEqual([d.name for d in lst.marked_devices()], ["cd-1", "ab-2"])
        lst.set_query("is:marked")
        self.assertEqual(sorted(d.name for d in lst.view), ["ab-2", "cd-1"])

    def test_the_cursor_stays_inside_the_list(self):
        lst = self.make()
        lst.move(-5)
        self.assertEqual(lst.cursor, 0)
        lst.move(50)
        self.assertEqual(lst.cursor, 2)
        lst.set_query("nothing matches")
        lst.move(1)
        self.assertIsNone(lst.selected())

    def test_a_status_sort_follows_new_results(self):
        lst = self.make()
        self.assertTrue(lst.set_sort(lst.ncols() - 1))            # the SSH column
        lst.results.set("ssh", "10.0.0.3", "failed", 100)
        lst.status_changed()
        self.assertEqual(lst.view[0].name, "cd-1")                # problems first


class TestTypedAndSavedDevices(TempDir):
    """D55: an address typed in the search, and your own saved devices."""

    def make(self):
        return TestSwitchList.make(self)

    def test_an_unknown_address_is_the_first_row(self):
        lst = self.make()
        lst.set_query("10.0.0.9")
        self.assertEqual([(d.origin, d.host) for d in lst.view], [("typed", "10.0.0.9")])
        self.assertEqual(lst.selected().cells, ["10.0.0.9", "10.0.0.9"])

    def test_it_comes_before_the_devices_it_is_part_of(self):
        csv = self.write("sw.csv", "Name;IP\nab-1;10.0.0.10\n")
        conf = self.write("c.conf", "[truffle]\ndata = %s\ncolumns = Name, IP\n" % csv)
        lst = switchlist.SwitchList(config.load_config(args(config=conf)),
                                    state.UserState(os.path.join(self.tmp, "st")), Results())
        lst.load()
        lst.set_query("10.0.0.1")
        self.assertEqual([d.name for d in lst.view], ["10.0.0.1", "ab-1"])
        self.assertEqual(lst.selected().origin, "typed")         # Enter never hits 10.0.0.10

    def test_a_listed_address_or_a_matching_hostname_is_no_typed_row(self):
        lst = self.make()
        lst.set_query("10.0.0.1")
        self.assertEqual([d.name for d in lst.view], ["ab-1"])
        lst.set_query("10.0")
        self.assertFalse(any(d.origin == "typed" for d in lst.view))
        lst.set_query("ab.1")                                    # a search that finds ab-1
        self.assertEqual([d.name for d in lst.view], ["ab-1"])
        lst.set_query("sw1.lab.example")
        self.assertEqual([d.origin for d in lst.view], ["typed"])

    def test_user_at_host_is_offered_even_for_a_listed_device(self):
        lst = self.make()
        lst.set_query("admin@10.0.0.1")
        dev = lst.selected()
        self.assertEqual((dev.origin, dev.user, dev.host, dev.name), ("typed", "admin", "10.0.0.1", "admin@10.0.0.1"))

    def test_saved_devices_join_the_list_and_can_be_forgotten(self):
        lst = self.make()
        lst.store.save_device("10.0.0.9", "lab-box", "admin")
        lst.load()
        lst.set_query("is:saved")
        dev = lst.selected()
        self.assertEqual((dev.name, dev.host, dev.user, dev.origin), ("lab-box", "10.0.0.9", "admin", "saved"))
        lst.toggle_mark(dev)
        self.assertEqual([d.name for d in lst.marked_devices()], ["lab-box"])
        lst.set_query("admin@10.0.0.9")                         # saved like that: no typed row
        self.assertEqual([d.origin for d in lst.view], [])
        lst.remove_saved(dev)
        self.assertEqual(lst.marked_devices(), [])
        lst.set_query("is:saved")
        self.assertEqual(lst.view, [])

    def test_saving_shows_it_under_its_name(self):
        lst = self.make()
        lst.set_query("10.0.0.9")
        dev = lst.add_saved("10.0.0.9", "lab-box-with-a-long-name", None)
        self.assertIs(lst.selected(), dev)
        self.assertEqual(lst.query, "lab-box-with-a-long-name")
        self.assertGreaterEqual(lst.widths[0], len("lab-box-with-a-long-name"))

    def test_without_a_device_list_typed_and_saved_still_work(self):
        conf = self.write("c.conf", "[truffle]\ndata = %s/nope.csv\n" % self.tmp)
        st = state.UserState(os.path.join(self.tmp, "st"))
        st.save_device("10.0.0.9", "lab-box")
        lst = switchlist.SwitchList(config.load_config(args(config=conf)), st, Results())
        lst.load()
        self.assertIsNotNone(lst.load_error)
        self.assertEqual([d.name for d in lst.view], ["lab-box"])
        lst.set_query("10.0.0.8")
        self.assertEqual(lst.selected().cells, ["10.0.0.8", "10.0.0.8"])


class TestPaneSessions(unittest.TestCase):
    def test_a_session_noticed_as_ended_elsewhere_is_still_reported(self):
        """D45 review: Ctrl-T / Ctrl-G l refreshed the list and threw away which sessions
        had ended, so their panes' results were never picked up."""
        alive = ["truffle-1", "truffle-2"]
        originals = tmux.truffle_sessions, tmux.tmux_try
        tmux.truffle_sessions = lambda: list(alive)
        tmux.tmux_try = lambda *args: alive.remove(args[-1][1:]) if args[0] == "kill-session" else None
        try:
            panes = tmux.PaneSessions()
            panes.add("truffle-1", {}, "u")
            panes.add("truffle-2", {}, "u")
            alive.remove("truffle-1")
            self.assertEqual(panes.refresh(), ["truffle-2"])     # e.g. Ctrl-T
            self.assertEqual(panes.take_ended(), ["truffle-1"])
            self.assertEqual(panes.take_ended(), [])
            panes.close(["truffle-2"])                           # closed by you: not "ended"
            self.assertEqual(panes.take_ended(), [])
        finally:
            tmux.truffle_sessions, tmux.tmux_try = originals


if __name__ == "__main__":
    unittest.main()
