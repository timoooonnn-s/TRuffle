"""The switch list: CSV reading, which column is which, the data check."""

import os
import unittest

from support import args, TempDir
from truffle import config, inventory


class TestCsv(TempDir):
    def test_semicolon_with_bom_and_comments(self):
        p = self.write("a.csv", "﻿Name;IP;comment\n# comment line\n\nsw1;10.0.0.1;Zürich\n")
        headers, rows = inventory.read_table(p)
        self.assertEqual(headers, ["Name", "IP", "comment"])
        self.assertEqual(rows, [{"Name": "sw1", "IP": "10.0.0.1", "comment": "Zürich"}])

    def test_comma_autodetect_crlf_and_quotes(self):
        p = self.write("b.csv", 'Name,IP,comment\r\nsw1,10.0.0.1,"a, b"\r\n')
        _, rows = inventory.read_table(p)
        self.assertEqual(rows[0]["comment"], "a, b")

    def test_cp1252_fallback(self):
        p = self.write("c.csv", "Name;IP;comment\nsw1;10.0.0.1;Gr\xfcezi\n".encode("cp1252"), mode="wb")
        _, rows = inventory.read_table(p)
        self.assertEqual(rows[0]["comment"], "Grüezi")

    def test_short_and_long_rows_and_control_chars(self):
        p = self.write("d.csv", "Name;IP;comment\nsw1;10.0.0.1\nsw2;10.0.0.2;x\ty;extra\n")
        _, rows = inventory.read_table(p)
        self.assertEqual(rows[0]["comment"], "")
        self.assertEqual(rows[1]["comment"], "x y")

    def test_missing_and_empty(self):
        with self.assertRaises(inventory.DataError):
            inventory.read_table(os.path.join(self.tmp, "nope.csv"))
        with self.assertRaises(inventory.DataError):
            inventory.read_table(self.write("e.csv", "\n\n"))

    def test_build_devices_case_insensitive_and_warnings(self):
        p = self.write("f.csv", "name;ip;Subnet;aliases;location\nsw1;10.0.0.1;a;Core;Room 1\n")
        cfg = config.load_config(args())
        devices, columns, warns, picked = inventory.build_devices(*inventory.read_table(p), cfg=cfg)
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
        devices, columns, warns, picked = inventory.build_devices(*inventory.read_table(p, report),
                                                           cfg=config.load_config(args()))
        self.assertEqual(picked["host"], "ADDRESS")          # not SUBNET: the host address
        self.assertEqual(picked["name"], "SUBNET")           # the silent fallback ...
        self.assertTrue(any("no 'Name' column" in w for w in warns), warns)   # ... now says so
        issues = inventory.data_issues(devices, report["lines"], report["issues"])
        self.assertTrue(any("appears 2 times" in i for i in issues), issues)

    def test_infoblox_export_with_labelled_columns_is_clean(self):
        """columns = PRIMARY_DN_CODE:Name, ADDRESS:IP is the whole fix - no code change.
        The label picks the column, so an export with its own header names just works."""
        p = self.write("ib2.csv", self.INFOBLOX)
        conf = self.write("ib.conf", "[truffle]\ndata = %s\n"
                          "columns = PRIMARY_DN_CODE:Name, ADDRESS:IP\n" % p)
        report = {}
        devices, columns, warns, picked = inventory.build_devices(
            *inventory.read_table(p, report), cfg=config.load_config(args(config=conf)))
        self.assertEqual(warns, [])
        self.assertEqual(picked, {"name": "PRIMARY_DN_CODE", "host": "ADDRESS"})
        self.assertEqual([c[1] for c in columns], ["Name", "IP"])
        self.assertEqual([d.name for d in devices],
                         ["ab-12-s34-r1.example.net", "cd-34-s56-r1.example.net",
                          "cd-34-s56-r2.example.net"])
        self.assertEqual([d.host for d in devices], ["192.0.2.98", "198.51.100.20", "198.51.100.21"])
        self.assertEqual(inventory.data_issues(devices, report["lines"], report["issues"]), [])
        self.assertEqual(report["delimiter"], ",")           # comma-separated, auto-detected
        # the columns nobody asked for are still searchable and shown by "details"
        self.assertEqual(devices[1].values["VLAN_ID"], "2301")

    def test_a_columns_line_that_does_not_fit_falls_back_to_name_and_address(self):
        """Field bug: with the default columns line only 'subnet' matched the Infoblox
        export, so the table showed one column of NETWORK addresses and nothing else."""
        p = self.write("fit.csv", self.INFOBLOX)
        devices, columns, warns, picked = inventory.build_devices(*inventory.read_table(p),
                                                           cfg=config.load_config(args()))
        self.assertEqual([c[1] for c in columns], ["Name", "IP"])
        self.assertEqual(columns[1][0], "ADDRESS")            # the switch address, not SUBNET
        self.assertEqual(devices[0].cells[1], "192.0.2.98")
        self.assertTrue(any("falls back to the device name and its address" in w for w in warns), warns)

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
        devices, _, _, picked = inventory.build_devices(*inventory.read_table(p, report),
                                                 cfg=config.load_config(args(config=conf)))
        issues = inventory.data_issues(devices, report["lines"], report["issues"], picked["name"])
        self.assertTrue(any("nothing in the name column 'PRIMARY_DN_CODE'" in i for i in issues), issues)
        self.assertTrue(any("lines 2, 3" in i for i in issues), issues)
        self.assertEqual(devices[0].name, "198.51.100.20")      # falls back to the address
        self.assertEqual(devices[0].cells[0], "")               # but the NAME cell is empty
        # a fully named list must not be warned about
        clean = self.write("ok.csv", "SUBNET,PRIMARY_DN_CODE,ADDRESS\n"
                                     "192.0.2.96,ab-12-s34-r1.example.net,192.0.2.98\n")
        rep2 = {}
        devs, _, _, pick2 = inventory.build_devices(*inventory.read_table(clean, rep2),
                                             cfg=config.load_config(args(config=conf)))
        self.assertEqual(inventory.data_issues(devs, rep2["lines"], rep2["issues"], pick2["name"]), [])

    def test_the_warning_names_the_column_that_probably_holds_the_hostname(self):
        """The real failure: Infoblox's 'Name-Server' had been renamed to 'Name', so the
        name column resolved and was empty for all 843 rows.  Saying "it is empty" was not
        enough - the warning has to point at PRIMARY_DN_CODE."""
        p = self.write("hint.csv",
                       "SUBNET,MASK,VLAN_ID,PRIMARY_DN_CODE,CREATION_DATE,Name,IP\n"
                       '192.0.2.96,255.255.255.224,43,ab-12-s34-r1.example.net,'
                       '"1970-01-01 00:00:00.000",,192.0.2.98\n')
        report = {}
        devices, _, _, picked = inventory.build_devices(*inventory.read_table(p, report),
                                                 cfg=config.load_config(args()))
        self.assertEqual(picked["name"], "Name")              # resolves, but is empty
        self.assertEqual(picked["host"], "IP")
        issues = inventory.data_issues(devices, report["lines"], report["issues"], picked["name"])
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
        devices, _, _, picked = inventory.build_devices(*inventory.read_table(p), cfg=config.load_config(args(config=conf)))
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
        devices = inventory.build_devices(*inventory.read_table(p, report), cfg=config.load_config(args()))[0]
        self.assertEqual(report["lines"], [2, 3, 4, 5, 6, 7, 8])
        issues = "\n".join(inventory.data_issues(devices, report["lines"], report["issues"]))
        for expected in ("line 8: 4 fields, the header has 3", "IP 10.0.0.1 is used 2 times",
                         "name 'sw1' appears 2 times: lines 2, 4", "'10.0.0.300' is not a valid IPv4",
                         "leading zeros", "line 7: 'sw6' has no IP"):
            self.assertIn(expected, issues)

    def test_no_ip_column(self):
        p = self.write("g.csv", "Name;where\nsw1;x\n")
        cfg = config.load_config(args())
        with self.assertRaises(inventory.DataError):
            inventory.build_devices(*inventory.read_table(p), cfg=cfg)



class TestTypedTarget(unittest.TestCase):
    """D55: which searches are an address to connect to, and which stay a search."""

    def test_addresses(self):
        t = inventory.typed_target
        self.assertEqual(t(" 10.1.2.3 "), (None, "10.1.2.3"))
        self.assertEqual(t("sw-lab-17.example.net"), (None, "sw-lab-17.example.net"))
        self.assertEqual(t("admin@10.1.2.3"), ("admin", "10.1.2.3"))
        self.assertEqual(t("admin@sw1.lab"), ("admin", "sw1.lab"))

    def test_searches_stay_searches(self):
        t = inventory.typed_target
        for text in ("ber", "sw-1", "10.1.2", "10.1.2.300", "10.01.2.3", "1.2.3.4.5", "type:core",
                     "a b", "-x.y", "sw..lab", "*.lab", "@10.1.2.3", "-o@10.1.2.3", "a@b@10.1.2.3",
                     "10.1.2.3.", "'10.1.2.3"):
            self.assertIsNone(t(text), text)


if __name__ == "__main__":
    unittest.main()
