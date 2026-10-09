"""Unit tests for the logic in truffle (stdlib unittest only).

Run from the repository root:  python3 -m unittest discover -s tests -v
"""
import contextlib
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
_loader = importlib.machinery.SourceFileLoader("truffle", os.path.join(ROOT, "truffle"))
_spec = importlib.util.spec_from_loader("truffle", _loader)
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
        devices, columns, warns, picked = tl.build_devices(*tl.read_table(p), cfg=cfg)
        self.assertEqual(devices[0].host, "10.0.0.1")
        self.assertEqual(devices[0].name, "sw1")
        self.assertEqual([c[1] for c in columns], ["Name", "IP", "subnet", "Alias"])
        self.assertTrue(any("comment" in w for w in warns))

    # An Infoblox network export: the hostname is in PRIMARY_DN_CODE, the host address in
    # ADDRESS, and the FIRST column is the SUBNET - which must never be used as either.
    INFOBLOX = ("SUBNET,MASK,VLAN_ID,PRIMARY_DN_CODE,CREATION_DATE,Default-GW,Name-Server,"
                "WINS-Server,BootP_NextServer,BootP_BootFile,MAC_ADDRESS,RFC_MAC_ADDRESS,ADDRESS\n"
                '192.0.2.96,255.255.255.224,43,ab-12-s34-r1.example.net,"1970-01-01 00:00:00.000"'
                ",,,,,,,,192.0.2.98\n"
                '198.51.100.0,255.255.255.0,2301,cd-34-s56-r1.example.net,"1970-01-01 00:00:00.000"'
                ",,,,,,,,198.51.100.20\n"
                '198.51.100.0,255.255.255.0,2301,cd-34-s56-r2.example.net,"1970-01-01 00:00:00.000"'
                ",,,,,,,,198.51.100.21\n")

    def test_infoblox_export_without_labels_warns_instead_of_using_the_subnet(self):
        """With no Name column the first one was used silently - so two switches in one
        subnet shared an identity, and favourites and history went with it."""
        p = self.write("ib.csv", self.INFOBLOX)
        report = {}
        devices, columns, warns, picked = tl.build_devices(*tl.read_table(p, report),
                                                           cfg=tl.load_config(args()))
        self.assertEqual(picked["host"], "ADDRESS")          # not SUBNET: the host address
        self.assertEqual(picked["name"], "SUBNET")           # the silent fallback ...
        self.assertTrue(any("no 'Name' column" in w for w in warns), warns)   # ... now says so
        issues = tl.data_issues(devices, report["lines"], report["issues"])
        self.assertTrue(any("appears 2 times" in i for i in issues), issues)

    def test_infoblox_export_with_labelled_columns_is_clean(self):
        """columns = PRIMARY_DN_CODE:Name, ADDRESS:IP is the whole fix - no code change.
        The label picks the column, so an export with its own header names just works."""
        p = self.write("ib2.csv", self.INFOBLOX)
        conf = self.write("ib.conf", "[truffle]\ndata = %s\n"
                          "columns = PRIMARY_DN_CODE:Name, ADDRESS:IP\n" % p)
        report = {}
        devices, columns, warns, picked = tl.build_devices(
            *tl.read_table(p, report), cfg=tl.load_config(args(config=conf)))
        self.assertEqual(warns, [])
        self.assertEqual(picked, {"name": "PRIMARY_DN_CODE", "host": "ADDRESS"})
        self.assertEqual([c[1] for c in columns], ["Name", "IP"])
        self.assertEqual([d.name for d in devices],
                         ["ab-12-s34-r1.example.net", "cd-34-s56-r1.example.net",
                          "cd-34-s56-r2.example.net"])
        self.assertEqual([d.host for d in devices], ["192.0.2.98", "198.51.100.20", "198.51.100.21"])
        self.assertEqual(tl.data_issues(devices, report["lines"], report["issues"]), [])
        self.assertEqual(report["delimiter"], ",")           # comma-separated, auto-detected
        # the columns nobody asked for are still searchable and shown by "details"
        self.assertEqual(devices[1].values["VLAN_ID"], "2301")

    def test_a_columns_line_that_does_not_fit_falls_back_to_name_and_address(self):
        """Field bug: with the default columns line only 'subnet' matched the Infoblox
        export, so the table showed one column of NETWORK addresses and nothing else."""
        p = self.write("fit.csv", self.INFOBLOX)
        devices, columns, warns, picked = tl.build_devices(*tl.read_table(p),
                                                           cfg=tl.load_config(args()))
        self.assertEqual([c[1] for c in columns], ["Name", "IP"])
        self.assertEqual(columns[1][0], "ADDRESS")            # the switch address, not SUBNET
        self.assertEqual(devices[0].cells[1], "192.0.2.98")
        self.assertTrue(any("falls back to the switch name and its address" in w for w in warns), warns)

    def test_rows_with_an_empty_name_column_are_reported(self):
        """Field bug: the Name column was recognised but stayed empty.  The switch itself
        falls back to its IP, so nothing looked wrong until the table was on screen."""
        p = self.write("blank.csv", "SUBNET,PRIMARY_DN_CODE,ADDRESS\n"
                                    "198.51.100.0,,198.51.100.20\n"
                                    "198.51.100.0,,198.51.100.21\n"
                                    "192.0.2.96,ab-12-s34-r1.example.net,192.0.2.98\n")
        conf = self.write("blank.conf", "[truffle]\ndata = %s\n"
                          "columns = PRIMARY_DN_CODE:Name, ADDRESS:IP\n" % p)
        report = {}
        devices, _, _, picked = tl.build_devices(*tl.read_table(p, report),
                                                 cfg=tl.load_config(args(config=conf)))
        issues = tl.data_issues(devices, report["lines"], report["issues"], picked["name"])
        self.assertTrue(any("nothing in the name column 'PRIMARY_DN_CODE'" in i for i in issues), issues)
        self.assertTrue(any("lines 2, 3" in i for i in issues), issues)
        self.assertEqual(devices[0].name, "198.51.100.20")      # falls back to the address
        self.assertEqual(devices[0].cells[0], "")               # but the NAME cell is empty
        # a fully named list must not be warned about
        clean = self.write("ok.csv", "SUBNET,PRIMARY_DN_CODE,ADDRESS\n"
                                     "192.0.2.96,ab-12-s34-r1.example.net,192.0.2.98\n")
        rep2 = {}
        devs, _, _, pick2 = tl.build_devices(*tl.read_table(clean, rep2),
                                             cfg=tl.load_config(args(config=conf)))
        self.assertEqual(tl.data_issues(devs, rep2["lines"], rep2["issues"], pick2["name"]), [])

    def test_the_warning_names_the_column_that_probably_holds_the_hostname(self):
        """The real failure: Infoblox's 'Name-Server' had been renamed to 'Name', so the
        name column resolved and was empty for all 843 rows.  Saying "it is empty" was not
        enough - the warning has to point at PRIMARY_DN_CODE."""
        p = self.write("hint.csv",
                       "SUBNET,MASK,VLAN_ID,PRIMARY_DN_CODE,CREATION_DATE,Name,IP\n"
                       '192.0.2.96,255.255.255.224,43,ab-12-s34-r1.example.net,'
                       '"1970-01-01 00:00:00.000",,192.0.2.98\n')
        report = {}
        devices, _, _, picked = tl.build_devices(*tl.read_table(p, report),
                                                 cfg=tl.load_config(args()))
        self.assertEqual(picked["name"], "Name")              # resolves, but is empty
        self.assertEqual(picked["host"], "IP")
        issues = tl.data_issues(devices, report["lines"], report["issues"], picked["name"])
        hint = " ".join(issues)
        self.assertIn("columns = PRIMARY_DN_CODE:Name", hint)
        # the mask, the vlan and the date must not be offered as hostname candidates
        for noise in ("255.255.255.224", "MASK", "VLAN_ID", "CREATION_DATE"):
            self.assertNotIn(noise, hint, hint)

    def test_the_label_wins_over_a_same_named_header(self):
        """A CSV that has its own 'Name'/'IP' columns AND a label must follow the label -
        otherwise you could never point TRuffle at a different column."""
        p = self.write("both.csv", "Name,IP,PRIMARY_DN_CODE,ADDRESS\n"
                                   "wrong,10.0.0.1,right.example.net,10.0.0.9\n")
        conf = self.write("both.conf", "[truffle]\ndata = %s\n"
                          "columns = PRIMARY_DN_CODE:Name, ADDRESS:IP\n" % p)
        devices, _, _, picked = tl.build_devices(*tl.read_table(p), cfg=tl.load_config(args(config=conf)))
        self.assertEqual(picked, {"name": "PRIMARY_DN_CODE", "host": "ADDRESS"})
        self.assertEqual(devices[0].name, "right.example.net")
        self.assertEqual(devices[0].host, "10.0.0.9")

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
        devices = tl.build_devices(*tl.read_table(p, report), cfg=tl.load_config(args()))[0]
        self.assertEqual(report["lines"], [2, 3, 4, 5, 6, 7, 8])
        issues = "\n".join(tl.data_issues(devices, report["lines"], report["issues"]))
        for expected in ("line 8: 4 fields, the header has 3", "IP 10.0.0.1 is used 2 times",
                         "name 'sw1' appears 2 times: lines 2, 4", "'10.0.0.300' is not a valid IPv4",
                         "leading zeros", "line 7: 'sw6' has no IP"):
            self.assertIn(expected, issues)

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
        conf = self.write("my.conf", "[truffle]\ndata = lists/sw.csv\n"
                          "columns = Name, location:Where\nsession_log = yes\nuser = netadmin\n")
        cfg = tl.load_config(args(config=conf))
        self.assertEqual(cfg.data, os.path.join(self.tmp, "lists", "sw.csv"))
        self.assertEqual(cfg.columns, [("Name", "Name"), ("location", "Where")])
        self.assertTrue(cfg.session_log)
        self.assertEqual(cfg.user, "netadmin")

    def test_unknown_option_and_bad_values(self):
        for body in ("[truffle]\ndatta = x\n", "[truffle]\nping_rate = lots\n",
                     "[truffle]\nsession_log = maybe\n", "[other]\n", "[truffle]\nuser = -oProxyCommand=x\n"):
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
            d.lsegments = [tl.segments_of(c) for c in d.lcells]
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
                     "ctrl-e", "export",                 # CSV export removed (D35)
                     "round-trip", "slowest"):           # MS column removed (D36)
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

    SOURCE = open(os.path.join(ROOT, "truffle"), encoding="utf-8").read()

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
    def run_check(self, csv_body):
        data = self.write("sw.csv", csv_body)
        return self.check(self.write("c.conf", "[truffle]\ndata = %s\n" % data))

    def check(self, conf):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = tl.check(tl.load_config(args(config=conf)))
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
        path = self.write("c.conf", "[truffle]\ndata = %s/nope.csv\n" % self.tmp)
        self.assertEqual(self.check(path)[0], 2)

    def test_a_retired_option_is_a_hard_error_not_a_silent_note(self):
        """Back-compat for old config files was dropped on purpose: a stale option now
        refuses to start and names itself, instead of being quietly ignored."""
        data = self.write("sw.csv", self.COLUMNS + "sw1;10.0.0.1;a;b;c\n")
        path = self.write("c.conf", "[truffle]\ndata = %s\nping_workers = 200\n" % data)
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
        self.devices, columns = tl.build_devices(headers, rows, cfg)[:2]
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


