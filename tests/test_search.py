"""The search language and sorting."""

import types
import unittest

import support  # noqa: F401  (puts src/ on the path)
from truffle import inventory, results, search, sorting


class TestSearchSort(unittest.TestCase):
    def devices(self, rows):
        cfg = types.SimpleNamespace(columns=[("Name", "Name"), ("IP", "IP")])
        return inventory.build_devices(["Name", "IP"], [{"Name": n, "IP": ip} for n, ip in rows], cfg)[0]

    def test_filter_tokens_all_must_match(self):
        ds = self.devices([("ber-core-01", "10.0.0.1"), ("ber-acc-01", "10.0.0.2"), ("muc-core-01", "10.0.1.1")])
        self.assertEqual([d.name for d in search.filter_devices(ds, "core BER")], ["ber-core-01"])
        self.assertEqual(len(search.filter_devices(ds, "  ")), 3)
        # tokens never match across two fields
        self.assertEqual(search.filter_devices(ds, "01 10"), ds)
        self.assertEqual(search.filter_devices(ds, "0110"), [])

    def test_natural_sort_and_empty_last(self):
        ds = self.devices([("sw10", "10.0.0.10"), ("", "10.0.0.9"), ("sw2", "10.0.0.2")])
        self.assertEqual([d.cells[0] for d in sorting.sort_devices(ds, 0, False, {})], ["sw2", "sw10", ""])
        self.assertEqual([d.cells[0] for d in sorting.sort_devices(ds, 0, True, {})], ["sw10", "sw2", ""])
        self.assertEqual([d.host for d in sorting.sort_devices(ds, 1, False, {})],
                         ["10.0.0.2", "10.0.0.9", "10.0.0.10"])

    def test_sort_key_cycle_and_off(self):
        state = (None, False)
        seen = []
        for _ in range(4):
            state = sorting.next_sort(state[0], state[1], 2)
            seen.append(state)
        self.assertEqual(seen, [(2, False), (2, True), (None, False), (2, False)])
        self.assertEqual(sorting.next_sort(2, True, 0), (0, False))           # other column: ascending

    def test_sort_off_restores_csv_order(self):
        ds = self.devices([("sw10", "1"), ("sw2", "2"), ("sw1", "3")])
        sorted_once = sorting.sort_devices(ds, 0, False, {})
        self.assertEqual([d.name for d in sorting.sort_devices(ds, None, False, {})], ["sw10", "sw2", "sw1"])
        self.assertNotEqual(sorted_once, ds)

    def test_sort_by_ping_down_first(self):
        ds = self.devices([("a", "1"), ("b", "2"), ("c", "3")])
        ping = {"1": results.PING_UP, "2": results.PING_DOWN}
        ssh = {"1": results.SSH_OK, "3": results.SSH_FAILED}
        # indices come from STATUS_KINDS, not hardcoded: adding a status column must not
        # silently make this test sort a different column than its name says
        def col(kind):
            return len(ds[0].cells) + results.KINDS.index(kind)
        status = [ping if k == "ping" else ssh if k == "ssh" else {} for k in results.KINDS]
        self.assertEqual([d.name for d in sorting.sort_devices(ds, col("ping"), False, status)], ["b", "a", "c"])
        self.assertEqual([d.name for d in sorting.sort_devices(ds, col("ssh"), False, status)], ["c", "a", "b"])


