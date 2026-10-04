"""Unit tests for the logic in tree-li (stdlib unittest only).

Run from the repository root:  python3 -m unittest discover -s tests -v
"""
import importlib.machinery
import importlib.util
import io
import os
import re
import shutil
import sys
import tempfile
import time
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_loader = importlib.machinery.SourceFileLoader("treeli", os.path.join(ROOT, "tree-li"))
_spec = importlib.util.spec_from_loader("treeli", _loader)
tl = importlib.util.module_from_spec(_spec)
_loader.exec_module(tl)


def args(**kw):
    base = dict(config=None, data=None, log=False, debug=False, check=False, ascii=False)
    base.update(kw)
    return types.SimpleNamespace(**base)


class TempDir(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._env = dict(os.environ)
        os.environ["XDG_CONFIG_HOME"] = os.path.join(self.tmp, "xdg")   # ignore the real user config

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)
        shutil.rmtree(self.tmp)

    def write(self, name, content, mode="w", encoding="utf-8"):
        path = os.path.join(self.tmp, name)
        if "b" in mode:
            with open(path, mode) as f:
                f.write(content)
        else:
            with open(path, mode, encoding=encoding, newline="") as f:
                f.write(content)
        return path


class TestCsv(TempDir):
    def test_semicolon_with_bom_and_comments(self):
        p = self.write("a.csv", "﻿Name;IP;comment\n# comment line\n\nsw1;10.0.0.1;Zürich\n")
        headers, rows = tl.read_table(p)
        self.assertEqual(headers, ["Name", "IP", "comment"])
        self.assertEqual(rows, [{"Name": "sw1", "IP": "10.0.0.1", "comment": "Zürich"}])

    def test_comma_autodetect_crlf_and_quotes(self):
        p = self.write("b.csv", 'Name,IP,comment\r\nsw1,10.0.0.1,"a, b"\r\n')
        _, rows = tl.read_table(p)
        self.assertEqual(rows[0]["comment"], "a, b")

    def test_cp1252_fallback(self):
        p = self.write("c.csv", "Name;IP;comment\nsw1;10.0.0.1;Gr\xfcezi\n".encode("cp1252"), mode="wb")
        _, rows = tl.read_table(p)
        self.assertEqual(rows[0]["comment"], "Grüezi")

    def test_short_and_long_rows_and_control_chars(self):
        p = self.write("d.csv", "Name;IP;comment\nsw1;10.0.0.1\nsw2;10.0.0.2;x\ty;extra\n")
        _, rows = tl.read_table(p)
        self.assertEqual(rows[0]["comment"], "")
        self.assertEqual(rows[1]["comment"], "x y")

    def test_missing_and_empty(self):
        with self.assertRaises(tl.DataError):
            tl.read_table(os.path.join(self.tmp, "nope.csv"))
        with self.assertRaises(tl.DataError):
            tl.read_table(self.write("e.csv", "\n\n"))

    def test_build_devices_case_insensitive_and_warnings(self):
        p = self.write("f.csv", "name;ip;Subnet;aliases;location\nsw1;10.0.0.1;a;Core;Room 1\n")
        cfg = tl.load_config(args())
        devices, columns, warns = tl.build_devices(*tl.read_table(p), cfg=cfg)
        self.assertEqual(devices[0].host, "10.0.0.1")
        self.assertEqual(devices[0].name, "sw1")
        self.assertEqual([c[1] for c in columns], ["Name", "IP", "subnet", "Alias"])
        self.assertTrue(any("comment" in w for w in warns))

    def test_data_check(self):
        p = self.write("h.csv", "Name;IP;comment\n"
                       "sw1;10.0.0.1;ok\n"
                       "sw2;10.0.0.1;same IP\n"
                       "SW1;10.0.0.3;same name\n"
                       "sw4;10.0.0.300;bad\n"
                       "sw5;010.0.0.5;octal\n"
                       "sw6;;no ip\n"
                       "sw7;10.0.0.7;a;b\n")
        report = {}
        devices, _, _ = tl.build_devices(*tl.read_table(p, report), cfg=tl.load_config(args()))
        self.assertEqual(report["lines"], [2, 3, 4, 5, 6, 7, 8])
        issues = "\n".join(tl.data_issues(devices, report["lines"], report["issues"]))
        for expected in ("line 8: 4 fields, the header has 3", "IP 10.0.0.1 is used 2 times",
                         "name 'sw1' appears 2 times: lines 2, 4", "'10.0.0.300' is not a valid IPv4",
                         "leading zeros", "line 7: 'sw6' has no IP"):
            self.assertIn(expected, issues)

    def test_export(self):
        p = self.write("i.csv", "Name;IP;location\nsw1;10.0.0.1;Room 1\n")
        headers, rows = tl.read_table(p)
        devices, _, _ = tl.build_devices(headers, rows, tl.load_config(args()))
        out = os.path.join(self.tmp, "export.csv")
        tl.export_csv(out, devices, headers, ";", {"ping": {"10.0.0.1": "up"}, "ssh": {}}, {("ping", "10.0.0.1"): 0.0})
        h2, r2 = tl.read_table(out)
        self.assertEqual(h2, ["Name", "IP", "location", "Ping", "Ping ms", "Ping checked",
                              "SSH last try", "SSH reason", "SSH tried"])
        self.assertEqual(r2[0]["location"], "Room 1")
        self.assertEqual(r2[0]["Ping"], "up")
        self.assertEqual(os.stat(out).st_mode & 0o777, 0o600)

    def test_no_ip_column(self):
        p = self.write("g.csv", "Name;where\nsw1;x\n")
        cfg = tl.load_config(args())
        with self.assertRaises(tl.DataError):
            tl.build_devices(*tl.read_table(p), cfg=cfg)