class TestPatternAndOrSearch(unittest.TestCase):
    """Site naming is xx-xx-sxx-ROLE.domain, so the role is the thing you filter on."""

    ROLES = ("ab-12-s34-l1", "ab-12-s34-l11", "ab-12-s34-w3", "ab-12-s34-w4",
             "cd-34-s56-l1", "cd-34-s56-w3", "cd-34-s56-w4", "legacy-core-01")

    def setUp(self):
        headers = ["Name", "IP"]
        rows = [{"Name": n + ".example.net", "IP": "192.0.2.%d" % (i + 1)}
                for i, n in enumerate(self.ROLES)]
        cfg = types.SimpleNamespace(columns=[("Name", "Name"), ("IP", "IP")])
        self.devices, columns, _, _ = tl.build_devices(headers, rows, cfg)
        self.fields = dict((h.lower(), h) for h in headers)

    def names(self, query, **kw):
        return [d.name.split(".")[0] for d in tl.filter_devices(self.devices, query, self.fields, **kw)]

    def test_a_pattern_tells_l1_from_l11(self):
        """The point of patterns: an exact role match, which fuzzy and substring cannot do.
        These names are FQDNs, so the pattern is tried against the host part too - that is
        what makes the short form work."""
        self.assertEqual(self.names("*-l1"), ["ab-12-s34-l1", "cd-34-s56-l1"])
        self.assertEqual(self.names("*-l1.*"), self.names("*-l1"))   # the explicit form
        self.assertEqual(self.names("??-??-s??-l1"), self.names("*-l1"))
        self.assertIn("ab-12-s34-l11", self.names("l1"))             # fuzzy is too loose
        # a trailing * after the role swallows the rest, l11 included - say so, do not pretend
        self.assertIn("ab-12-s34-l11", self.names("*-l1*"))

    def test_patterns_over_other_columns(self):
        self.assertEqual(self.names("ab-*"), ["ab-12-s34-l1", "ab-12-s34-l11",
                                              "ab-12-s34-w3", "ab-12-s34-w4"])
        self.assertEqual(self.names("*nothinglikethis*"), [])
        self.assertEqual(self.names("192.0.2.?"), [d.name.split(".")[0] for d in self.devices])
        self.assertEqual(self.names("*-2"), [])
        # the host-part try must not let a pattern match an address through its first octet
        self.assertEqual(self.names("19?"), [])
        self.assertTrue(tl.glob_match("ab-12-s34-l1.example.net", "*-l1"))
        self.assertFalse(tl.glob_match("ab-12-s34-l11.example.net", "*-l1"))
        self.assertFalse(tl.glob_match("192.0.2.98", "19?"))         # not split on dots
        self.assertTrue(tl.glob_match("192.0.2.98", "192.0.2.*"))

    def test_or_inside_one_term(self):
        self.assertEqual(self.names("w3|w4"), ["ab-12-s34-w3", "ab-12-s34-w4",
                                               "cd-34-s56-w3", "cd-34-s56-w4"])
        self.assertEqual(self.names("*-w3|*-w4"), self.names("w3|w4"))
        # AND still narrows: site ab AND (w3 or w4)
        self.assertEqual(self.names("ab-* w3|w4"), ["ab-12-s34-w3", "ab-12-s34-w4"])
        # space is still AND, so this asks for both at once and finds nothing
        self.assertEqual(self.names("w3 w4"), [])

    def test_a_negated_group_excludes_every_alternative(self):
        self.assertEqual(self.names("-*-w3|*-w4"),
                         ["ab-12-s34-l1", "ab-12-s34-l11", "cd-34-s56-l1", "legacy-core-01"])

    def test_alternatives_inherit_the_field_prefix(self):
        status = {"status": {"ping": {"192.0.2.1": tl.PING_UP, "192.0.2.2": tl.WAIT,
                                      "192.0.2.3": tl.PING_DOWN}}}
        self.assertEqual(self.names("ping:up|wait", **status),
                         ["ab-12-s34-l1", "ab-12-s34-l11"])
        self.assertEqual(self.names("name:*-w4|*-l1"),           # list order, not query order
                         ["ab-12-s34-l1", "ab-12-s34-w4", "cd-34-s56-l1", "cd-34-s56-w4"])

    def test_a_half_typed_term_filters_nothing(self):
        for partial in ("|", "'", "-", "-'", "w3|", "|w3"):
            self.assertTrue(self.names(partial), "%r should not empty the list" % partial)

    def test_is_marked_shows_what_you_collected(self):
        picked = {"ab-12-s34-w3.example.net": True, "cd-34-s56-l1.example.net": True}
        self.assertEqual(self.names("is:marked", marked=picked),
                         ["ab-12-s34-w3", "cd-34-s56-l1"])
        self.assertEqual(self.names("is:marked", marked={}), [])


