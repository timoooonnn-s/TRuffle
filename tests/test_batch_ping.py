"""Pinging the marked switches: results, concurrency, cancel."""
import time
import types
import unittest

from test_truffle import tl


class BatchPingTest(unittest.TestCase):
    def setUp(self):
        self._ping_once = tl.ping_once
        self.started = []
        self.delay = 0.0

        def fake_ping(host, timeout):           # no real ICMP needed in tests
            self.started.append(time.time())
            if self.delay:
                time.sleep(self.delay)
            return host.endswith(".1")          # True = a reply came back
        tl.ping_once = fake_ping

    def tearDown(self):
        tl.ping_once = self._ping_once

    def wait(self, batch):
        for _ in range(200):
            if not batch.running:
                return
            time.sleep(0.05)

    def test_results_and_concurrency(self):
        cfg = types.SimpleNamespace(ping_timeout=1)
        hosts = ["10.0.0.%d" % i for i in range(1, 11)]
        ping, checked = {}, {}
        batch = tl.BatchPing(hosts, cfg, {"ping": ping}, checked)
        self.wait(batch)
        self.assertEqual(ping["10.0.0.1"], tl.PING_UP)
        self.assertEqual(ping["10.0.0.2"], tl.PING_DOWN)
        self.assertEqual(batch.percent, 100)
        self.assertEqual(batch.summary(), "1 up, 9 down")
        self.assertIn(("ping", "10.0.0.5"), checked)
        # all at once now: the rate limiter went with the fleet-wide sweep (D35)
        self.assertLess(max(self.started) - min(self.started), 1.0)

    def test_cancel_restores_earlier_results(self):
        """A ping already in flight must not overwrite what was known before."""
        cfg = types.SimpleNamespace(ping_timeout=1)
        self.delay = 0.6                                     # still pinging when we cancel
        hosts = ["10.0.0.%d" % i for i in range(2, 8)]
        ping = dict((h, tl.PING_UP) for h in hosts)
        batch = tl.BatchPing(hosts, cfg, {"ping": ping}, {})
        time.sleep(0.1)
        batch.cancel()
        self.wait(batch)
        self.assertNotIn(tl.WAIT, ping.values())             # nothing left hanging in "wait"
        self.assertEqual(ping["10.0.0.7"], tl.PING_UP)       # earlier result kept


if __name__ == "__main__":
    unittest.main()