class TestConfig(TempDir):
    def test_defaults_resolve_data_next_to_script(self):
        cfg = tl.load_config(args())
        self.assertEqual(cfg.data, os.path.join(tl.SCRIPT_DIR, "data.csv"))
        self.assertFalse(cfg.session_log)

    def test_config_file_relative_data_and_overrides(self):
        conf = self.write("my.conf", "[tree-li]\ndata = lists/sw.csv\n"
                          "columns = Name, location:Where\nsession_log = yes\nuser = netadmin\n")
        cfg = tl.load_config(args(config=conf))
        self.assertEqual(cfg.data, os.path.join(self.tmp, "lists", "sw.csv"))
        self.assertEqual(cfg.columns, [("Name", "Name"), ("location", "Where")])
        self.assertTrue(cfg.session_log)
        self.assertEqual(cfg.user, "netadmin")

    def test_unknown_option_and_bad_values(self):
        for body in ("[tree-li]\ndatta = x\n", "[tree-li]\nping_rate = lots\n",
                     "[tree-li]\nsession_log = maybe\n", "[other]\n", "[tree-li]\nuser = -oProxyCommand=x\n"):
            conf = self.write("bad.conf", body)
            with self.assertRaises(tl.ConfigError, msg=body):
                tl.load_config(args(config=conf))


class TestSearchSort(unittest.TestCase):
    def devices(self, rows):
        out = []
        for name, ip in rows:
            d = tl.Device()
            d.values, d.host, d.name, d.cells = {}, ip, name, [name, ip]
            d.lcells = [c.lower() for c in d.cells]
            d.search = "\x00".join(d.lcells)
            out.append(d)
        return out

    def test_filter_tokens_all_must_match(self):
        ds = self.devices([("ber-core-01", "10.0.0.1"), ("ber-acc-01", "10.0.0.2"), ("muc-core-01", "10.0.1.1")])
        self.assertEqual([d.name for d in tl.filter_devices(ds, "core BER")], ["ber-core-01"])
        self.assertEqual(len(tl.filter_devices(ds, "  ")), 3)
        # tokens never match across two fields
        self.assertEqual(tl.filter_devices(ds, "01 10"), ds)
        self.assertEqual(tl.filter_devices(ds, "0110"), [])

    def test_natural_sort_and_empty_last(self):
        ds = self.devices([("sw10", "10.0.0.10"), ("", "10.0.0.9"), ("sw2", "10.0.0.2")])
        self.assertEqual([d.name for d in tl.sort_devices(ds, 0, False, {})], ["sw2", "sw10", ""])
        self.assertEqual([d.name for d in tl.sort_devices(ds, 0, True, {})], ["sw10", "sw2", ""])
        self.assertEqual([d.host for d in tl.sort_devices(ds, 1, False, {})],
                         ["10.0.0.2", "10.0.0.9", "10.0.0.10"])

    def test_sort_key_cycle_and_off(self):
        state = (None, False)
        seen = []
        for _ in range(4):
            state = tl.next_sort(state[0], state[1], 2)
            seen.append(state)
        self.assertEqual(seen, [(2, False), (2, True), (None, False), (2, False)])
        self.assertEqual(tl.next_sort(2, True, 0), (0, False))           # other column: ascending

    def test_sort_off_restores_csv_order(self):
        ds = self.devices([("sw10", "1"), ("sw2", "2"), ("sw1", "3")])
        sorted_once = tl.sort_devices(ds, 0, False, {})
        self.assertEqual([d.name for d in tl.sort_devices(ds, None, False, {})], ["sw10", "sw2", "sw1"])
        self.assertNotEqual(sorted_once, ds)

    def test_sort_by_ping_down_first(self):
        ds = self.devices([("a", "1"), ("b", "2"), ("c", "3")])
        ping = {"1": tl.PING_UP, "2": tl.PING_DOWN}
        ssh = {"1": tl.SSH_OK, "3": tl.SSH_FAILED}
        # indices come from STATUS_KINDS, not hardcoded: adding a status column must not
        # silently make this test sort a different column than its name says
        def col(kind):
            return len(ds[0].cells) + tl.STATUS_KINDS.index(kind)
        status = [ping if k == "ping" else ssh if k == "ssh" else {} for k in tl.STATUS_KINDS]
        self.assertEqual([d.name for d in tl.sort_devices(ds, col("ping"), False, status)], ["b", "a", "c"])
        self.assertEqual([d.name for d in tl.sort_devices(ds, col("ssh"), False, status)], ["c", "a", "b"])