class TestSearchSyntax(unittest.TestCase):
    def setUp(self):
        headers = ["Name", "IP", "type", "aliases", "location"]
        rows = [dict(zip(headers, r)) for r in (
            ("ber-core-01", "10.0.0.1", "core", "Core Berlin", "Room 1"),
            ("ber-edge-01", "10.0.0.2", "edge", "Edge Berlin", ""),
            ("muc-core-01", "fe80::1", "core", "Core Munich", "Room 9"),
            ("ber-test-01", "10.0.0.4", "edge", "Test", "Lab"))]
        cfg = types.SimpleNamespace(columns=[("Name", "Name"), ("IP", "IP"), ("aliases", "Alias")])
        self.devices, columns = inventory.build_devices(headers, rows, cfg)[:2]
        self.fields = dict((h.lower(), h) for h in headers)
        self.fields.update((label.lower(), h) for h, label in columns)

    def names(self, query, **kw):
        return [d.name for d in search.filter_devices(self.devices, query, self.fields, **kw)]

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
        ping = {"status": {"ping": {"10.0.0.1": results.PING_UP, "10.0.0.2": results.PING_DOWN}}}
        self.assertEqual(self.names("ping:down", **ping), ["ber-edge-01"])
        self.assertEqual(self.names("ping:none", **ping), ["muc-core-01", "ber-test-01"])
        self.assertEqual(self.names("-ping:up", **ping), ["ber-edge-01", "muc-core-01", "ber-test-01"])
        ssh = {"status": {"ssh": {"10.0.0.1": results.SSH_OK, "10.0.0.2": results.SSH_FAILED}}}
        self.assertEqual(self.names("ssh:failed", **ssh), ["ber-edge-01"])
        self.assertEqual(self.names("ssh:none", **ssh), ["muc-core-01", "ber-test-01"])
        self.assertEqual(self.names("is:fav", favorites={"ber-test-01"}), ["ber-test-01"])
        self.assertEqual(self.names("is:recent", recent={"muc-core-01": 5}), ["muc-core-01"])
        self.assertEqual(self.names("is:favs", favorites={"ber-test-01"}), [])  # no hidden aliases
        self.assertEqual(self.names("ping:wait", status={"ping": {"10.0.0.4": results.WAIT}}), ["ber-test-01"])
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
        view = search.filter_devices(self.devices, "core", self.fields, found=found)
        order = [d.name for d in search.default_order(view, "core", set(), {}, found)]
        self.assertEqual(order, ["ber-core-01", "muc-core-01"])
        d = next(d for d in view if d.name == "ber-core-01")
        self.assertEqual(found[d][1], {0: {4, 5, 6, 7}})                      # "core" in the Name column

    def test_default_order(self):
        favorites, recent = {"muc-core-01"}, {"ber-edge-01": 10, "ber-test-01": 20}
        order = [d.name for d in search.default_order(self.devices, "", favorites, recent)]
        self.assertEqual(order[0], "muc-core-01")                              # favourites pinned
        order = [d.name for d in search.default_order(self.devices, "is:recent", favorites, recent)]
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
        self.devices, columns, _, _ = inventory.build_devices(headers, rows, cfg)
        self.fields = dict((h.lower(), h) for h in headers)

    def names(self, query, **kw):
        return [d.name.split(".")[0] for d in search.filter_devices(self.devices, query, self.fields, **kw)]

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
        self.assertTrue(search.glob_match("ab-12-s34-l1.example.net", "*-l1"))
        self.assertFalse(search.glob_match("ab-12-s34-l11.example.net", "*-l1"))
        self.assertFalse(search.glob_match("192.0.2.98", "19?"))         # not split on dots
        self.assertTrue(search.glob_match("192.0.2.98", "192.0.2.*"))

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
        status = {"status": {"ping": {"192.0.2.1": results.PING_UP, "192.0.2.2": results.WAIT,
                                      "192.0.2.3": results.PING_DOWN}}}
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
        self.assertEqual(search.fuzzy_match("bc01", "ber-core-01")[1], (0, 4, 9, 10))
        self.assertIsNone(search.fuzzy_match("cb", "ber-core-01"))                 # order matters
        self.assertEqual(search.fuzzy_match("core", "ber-core-01")[1], (4, 5, 6, 7))

    def test_scores(self):
        exact = search.fuzzy_match("core", "ber-core-01")[0]
        split = search.fuzzy_match("bc01", "ber-core-01")[0]                       # b|c|01, all at starts
        at_start = search.fuzzy_match("cor", "ber-core-01")[0]                     # 'core' begins here
        mid_word = search.fuzzy_match("ore", "ber-core-01")[0]                     # sits inside 'core'
        self.assertGreater(exact, split)                                       # written together wins
        self.assertGreater(at_start, mid_word)                                 # segment starts score higher

    def test_a_word_may_only_be_split_at_the_separators(self):
        """The rule the whole search rests on: inside a segment the letters must be
        written together; only a separator allows the search to jump ahead."""
        self.assertIsNotNone(search.fuzzy_match("w4", "xx-xx-sxx-w4"))             # together in a segment
        self.assertIsNone(search.fuzzy_match("w4", "wx-x4-sxx-xx"))                # 4 buried inside 'x4'
        self.assertIsNone(search.fuzzy_match("cr01", "ber-core-01"))               # 'o' skipped inside 'core'
        self.assertIsNone(search.fuzzy_match("a4", "ab-12-s34-w4"))                # 4 buried inside 'w4'
        for pattern in ("bc01", "ab12", "s34", "12s", "ab-s34", "x4"):
            self.assertIsNotNone(search.fuzzy_match(pattern, {"bc01": "ber-core-01",
                                                          "x4": "wx-x4-sxx-xx"}.get(pattern, "ab-12-s34-w4")),
                                 "%r should still be found" % pattern)

    def test_segments_of(self):
        self.assertEqual(inventory.segments_of("ab-12-s34"), [(0, "ab"), (3, "12"), (6, "s34")])
        self.assertEqual(inventory.segments_of("a..b"), [(0, "a"), (3, "b")])         # empty parts dropped
        self.assertEqual(inventory.segments_of(""), [])
        self.assertEqual(inventory.segments_of("plain"), [(0, "plain")])


