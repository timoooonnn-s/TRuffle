"""Batch ping: rate limit, results, cancel."""
import time
import types
import unittest

from test_tree_li import tl


class BatchPingTest(unittest.TestCase):
    def setUp(self):
        self._ping_once = tl.ping_once
        self.started = []

        def fake_ping(host, timeout):           # no real ICMP needed in tests
            self.started.append(time.time())
            return host.endswith(".1"), 1.5 if host.endswith(".1") else None
        tl.ping_once = fake_ping

    def tearDown(self):
        tl.ping_once = self._ping_once

    def wait(self, batch):
        for _ in range(200):
            if not batch.running:
                return
            time.sleep(0.05)

    def test_results_and_rate_limit(self):
        cfg = types.SimpleNamespace(ping_rate=10, ping_timeout=1)
        hosts = ["10.0.0.%d" % i for i in range(1, 11)]
        ping, rtt, checked = {}, {}, {}
        batch = tl.BatchPing(hosts, cfg, {"ping": ping, "rtt": rtt}, checked)
        self.wait(batch)
        self.assertEqual(ping["10.0.0.1"], tl.PING_UP)
        self.assertEqual(ping["10.0.0.2"], tl.PING_DOWN)
        self.assertEqual(batch.percent, 100)
        self.assertEqual(batch.summary(), "1 up, 9 down, 1.50-1.50 ms")
        self.assertEqual(rtt, {"10.0.0.1": 1.5})             # only hosts that answered
        self.assertNotIn("10.0.0.2", rtt)
        self.assertIn(("ping", "10.0.0.5"), checked)
        span = max(self.started) - min(self.started)
        self.assertGreaterEqual(span, 0.8)                  # 10 pings at 10/s: spread over ~0.9 s

    def test_cancel_restores_earlier_results(self):
        cfg = types.SimpleNamespace(ping_rate=2, ping_timeout=1)
        hosts = ["10.0.0.%d" % i for i in range(2, 8)]
        ping = dict((h, tl.PING_UP) for h in hosts)
        batch = tl.BatchPing(hosts, cfg, {"ping": ping, "rtt": {}}, {})
        time.sleep(0.1)
        batch.cancel()
        self.wait(batch)
        self.assertNotIn(tl.WAIT, ping.values())             # nothing left hanging in "wait"
        self.assertEqual(ping["10.0.0.7"], tl.PING_UP)       # not reached: earlier result kept


if __name__ == "__main__":
    unittest.main()