class TestHelpPage(TempDir):
    """The about / help page is data, so it can be checked against the real feature set."""

    def sections(self):
        cfg = tl.load_config(args())
        return tl.help_sections(cfg, 7, 42)

    def text(self):
        return "\n".join(" ".join(e[1:]) for e in self.sections())

    def test_every_command_is_documented(self):
        keys = [e[1] for e in self.sections() if e[0] == "item"]
        for command in tl.COMMANDS:
            self.assertIn(command, keys, "help page does not document the '%s' command" % command)

    def test_the_esc_chain_names_every_step_it_does(self):
        """The ESC key walks search -> marks -> batch ping -> sort.  The help page used
        to skip the marks step, which is exactly the kind of drift this page is data for."""
        items = [e for e in self.sections() if e[0] == "item"]
        index = next(i for i, e in enumerate(items) if e[1] == "ESC")
        esc = items[index][2]
        for entry in items[index + 1:]:                 # wrapped continuation lines
            if entry[1]:
                break
            esc += " " + entry[2]
        esc = esc.lower()
        for step in ("search", "mark", "batch ping", "sort"):
            self.assertIn(step, esc, "the help page's ESC entry (%r) does not mention '%s'" % (esc, step))

    def test_no_removed_feature_is_still_advertised(self):
        text = self.text().lower()
        for gone in ("ssh check", "traceroute", "tracepath", "no-answer", "ping + ssh",
                     "next / previous sort column"):          # Tab sorts no longer, it marks
            self.assertNotIn(gone, text, "help page still mentions the removed '%s'" % gone)

    def test_shows_the_paths_in_use(self):
        cfg = tl.load_config(args())
        text = self.text()
        self.assertIn(cfg.data, text)
        self.assertIn(cfg.state_dir, text)
        self.assertIn("42 switches", text)


class TestTheme(unittest.TestCase):
    """Theme names are looked up as attributes, so a typo only shows on a rare screen.
    This checks every name the source uses against the palette."""

    SOURCE = open(os.path.join(ROOT, "tree-li"), encoding="utf-8").read()

    def palette(self):
        return set(re.findall(r'^    "(\w+)":\s+\(\(', self.SOURCE, re.M))

    def test_every_theme_attribute_exists(self):
        used = set(re.findall(r"\bth\.(\w+)\b", self.SOURCE)) - {"sym", "colors"}
        self.assertEqual(sorted(used - self.palette()), [], "theme attribute used but not defined")

    def test_status_and_banner_styles_exist(self):
        palette = self.palette()
        for state in (tl.PING_UP, tl.PING_DOWN, tl.SSH_OK, tl.SSH_FAILED, tl.WAIT):
            style = tl.STATUS_STYLE[state]
            self.assertIn(style, palette)
            self.assertIn(style + "_sel", palette)       # built as style + "_sel" when selected
        for i in range(1, len(tl.BANNER) + 1):
            self.assertIn("banner%d" % i, palette)

    def test_mono_fallback_covers_only_real_names(self):
        mono = set(re.findall(r'"(\w+)":', self.SOURCE[self.SOURCE.index("MONO = {"):
                                                       self.SOURCE.index("COLOR_NAMES")]))
        self.assertEqual(sorted(mono - self.palette()), [])


class TestCheck(TempDir):
    def run_check(self, csv_body, conf=""):
        data = self.write("sw.csv", csv_body)
        path = self.write("c.conf", "[tree-li]\ndata = %s\n%s" % (data, conf))
        cfg = tl.load_config(args(config=path))
        out = io.StringIO()
        stdout, sys.stdout = sys.stdout, out
        try:
            code = tl.check(cfg)
        finally:
            sys.stdout = stdout
        return code, out.getvalue()

    COLUMNS = "Name;IP;subnet;aliases;comment\n"

    def test_clean_list_exits_zero(self):
        code, out = self.run_check(self.COLUMNS + "sw1;10.0.0.1;a;b;c\n")
        self.assertEqual(code, 0)
        self.assertIn("data check   : ok", out)

    def test_warnings_exit_one_so_cron_can_gate(self):
        code, out = self.run_check(self.COLUMNS + "sw1;10.0.0.1;a;b;c\nsw2;10.0.0.1;a;b;c\n")
        self.assertEqual(code, 1)
        self.assertIn("is used 2 times", out)

    def test_missing_list_exits_two(self):
        path = self.write("c.conf", "[tree-li]\ndata = %s/nope.csv\n" % self.tmp)
        cfg = tl.load_config(args(config=path))
        out = io.StringIO()
        stdout, sys.stdout = sys.stdout, out
        try:
            self.assertEqual(tl.check(cfg), 2)
        finally:
            sys.stdout = stdout

    def test_a_retired_option_is_a_hard_error_not_a_silent_note(self):
        """Back-compat for old config files was dropped on purpose: a stale option now
        refuses to start and names itself, instead of being quietly ignored."""
        data = self.write("sw.csv", self.COLUMNS + "sw1;10.0.0.1;a;b;c\n")
        path = self.write("c.conf", "[tree-li]\ndata = %s\nping_workers = 200\n" % data)
        with self.assertRaises(tl.ConfigError) as caught:
            tl.load_config(args(config=path))
        self.assertIn("ping_workers", str(caught.exception))