class TestFuzzyMatch(unittest.TestCase):
    def test_match_and_positions(self):
        self.assertEqual(tl.fuzzy_match("bc01", "ber-core-01")[1], (0, 4, 9, 10))
        self.assertIsNone(tl.fuzzy_match("cb", "ber-core-01"))                 # order matters
        self.assertEqual(tl.fuzzy_match("core", "ber-core-01")[1], (4, 5, 6, 7))

    def test_scores(self):
        exact = tl.fuzzy_match("core", "ber-core-01")[0]
        split = tl.fuzzy_match("bc01", "ber-core-01")[0]                       # b|c|01, all at starts
        at_start = tl.fuzzy_match("cor", "ber-core-01")[0]                     # 'core' begins here
        mid_word = tl.fuzzy_match("ore", "ber-core-01")[0]                     # sits inside 'core'
        self.assertGreater(exact, split)                                       # written together wins
        self.assertGreater(at_start, mid_word)                                 # segment starts score higher

    def test_a_word_may_only_be_split_at_the_separators(self):
        """The rule the whole search rests on: inside a segment the letters must be
        written together; only a separator allows the search to jump ahead."""
        self.assertIsNotNone(tl.fuzzy_match("w4", "xx-xx-sxx-w4"))             # together in a segment
        self.assertIsNone(tl.fuzzy_match("w4", "wx-x4-sxx-xx"))                # 4 buried inside 'x4'
        self.assertIsNone(tl.fuzzy_match("cr01", "ber-core-01"))               # 'o' skipped inside 'core'
        self.assertIsNone(tl.fuzzy_match("a4", "ab-12-s34-w4"))                # 4 buried inside 'w4'
        for pattern in ("bc01", "ab12", "s34", "12s", "ab-s34", "x4"):
            self.assertIsNotNone(tl.fuzzy_match(pattern, {"bc01": "ber-core-01",
                                                          "x4": "wx-x4-sxx-xx"}.get(pattern, "ab-12-s34-w4")),
                                 "%r should still be found" % pattern)

    def test_segments_of(self):
        self.assertEqual(tl.segments_of("ab-12-s34"), [(0, "ab"), (3, "12"), (6, "s34")])
        self.assertEqual(tl.segments_of("a..b"), [(0, "a"), (3, "b")])         # empty parts dropped
        self.assertEqual(tl.segments_of(""), [])
        self.assertEqual(tl.segments_of("plain"), [(0, "plain")])


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

    def test_set_or_clear_drops_empty_values(self):
        m = {("ssh", "h"): "old"}
        tl.set_or_clear(m, ("ssh", "h"), "")
        self.assertEqual(m, {})
        tl.set_or_clear(m, ("ssh", "h"), "why")
        self.assertEqual(m, {("ssh", "h"): "why"})

    def test_the_detail_field_round_trips_and_stays_backward_compatible(self):
        """The 5th field carries a detail - today the reason a ssh attempt failed.
        Rows without it must keep working - an older TRuffle writes only 4 fields,
        and a row with no detail is still written with 4 so an older one can read it."""
        d = os.path.join(self.tmp, "state")
        tl.UserState(d).save_status(
            {"ping": {"10.0.0.1": "up"}, "ssh": {"10.0.0.1": "failed"}},
            {("ping", "10.0.0.1"): 100, ("ssh", "10.0.0.1"): 100},
            {("ping", "10.0.0.1"): "1.25", ("ssh", "10.0.0.1"): "Connection timed out (exit 255)"})
        status, checked, detail = tl.UserState(d).load_status()
        self.assertEqual(detail[("ping", "10.0.0.1")], "1.25")
        self.assertEqual(detail[("ssh", "10.0.0.1")], "Connection timed out (exit 255)")
        # a result with no detail is written as 4 fields, readable by an older TRuffle
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
        comes back through this file - TRuffle then drops the password it holds."""
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


class TestPasswordLifetime(unittest.TestCase):
    """The password must not outlive a window left open for days."""

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


class TestPingVerdict(unittest.TestCase):
    """Field bug: pressing ESC while a ping was running recorded the switch as DOWN even
    though its replies were on the screen - a killed ping exits non-zero.  And a router
    answering "Destination Net Unreachable" prints a "76 bytes from ..." line and on macOS
    exits 0, so neither the text nor the exit code proves a reply.  Only "time=" does."""

    def test_a_cancelled_ping_that_already_had_replies_is_up(self):
        self.assertEqual(tl.ping_verdict(True, done=True, killed=True), tl.PING_UP)
        self.assertEqual(tl.ping_verdict(True, done=False, killed=True), tl.PING_UP)

    def test_a_cancelled_ping_with_no_reply_yet_records_nothing(self):
        """It proves nothing, so whatever was known before must survive."""
        self.assertIsNone(tl.ping_verdict(False, done=False, killed=True))
        self.assertIsNone(tl.ping_verdict(False, done=True, killed=True))

    def test_only_a_finished_ping_may_say_down(self):
        self.assertEqual(tl.ping_verdict(False, done=True, killed=False), tl.PING_DOWN)
        self.assertIsNone(tl.ping_verdict(False, done=False, killed=False))

    def test_ping_that_could_not_start_says_nothing_about_the_switch(self):
        self.assertIsNone(tl.ping_verdict(False, done=True, killed=False, started=False))

    def test_an_icmp_error_is_not_a_reply(self):
        """This is the text a router sends back; it must not read as a round-trip time."""
        unreachable = ("PING 192.0.2.77 (192.0.2.77): 56 data bytes\n"
                       "76 bytes from 198.51.100.1: Destination Net Unreachable\n"
                       "Request timeout for icmp_seq 0\n")
        self.assertFalse(tl.ping_replied(unreachable))
        self.assertEqual(tl.ping_verdict(tl.ping_replied(unreachable), done=True, killed=False),
                         tl.PING_DOWN)

    def test_only_a_time_field_counts_as_a_reply(self):
        self.assertTrue(tl.ping_replied("64 bytes from 10.0.0.1: icmp_seq=1 ttl=63 time=1.23 ms"))
        self.assertTrue(tl.ping_replied("... time<1 ms"))        # some pings report "<"
        self.assertTrue(tl.ping_replied("... time=0.0 ms"))      # a 0 ms reply is still a reply
        self.assertFalse(tl.ping_replied("Request timeout for icmp_seq 0"))
        self.assertFalse(tl.ping_replied(""))
        self.assertFalse(tl.ping_replied(None))

    def test_a_stream_that_cannot_start_is_marked_not_started(self):
        s = tl.ProcStream(["/nonexistent/ping"])
        self.assertTrue(s.done)
        self.assertFalse(s.started)
        self.assertFalse(s.killed)


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


class TestCharset(TempDir):
    def test_setting_and_flag(self):
        self.assertEqual(tl.detect_charset("ascii"), "ascii")
        self.assertEqual(tl.detect_charset("unicode"), "unicode")
        self.assertIn(tl.detect_charset("auto"), ("ascii", "unicode"))
        self.assertEqual(tl.load_config(args(ascii=True)).charset_setting, "ascii")
        with self.assertRaises(tl.ConfigError):
            tl.load_config(args(config=self.write("c.conf", "[truffle]\ncharset = emoji\n")))

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