if __name__ == "__main__":
    unittest.main()


class TestRenamedColumns(unittest.TestCase):
    """D49: a column renamed in `columns` (cursed CSV header -> LOCATION) is searched
    by its new name, by the start of it, and its values like a plain word."""

    HEADERS = ["Name", "IP", "Standort Bezeichnung (lang)", "local_contact"]
    COLUMNS = [("Name", "Name"), ("IP", "IP"), ("Standort Bezeichnung (lang)", "LOCATION")]

    def setUp(self):
        cfg = types.SimpleNamespace(columns=self.COLUMNS)
        rows = [{"Name": "ber-core-01", "IP": "192.0.2.1", "Standort Bezeichnung (lang)": "Berlin Mitte DC",
                 "local_contact": "anna"},
                {"Name": "ab-12-s34-w4", "IP": "192.0.2.2", "Standort Bezeichnung (lang)": "ZH-Altstetten",
                 "local_contact": "bob"}]
        self.ds = inventory.build_devices(self.HEADERS, rows, cfg)[0]
        self.fields = search.Fields(self.HEADERS, self.COLUMNS)

    def names(self, query):
        return [d.name for d in search.filter_devices(self.ds, query, self.fields)]

    def test_the_label_and_the_start_of_it(self):
        for query in ("LOCATION:berlin", "location:berlin", "loc:berlin", "lo:berlin"):
            self.assertEqual(self.names(query), ["ber-core-01"], query)

    def test_your_label_wins_over_a_header_with_the_same_start(self):
        self.assertEqual(self.search_header("loc"), "Standort Bezeichnung (lang)")
        self.assertEqual(self.names("local_contact:bob"), ["ab-12-s34-w4"])      # still reachable by its name
        self.assertEqual(self.names("localc:bob"), ["ab-12-s34-w4"])
        self.assertEqual(self.names("standort_bez:zh"), ["ab-12-s34-w4"])         # header, spaces as _

    def search_header(self, name):
        return search.field_header(name, self.fields)

    def test_a_start_that_fits_two_columns_means_neither(self):
        fields = search.Fields(["site_a", "site_b"], [])
        self.assertIsNone(search.field_header("site", fields))
        self.assertIsNone(search.field_header("s", self.fields))                  # one letter: never

    def test_values_match_like_a_plain_word(self):
        self.assertEqual(self.names("location:zhalt"), ["ab-12-s34-w4"])
        self.assertEqual(self.names("name:bc01"), ["ber-core-01"])
        self.assertEqual(self.names("location:mitte"), ["ber-core-01"])           # contained, as before

    def test_exact_and_excluded_values_stay_exact(self):
        self.assertEqual(self.names("'location:zhalt"), [])
        self.assertEqual(self.names("-location:zhalt"), ["ber-core-01", "ab-12-s34-w4"])
        self.assertEqual(self.names("-location:zh-alt"), ["ber-core-01"])

    def test_a_space_where_the_colon_belongs_gets_a_hint(self):
        self.assertEqual(self.names("LOCATION berlin"), [])
        self.assertEqual(search.field_hint("LOCATION berlin", self.fields), "LOCATION:berlin")
        self.assertIsNone(search.field_hint("ber core", self.fields))
        self.assertIsNone(search.field_hint("ping down", self.fields))           # a state, not a column