class TestSearchSyntax(unittest.TestCase):
    def setUp(self):
        headers = ["Name", "IP", "type", "aliases", "location"]
        rows = [dict(zip(headers, r)) for r in (
            ("ber-core-01", "10.0.0.1", "core", "Core Berlin", "Room 1"),
            ("ber-edge-01", "10.0.0.2", "edge", "Edge Berlin", ""),
            ("muc-core-01", "fe80::1", "core", "Core Munich", "Room 9"),
            ("ber-test-01", "10.0.0.4", "edge", "Test", "Lab"))]
        cfg = types.SimpleNamespace(columns=[("Name", "Name"), ("IP", "IP"), ("aliases", "Alias")])
        self.devices, columns, _ = tl.build_devices(headers, rows, cfg)
        self.fields = dict((h.lower(), h) for h in headers)
        self.fields.update((label.lower(), h) for h, label in columns)

    def names(self, query, **kw):
        return [d.name for d in tl.filter_devices(self.devices, query, self.fields, **kw)]

    def test_field_hidden_column_and_label(self):
        self.assertEqual(self.names("type:core"), ["ber-core-01", "muc-core-01"])
        self.assertEqual(self.names("TYPE:CORE ber"), ["ber-core-01"])
        self.assertEqual(self.names("alias:munich"), ["muc-core-01"])        # table label works too
        self.assertEqual(self.names("location:"), ["ber-edge-01"])             # empty column

    def test_negation(self):
        self.assertEqual(self.names("ber -test"), ["ber-core-01", "ber-edge-01"])
        self.assertEqual(self.names("-type:edge"), ["ber-core-01", "muc-core-01"])

    def test_unknown_field_is_plain_text(self):
        self.assertEqual(self.names("fe80::1"), ["muc-core-01"])                # IPv6 is not a field
        self.assertEqual(self.names("nosuch:x"), [])

    def test_ping_and_user_state(self):
        ping = {"status": {"ping": {"10.0.0.1": tl.PING_UP, "10.0.0.2": tl.PING_DOWN}}}
        self.assertEqual(self.names("ping:down", **ping), ["ber-edge-01"])
        self.assertEqual(self.names("ping:none", **ping), ["muc-core-01", "ber-test-01"])
        self.assertEqual(self.names("-ping:up", **ping), ["ber-edge-01", "muc-core-01", "ber-test-01"])
        ssh = {"status": {"ssh": {"10.0.0.1": tl.SSH_OK, "10.0.0.2": tl.SSH_FAILED}}}
        self.assertEqual(self.names("ssh:failed", **ssh), ["ber-edge-01"])
        self.assertEqual(self.names("ssh:none", **ssh), ["muc-core-01", "ber-test-01"])
        self.assertEqual(self.names("is:fav", favorites={"ber-test-01"}), ["ber-test-01"])
        self.assertEqual(self.names("is:recent", recent={"muc-core-01": 5}), ["muc-core-01"])
        self.assertEqual(self.names("is:favs", favorites={"ber-test-01"}), [])  # no hidden aliases
        self.assertEqual(self.names("ping:wait", status={"ping": {"10.0.0.4": tl.WAIT}}), ["ber-test-01"])
        # a bare "ping:" means the same as "ping:none", exactly like an empty "location:"
        self.assertEqual(self.names("ping:", **ping), self.names("ping:none", **ping))
        self.assertEqual(self.names("ssh:", **ssh), self.names("ssh:none", **ssh))

    def test_fuzzy_and_exact(self):
        self.assertEqual(self.names("bc01"), ["ber-core-01"])                  # b..c..01 in order
        self.assertEqual(self.names("bt"), ["ber-test-01"])                    # b..t only in ber-test-01
        self.assertEqual(self.names("'bc01"), [])                              # exact: not a substring
        self.assertEqual(self.names("'core ber"), ["ber-core-01"])
        self.assertEqual(self.names("-tst"), self.names(""))                   # excludes are exact
        self.assertEqual(self.names("'"), self.names(""))                      # just started an exact term

    def test_fuzzy_ranking_and_marks(self):
        found = {}
        view = tl.filter_devices(self.devices, "core", self.fields, found=found)
        order = [d.name for d in tl.default_order(view, "core", set(), {}, found)]
        self.assertEqual(order, ["ber-core-01", "muc-core-01"])
        d = next(d for d in view if d.name == "ber-core-01")
        self.assertEqual(found[d][1], {0: {4, 5, 6, 7}})                      # "core" in the Name column

    def test_default_order(self):
        favorites, recent = {"muc-core-01"}, {"ber-edge-01": 10, "ber-test-01": 20}
        order = [d.name for d in tl.default_order(self.devices, "", favorites, recent)]
        self.assertEqual(order[0], "muc-core-01")                              # favourites pinned
        order = [d.name for d in tl.default_order(self.devices, "is:recent", favorites, recent)]
        self.assertEqual(order[:2], ["ber-test-01", "ber-edge-01"])            # newest first


class TestFuzzyMatch(unittest.TestCase):
    def test_match_and_positions(self):
        self.assertEqual(tl.fuzzy_match("bc01", "ber-core-01")[1], (0, 4, 9, 10))
        self.assertIsNone(tl.fuzzy_match("cb", "ber-core-01"))                 # order matters
        self.assertEqual(tl.fuzzy_match("core", "ber-core-01")[1], (4, 5, 6, 7))

    def test_scores(self):
        exact = tl.fuzzy_match("core", "ber-core-01")[0]
        scattered = tl.fuzzy_match("cr01", "ber-core-01")[0]
        boundary = tl.fuzzy_match("bc", "ber-core-01")[0]
        middle = tl.fuzzy_match("ro", "ber-core-01")[0]
        self.assertGreater(exact, scattered)                                   # substring always wins
        self.assertGreater(boundary, middle)                                   # word starts score higher


