"""ping: the verdict of one ping, the live stream, and pinging the marked switches."""
import sys
import time
import unittest

import support  # noqa: F401  (puts src/ on the path)
from truffle import ping
from truffle.results import PING_DOWN, PING_UP, WAIT, Results

NO_REPLY = ping.NO_REPLY_EXIT


class TestPingVerdict(unittest.TestCase):
    """Field bug: pressing ESC while a ping was running recorded the switch as DOWN even
    though its replies were on the screen - a killed ping exits non-zero.  And a router
    answering "Destination Net Unreachable" prints a "76 bytes from ..." line and on macOS
    exits 0, so neither the text nor the exit code proves a reply.  Only "time=" does."""

    def test_a_cancelled_ping_that_already_had_replies_is_up(self):
        self.assertEqual(ping.ping_verdict(True, -15, killed=True), PING_UP)
        self.assertEqual(ping.ping_verdict(True, None, killed=True), PING_UP)

    def test_a_cancelled_ping_with_no_reply_yet_records_nothing(self):
        """It proves nothing, so whatever was known before must survive."""
        self.assertIsNone(ping.ping_verdict(False, None, killed=True))
        self.assertIsNone(ping.ping_verdict(False, NO_REPLY, killed=True))

    def test_only_a_ping_that_ran_and_heard_nothing_says_down(self):
        self.assertEqual(ping.ping_verdict(False, NO_REPLY), PING_DOWN)
        self.assertIsNone(ping.ping_verdict(False, None))           # still running

    def test_a_ping_that_could_not_run_says_nothing_about_the_switch(self):
        """D44: ping's own errors ("Operation not permitted", not installed, its own
        time-out) used to mark every marked switch as DOWN."""
        self.assertIsNone(ping.ping_verdict(False, 127))             # could not start
        self.assertIsNone(ping.ping_verdict(False, 68 if sys.platform == "darwin" else 2))   # ping error

    def test_an_icmp_error_is_not_a_reply(self):
        """This is the text a router sends back; it must not read as a round-trip time -
        but it does mean the switch cannot be reached (macOS ping exits 0 for it)."""
        unreachable = ("PING 192.0.2.77 (192.0.2.77): 56 data bytes\n"
                       "76 bytes from 198.51.100.1: Destination Net Unreachable\n"
                       "Request timeout for icmp_seq 0\n")
        self.assertFalse(ping.ping_replied(unreachable))
        self.assertEqual(ping.ping_verdict(ping.ping_replied(unreachable), 0), PING_DOWN)

    def test_only_a_time_field_counts_as_a_reply(self):
        self.assertTrue(ping.ping_replied("64 bytes from 10.0.0.1: icmp_seq=1 ttl=63 time=1.23 ms"))
        self.assertTrue(ping.ping_replied("... time<1 ms"))        # some pings report "<"
        self.assertTrue(ping.ping_replied("... time=0.0 ms"))      # a 0 ms reply is still a reply
        self.assertFalse(ping.ping_replied("Request timeout for icmp_seq 0"))
        self.assertFalse(ping.ping_replied(""))
        self.assertFalse(ping.ping_replied(None))

    def test_a_stream_that_cannot_start_has_no_verdict(self):
        s = ping.ProcStream(["/nonexistent/ping"])
        self.assertTrue(s.done)
        self.assertEqual(s.returncode, 127)
        self.assertFalse(s.killed)
        self.assertIsNone(ping.stream_verdict(s))


class TestProcStream(unittest.TestCase):
    def test_stream_collects_output(self):
        s = ping.ProcStream([sys.executable, "-c", "print('hello'); print('world')"])
        for _ in range(100):
            if s.done:
                break
            time.sleep(0.05)
        self.assertTrue(s.done)
        self.assertEqual(s.returncode, 0)
        self.assertIn("hello", s.snapshot())
        self.assertIn("world", s.snapshot())


class TestBatchPing(unittest.TestCase):
    """Pinging the marked switches: results, concurrency, cancel."""

    def setUp(self):
        self._ping_once = ping.ping_once
        self.started = []
        self.delay = 0.0

        def fake_ping(host, timeout):           # no real ICMP needed in tests
            self.started.append(time.time())
            if self.delay:
                time.sleep(self.delay)
            if host.endswith(".9"):
                return None                     # ping itself failed
            return PING_UP if host.endswith(".1") else PING_DOWN
        ping.ping_once = fake_ping

    def tearDown(self):
        ping.ping_once = self._ping_once

    def wait(self, batch):
        for _ in range(200):
            if not batch.running:
                return
            time.sleep(0.05)

    def test_results_and_concurrency(self):
        hosts = ["10.0.0.%d" % i for i in range(1, 11)]
        results = Results()
        batch = ping.BatchPing(hosts, 1, results)
        self.wait(batch)
        self.assertEqual(results.get("ping", "10.0.0.1"), PING_UP)
        self.assertEqual(results.get("ping", "10.0.0.2"), PING_DOWN)
        self.assertEqual(batch.percent, 100)
        self.assertTrue(batch.summary().startswith("1 up, 8 down, 1 could not be pinged"), batch.summary())
        self.assertIsNotNone(results.taken("ping", "10.0.0.5"))
        # all at once now: the rate limiter went with the fleet-wide sweep (D35)
        self.assertLess(max(self.started) - min(self.started), 1.0)

    def test_a_ping_that_failed_keeps_the_earlier_result(self):
        """D44: no verdict must not become "down"."""
        results = Results()
        results.set("ping", "10.0.0.9", PING_UP, 100.0)
        self.wait(ping.BatchPing(["10.0.0.9"], 1, results))
        self.assertEqual(results.get("ping", "10.0.0.9"), PING_UP)
        self.assertEqual(results.taken("ping", "10.0.0.9"), 100.0)

    def test_cancel_restores_earlier_results(self):
        """A ping already in flight must not overwrite what was known before."""
        self.delay = 0.6                                     # still pinging when we cancel
        hosts = ["10.0.0.%d" % i for i in range(2, 8)]
        results = Results()
        for h in hosts:
            results.set("ping", h, PING_UP, 100.0)
        batch = ping.BatchPing(hosts, 1, results)
        time.sleep(0.1)
        batch.cancel()
        self.wait(batch)
        self.assertNotIn(WAIT, results.states["ping"].values())   # nothing left hanging in "wait"
        self.assertEqual(results.get("ping", "10.0.0.7"), PING_UP)  # earlier result kept


if __name__ == "__main__":
    unittest.main()
