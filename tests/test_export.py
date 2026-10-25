"""Ctrl-E: the current view and its results as a CSV (D50)."""

import csv
import os
import types
import unittest

from support import TempDir
from truffle import export, inventory
from truffle.results import Results


class TestExport(TempDir):

    def setUp(self):
        TempDir.setUp(self)
        cfg = types.SimpleNamespace(columns=[("Name", "Name"), ("IP", "IP")])
        headers = ["Name", "IP", "location"]
        rows = [{"Name": "ab-12-s34-w4", "IP": "10.0.0.1", "location": "Zürich"},
                {"Name": "=HYPERLINK(1)", "IP": "10.0.0.2", "location": "-"}]
        self.headers = headers
        self.devices = inventory.build_devices(headers, rows, cfg)[0]
        self.results = Results()
        self.results.set("ping", "10.0.0.1", "down", 1_000_000_000)
        self.results.set("ssh", "10.0.0.1", "failed", 1_000_000_100, "Connection timed out (exit 255)")

    def read(self, path, delimiter=";"):
        with open(path, encoding="utf-8-sig", newline="") as f:
            return list(csv.reader(f, delimiter=delimiter))

    def test_every_column_and_the_results(self):
        path = export.export_csv(os.path.join(self.tmp, "x.csv"), self.devices, self.headers, ";", self.results)
        rows = self.read(path)
        self.assertEqual(rows[0], self.headers + export.EXTRA_HEADERS)
        first = dict(zip(rows[0], rows[1]))
        self.assertEqual(first["location"], "Zürich")
        self.assertEqual(first["Ping"], "down")
        self.assertTrue(first["Ping checked"])
        self.assertEqual(first["SSH last try"], "failed")
        self.assertEqual(first["SSH reason"], "Connection timed out (exit 255)")
        second = dict(zip(rows[0], rows[2]))
        self.assertEqual(second["Ping"], "")                                  # never checked

    def test_private_never_over_an_existing_file_and_excel_safe(self):
        path = os.path.join(self.tmp, "x.csv")
        first = export.export_csv(path, self.devices, self.headers, ";", self.results)
        second = export.export_csv(path, self.devices, self.headers, ";", self.results)
        self.assertEqual(first, path)
        self.assertEqual(second, os.path.join(self.tmp, "x-2.csv"))
        self.assertEqual(os.stat(second).st_mode & 0o777, 0o600)
        with open(first, "rb") as f:
            self.assertTrue(f.read().startswith(b"\xef\xbb\xbf"))           # BOM: Excel reads UTF-8
        rows = self.read(first)
        self.assertEqual(rows[2][0], "'=HYPERLINK(1)")                        # no formula from the IPAM
        self.assertEqual(rows[2][2], "-")                                     # a plain "-" stays

    def test_the_delimiter_of_the_switch_list(self):
        path = export.export_csv(os.path.join(self.tmp, "x.csv"), self.devices, self.headers, ",", self.results)
        self.assertEqual(self.read(path, ",")[0][0], "Name")

    def test_named_by_time_in_the_folder_and_found_again(self):
        path = export.export_path(self.tmp, now=1_000_000_000)
        self.assertTrue(os.path.basename(path).startswith("truffle-export-"))
        written = export.export_csv(path, self.devices, self.headers, ";", self.results)
        self.assertEqual(export.exports_since(0, self.tmp), [written])
        os.utime(written, (10, 10))
        self.assertEqual(export.exports_since(100, self.tmp), [])


if __name__ == "__main__":
    unittest.main()