class TestUserState(TempDir):
    def test_favorites_and_recent_persist(self):
        st = tl.UserState(os.path.join(self.tmp, "state"))
        self.assertTrue(st.toggle_favorite("sw1"))
        st.touch("sw2")
        again = tl.UserState(os.path.join(self.tmp, "state"))
        self.assertEqual(again.favorites, {"sw1"})
        self.assertIn("sw2", again.recent)
        self.assertFalse(again.toggle_favorite("sw1"))
        self.assertEqual(tl.UserState(os.path.join(self.tmp, "state")).favorites, set())
        mode = os.stat(os.path.join(self.tmp, "state", "favorites")).st_mode & 0o777
        self.assertEqual(mode, 0o600)

    def test_history_is_trimmed_and_tolerates_garbage(self):
        d = os.path.join(self.tmp, "state")
        os.makedirs(d)
        with open(os.path.join(d, "recent"), "w") as f:
            f.write("garbage\nnot-a-number\tsw9\n100\tsw1\n")
        self.assertEqual(tl.UserState(d).recent, {"sw1": 100.0})
        with open(os.path.join(d, "recent"), "w") as f:
            f.write("".join("%d\tx%d\n" % (i, i) for i in range(tl.UserState.MAX_RECENT + 20)))
        tl.UserState(d).touch("newest")
        self.assertEqual(len(tl.UserState(d).recent), tl.UserState.MAX_RECENT)
        self.assertIn("newest", tl.UserState(d).recent)

    def test_check_results_are_saved_and_merged(self):
        d = os.path.join(self.tmp, "state")
        tl.UserState(d).save_status({"ping": {"10.0.0.1": "up", "10.0.0.2": "wait"}, "ssh": {"10.0.0.1": "failed"}},
                                    {("ping", "10.0.0.1"): 100, ("ssh", "10.0.0.1"): 100})
        tl.UserState(d).save_status({"ping": {"10.0.0.1": "down"}, "ssh": {}}, {("ping", "10.0.0.1"): 50})  # older
        status, checked, _ = tl.UserState(d).load_status()
        self.assertEqual(status["ping"], {"10.0.0.1": "up"})                # "wait" is never saved
        self.assertEqual(status["ssh"], {"10.0.0.1": "failed"})
        self.assertEqual(checked[("ping", "10.0.0.1")], 100)

    def test_a_host_that_stops_answering_loses_its_old_round_trip_time(self):
        """App.save_detail rebuilds the ping details from self.rtt.  Copying self.detail
        instead kept yesterday's ms next to today's "down", and reloaded it at startup."""
        detail = {("ping", "10.0.0.9"): "1.20", ("ssh", "10.0.0.9"): "Connection timed out"}
        rtt = {}                                   # the batch ping got no reply -> popped
        rebuilt = dict((k, v) for k, v in detail.items() if k[0] != "ping")
        for host, ms in rtt.items():
            rebuilt[("ping", host)] = tl.format_rtt(ms)
        self.assertNotIn(("ping", "10.0.0.9"), rebuilt)          # the stale ms is gone
        self.assertIn(("ssh", "10.0.0.9"), rebuilt)              # the ssh reason is kept

    def test_set_or_clear_drops_empty_values(self):
        m = {("ssh", "h"): "old"}
        tl.set_or_clear(m, ("ssh", "h"), "")
        self.assertEqual(m, {})
        tl.set_or_clear(m, ("ssh", "h"), "why")
        self.assertEqual(m, {("ssh", "h"): "why"})

    def test_the_detail_field_round_trips_and_stays_backward_compatible(self):
        """The 5th field carries the ping's ms and the reason a ssh attempt failed.
        Rows without it must keep working - an older TRee-Li writes only 4 fields,
        and a row with no detail is still written with 4 so an older one can read it."""
        d = os.path.join(self.tmp, "state")
        tl.UserState(d).save_status(
            {"ping": {"10.0.0.1": "up"}, "ssh": {"10.0.0.1": "failed"}},
            {("ping", "10.0.0.1"): 100, ("ssh", "10.0.0.1"): 100},
            {("ping", "10.0.0.1"): "1.25", ("ssh", "10.0.0.1"): "Connection timed out (exit 255)"})
        status, checked, detail = tl.UserState(d).load_status()
        self.assertEqual(detail[("ping", "10.0.0.1")], "1.25")
        self.assertEqual(detail[("ssh", "10.0.0.1")], "Connection timed out (exit 255)")
        # a result with no detail is written as 4 fields, readable by an older TRee-Li
        tl.UserState(d).save_status({"ping": {"10.0.0.2": "down"}, "ssh": {}},
                                    {("ping", "10.0.0.2"): 200})
        with open(os.path.join(d, "status"), encoding="utf-8") as f:
            rows = dict((line.split("\t")[0], line.rstrip("\n").split("\t")) for line in f)
        self.assertEqual(len(rows["10.0.0.2"]), 4)
        self.assertEqual(len(rows["10.0.0.1"]), 5)
        # and a hand-written 4-field file still loads completely
        with open(os.path.join(d, "status"), "w", encoding="utf-8") as f:
            f.write("10.0.0.9\tping\tup\t300\n")
        status, checked, detail = tl.UserState(d).load_status()
        self.assertEqual(status["ping"], {"10.0.0.9": "up"})
        self.assertEqual(detail, {})

    def test_save_status_survives_a_dict_the_batch_threads_mutate(self):
        """BatchPing._restore deletes hosts from the very dict save_status walks, from
        its worker threads.  Iterating it live raised "dictionary changed size during
        iteration" and painted a traceback over the curses screen."""
        import threading
        st = tl.UserState(os.path.join(self.tmp, "state"))
        ping = dict(("10.0.%d.%d" % (i // 250, i % 250), tl.PING_UP) for i in range(2000))
        status = {"ping": ping, "ssh": {}}
        checked = dict((("ping", h), 100) for h in ping)
        detail = dict((("ping", h), "1.0") for h in ping)
        stop = []
        old = sys.getswitchinterval()

        def churn():                                   # what a cancelled batch ping does
            while not stop:
                for host in list(ping):
                    ping.pop(host, None) if host in ping else ping.setdefault(host, tl.PING_UP)
        sys.setswitchinterval(1e-6)                    # make the thread switch, reliably
        worker = threading.Thread(target=churn)
        worker.daemon = True
        worker.start()
        try:
            for _ in range(40):
                st.save_status(status, checked, detail)         # must not raise
        finally:
            stop.append(True)
            worker.join(timeout=5)
            sys.setswitchinterval(old)

    def test_a_pane_login_failure_is_reported_and_read_back(self):
        """The handover socket is closed before a pane ever logs in, so a wrong password
        comes back through this file - TRee-Li then drops the password it holds."""
        d = os.path.join(self.tmp, "state")
        st = tl.UserState(d)
        self.assertEqual(tl.UserState(d).load_auth_failure(), (0.0, ""))
        st.note_auth_failure("10.0.0.7")
        stamp, host = tl.UserState(d).load_auth_failure()
        self.assertEqual(host, "10.0.0.7")
        self.assertGreater(stamp, 0)
        self.assertEqual(os.stat(os.path.join(d, "authfail")).st_mode & 0o777, 0o600)

    def test_unwritable_directory_reports_error(self):
        blocker = os.path.join(self.tmp, "file")
        open(blocker, "w").close()
        st = tl.UserState(os.path.join(blocker, "state"))     # a file is in the way
        st.toggle_favorite("sw1")
        self.assertIsNotNone(st.error)
        self.assertEqual(st.favorites, {"sw1"})               # still works in memory


class TestIdleAndMarks(unittest.TestCase):
    """The top bar must promise what ssh / batch ping actually do, and the password
    must not outlive an idle window while tmux panes hold switch logins open."""

    def test_marked_label_counts_what_will_be_used(self):
        self.assertEqual(tl.marked_label(0, 0), "")
        self.assertEqual(tl.marked_label(3, 3), "3 marked")
        self.assertEqual(tl.marked_label(3, 1), "1 marked (+2 hidden)")
        self.assertEqual(tl.marked_label(3, 0), "0 marked (+3 hidden)")

    def test_the_password_expires_a_fixed_time_after_it_was_typed(self):
        """Absolute, not idle: touching the window must not keep a live credential
        alive for days.  10 h = never during a working day, always gone by morning."""
        now = 1_000_000.0
        life = tl.PASSWORD_LIFETIME_MINUTES
        self.assertEqual(life, 600)                                   # 10 hours
        self.assertFalse(tl.creds_expired(now, now - 9 * 3600, life))       # same working day
        self.assertTrue(tl.creds_expired(now, now - 11 * 3600, life))       # next morning
        self.assertFalse(tl.creds_expired(now, now, life))
        self.assertFalse(tl.creds_expired(now, now - 100 * 3600, 0))        # 0 = never

    def test_password_lifetime_is_configurable_and_bounded(self):
        self.assertEqual(tl.load_config(args()).password_lifetime, tl.PASSWORD_LIFETIME_MINUTES)
        with self.assertRaises(tl.ConfigError):
            tl.parse_int("1441", "password_lifetime", 0, 1440)

    def test_minutes_are_never_reported_as_a_rounded_lie(self):
        self.assertEqual(tl.minutes_text(600), "10 h")
        self.assertEqual(tl.minutes_text(90), "1 h 30 min")       # was reported as "2 h"
        self.assertEqual(tl.minutes_text(60), "1 h")
        self.assertEqual(tl.minutes_text(45), "45 min")


START, END = "\x1b[200~", "\x1b[201~"


class FakeWin(object):
    """Feeds a character stream to read_key the way curses would."""

    def __init__(self, text):
        self.buf = list(text)

    def timeout(self, ms):
        pass

    def get_wch(self):
        if not self.buf:
            raise tl.curses.error("no input")
        return self.buf.pop(0)


class TestPaste(unittest.TestCase):
    """A pasted newline used to arrive as Enter, which ran ssh on whatever switch
    happened to be selected.  Pasted text must be text."""

    def test_control_characters_never_become_keys(self):
        self.assertEqual(tl.paste_text("ber-core-01\n"), "ber-core-01")
        self.assertEqual(tl.paste_text("a\tb"), "ab")                  # a tab would mark a switch
        self.assertEqual(tl.paste_text("10.0.0.1\r\n10.0.0.2\n"), "10.0.0.1 10.0.0.2")
        self.assertEqual(tl.paste_text(""), "")
        self.assertEqual(tl.paste_text(None), "")

    def test_a_password_field_takes_only_the_first_line(self):
        self.assertEqual(tl.paste_text("secret\n", multiline=False), "secret")
        self.assertEqual(tl.paste_text("secret\nmore", multiline=False), "secret")

    def test_long_pastes_are_capped(self):
        self.assertEqual(len(tl.paste_text("x" * 5000)), tl.MAX_PASTE)

    def test_the_markers_are_parsed_as_keys(self):
        self.assertEqual(tl.parse_escape_sequence("[200~"), "PASTE_START")
        self.assertEqual(tl.parse_escape_sequence("[201~"), "PASTE_END")

    def test_an_oversized_paste_is_fully_drained(self):
        """The cap limits what we KEEP, never what we consume.  Stopping early left the
        rest of the paste in the input queue, where its newlines became Enter again -
        and Enter runs ssh on the selected switch."""
        keys = self.drain(START + "10.0.0.1\n" * 200 + END)
        self.assertEqual([k for k in keys if k != "PASTE"], [],
                         "characters leaked out of the paste and were read as keys")
        self.assertEqual(keys.count("PASTE"), 1)

    def test_a_paste_without_an_end_marker_still_terminates(self):
        keys = self.drain(START + "abc")            # terminal stops mid-paste
        self.assertEqual(keys, ["PASTE"])

    def drain(self, text):
        """Every key read_key reports for this character stream, as the app sees it."""
        win, out = FakeWin(text), []
        while win.buf:
            key = tl.read_key(win, 250)
            if key is not None:
                out.append(key)
        return out


class TestLatency(unittest.TestCase):
    def test_rtt_is_parsed_from_ping_output(self):
        line = "64 bytes from 10.0.0.1: icmp_seq=1 ttl=63 time=1.23 ms"
        self.assertAlmostEqual(tl.parse_rtt(line), 1.23)
        self.assertAlmostEqual(tl.parse_rtt("... time<1 ms"), 1.0)      # some pings report "<"
        self.assertIsNone(tl.parse_rtt("Request timeout for icmp_seq 0"))
        self.assertIsNone(tl.parse_rtt(""))

    def test_rtt_fits_a_narrow_column(self):
        width = dict((label, w) for label, w, _, _ in tl.STATUS_COLUMNS)["ms"]
        for ms in (0.84, 1.23, 12.4, 99.9, 180.0, 1204.7):
            self.assertLessEqual(len(tl.format_rtt(ms)), width, ms)
        self.assertEqual(tl.format_rtt(None), "")

    def test_the_ms_column_sorts_slowest_first(self):
        headers = ["Name", "IP"]
        rows = [dict(zip(headers, r)) for r in (("a", "10.0.0.1"), ("b", "10.0.0.2"),
                                                ("c", "10.0.0.3"), ("d", "10.0.0.4"))]
        cfg = types.SimpleNamespace(columns=[("Name", "Name"), ("IP", "IP")])
        devices = tl.build_devices(headers, rows, cfg)[0]
        rtt = {"10.0.0.1": 5.0, "10.0.0.2": 200.0, "10.0.0.3": 50.0}      # d never answered
        status = [{}, rtt, {}]
        col = len(cfg.columns) + tl.STATUS_KINDS.index("rtt")
        order = [d.name for d in tl.sort_devices(devices, col, False, status)]
        self.assertEqual(order, ["b", "c", "a", "d"])        # slowest first, unknown last

    def test_zero_ms_is_a_measurement_not_a_missing_value(self):
        """0.0 is falsy, so a truthiness test put a real reading in the never-measured
        group at the bottom while draw() still printed it.  The row order matters here:
        'never' comes first in the CSV, so a 0.0 wrongly grouped with it ends up AFTER
        it - which is how this test tells the two behaviours apart."""
        headers = ["Name", "IP"]
        rows = [dict(zip(headers, r)) for r in (("never", "10.0.0.3"), ("zero", "10.0.0.1"),
                                                ("slow", "10.0.0.2"))]
        cfg = types.SimpleNamespace(columns=[("Name", "Name"), ("IP", "IP")])
        devices = tl.build_devices(headers, rows, cfg)[0]
        status = [{}, {"10.0.0.1": 0.0, "10.0.0.2": 5.0}, {}]
        col = len(cfg.columns) + tl.STATUS_KINDS.index("rtt")
        order = [d.name for d in tl.sort_devices(devices, col, False, status)]
        self.assertEqual(order, ["slow", "zero", "never"])    # measured first, 0.0 included


class TestSecurityHelpers(unittest.TestCase):
    def test_valid_host(self):
        for ok in ("10.0.0.1", "sw1.example.com", "fe80::1%eth0", "SW_01"):
            self.assertTrue(tl.valid_host(ok), ok)
        for bad in ("", "-oProxyCommand=sh", "a b", "x;rm -rf /", "$(id)", "a\nb"):
            self.assertFalse(tl.valid_host(bad), bad)

    def test_valid_user(self):
        self.assertTrue(tl.valid_user("timmy.r"))
        for bad in ("", "-l", "a b", "a@b"):
            self.assertFalse(tl.valid_user(bad), bad)

    def test_password_prompt_detection(self):
        for p in ("Password:", "admin@10.0.0.1's password: ", "Enter Password : ", "PASSWORD:"):
            self.assertTrue(tl.is_password_prompt(p), p)
        for p in ("Enter passphrase for key '/home/u/.ssh/id_rsa': ", "Verification code:",
                  "password policy updated", "login:"):
            self.assertFalse(tl.is_password_prompt(p), p)

    def test_ssh_argv(self):
        cfg = tl.load_config(args())
        cfg.ssh_options = ["-o", "StrictHostKeyChecking=yes"]
        argv = tl.build_ssh_argv(cfg, "timmy", "10.0.0.1", inject_password=True)
        self.assertEqual(argv[:3], ["ssh", "-o", "StrictHostKeyChecking=yes"])   # user options first
        self.assertIn("NumberOfPasswordPrompts=1", argv)
        self.assertEqual(argv[-4:], ["-l", "timmy", "--", "10.0.0.1"])
        self.assertNotIn("NumberOfPasswordPrompts=1", tl.build_ssh_argv(cfg, "t", "h", inject_password=False))


class TestExport(TempDir):
    def devices(self):
        headers = ["Name", "IP"]
        rows = [{"Name": "sw1", "IP": "10.0.0.1"}]
        cfg = types.SimpleNamespace(columns=[("Name", "Name"), ("IP", "IP")])
        return tl.build_devices(headers, rows, cfg)[0], headers

    def test_two_exports_in_the_same_second_do_not_collide(self):
        devices, headers = self.devices()
        path = os.path.join(self.tmp, "export.csv")
        status, checked = {"ping": {"10.0.0.1": tl.PING_UP}, "ssh": {}}, {("ping", "10.0.0.1"): 100}
        first = tl.export_csv(path, devices, headers, ";", status, checked)
        second = tl.export_csv(path, devices, headers, ";", status, checked)
        self.assertEqual(first, path)
        self.assertEqual(second, os.path.join(self.tmp, "export-2.csv"))
        self.assertEqual(os.stat(second).st_mode & 0o777, 0o600)
        with open(second, encoding="utf-8-sig") as f:
            self.assertIn("Ping", f.readline())

    def test_free_path_gives_up_instead_of_looping(self):
        path = os.path.join(self.tmp, "x.csv")
        open(path, "w").close()
        open(os.path.join(self.tmp, "x-2.csv"), "w").close()
        self.assertEqual(tl.free_path(path), os.path.join(self.tmp, "x-3.csv"))
        with self.assertRaises(OSError):
            tl.free_path(path, limit=2)


class TestCharset(TempDir):
    def test_setting_and_flag(self):
        self.assertEqual(tl.detect_charset("ascii"), "ascii")
        self.assertEqual(tl.detect_charset("unicode"), "unicode")
        self.assertIn(tl.detect_charset("auto"), ("ascii", "unicode"))
        self.assertEqual(tl.load_config(args(ascii=True)).charset_setting, "ascii")
        with self.assertRaises(tl.ConfigError):
            tl.load_config(args(config=self.write("c.conf", "[tree-li]\ncharset = emoji\n")))

    def test_symbol_sets_match(self):
        self.assertEqual(set(tl.CHARSETS["ascii"]), set(tl.CHARSETS["unicode"]))
        for value in tl.CHARSETS["ascii"].values():
            value.encode("ascii")
        self.assertEqual(len(tl.CHARSETS["unicode"]["box"]), 6)


class TestKeys(unittest.TestCase):
    def test_escape_sequences(self):
        cases = {"": "ESC", "[A": "UP", "OA": "UP", "[11~": "F1", "OP": "F1", "[[E": "F5",
                 "[17~": "F6", "[1;5A": "UP", "[15;2~": "F5", "[5~": "PGUP", "[Z": "BTAB", "[999~": None}
        for seq, key in cases.items():
            self.assertEqual(tl.parse_escape_sequence(seq), key, seq)


class TestDrawingHelpers(unittest.TestCase):
    def test_fit(self):
        self.assertEqual(tl.fit("abc", 5), "abc  ")
        self.assertEqual(tl.fit("abcdef", 4), "abc~")
        self.assertEqual(tl.fit("abcdef", 4, "\u2026"), "abc\u2026")

    def test_fit_widths(self):
        self.assertEqual(sum(tl.fit_widths([40, 20, 6], 50)), 50)
        self.assertEqual(tl.fit_widths([10, 10], 50), [10, 10])

    def test_wrap(self):
        self.assertEqual(tl.wrap_lines(["a" * 25, ""], 10), ["a" * 10, "a" * 10, "a" * 5, ""])


class TestProcStream(unittest.TestCase):
    def test_stream_collects_output(self):
        s = tl.ProcStream([sys.executable, "-c", "print('hello'); print('world')"])
        for _ in range(100):
            if s.done:
                break
            time.sleep(0.05)
        self.assertTrue(s.done)
        self.assertEqual(s.returncode, 0)
        self.assertIn("hello", s.snapshot())
        self.assertIn("world", s.snapshot())

    def test_missing_binary(self):
        s = tl.ProcStream(["/nonexistent/binary"])
        self.assertTrue(s.done)
        self.assertEqual(s.returncode, 127)


if __name__ == "__main__":
    unittest.main()
