"""The password lifetime and the logins TRuffle holds."""

import unittest

from support import args
from truffle import config, credentials


class TestPasswordLifetime(unittest.TestCase):
    """The password must not outlive a window left open for days."""

    def test_the_password_expires_a_fixed_time_after_it_was_typed(self):
        """Absolute, not idle: touching the window must not keep a live credential
        alive for days.  10 h = never during a working day, always gone by morning."""
        now = 1_000_000.0
        life = config.PASSWORD_LIFETIME_MINUTES
        self.assertEqual(life, 600)                                   # 10 hours
        self.assertFalse(credentials.creds_expired(now, now - 9 * 3600, life))       # same working day
        self.assertTrue(credentials.creds_expired(now, now - 11 * 3600, life))       # next morning
        self.assertFalse(credentials.creds_expired(now, now, life))
        self.assertFalse(credentials.creds_expired(now, now - 100 * 3600, 0))        # 0 = never

    def test_password_lifetime_is_configurable_and_bounded(self):
        self.assertEqual(config.load_config(args()).password_lifetime, config.PASSWORD_LIFETIME_MINUTES)
        with self.assertRaises(config.ConfigError):
            config.parse_int("1441", "password_lifetime", 0, 1440)

    def test_minutes_are_never_reported_as_a_rounded_lie(self):
        self.assertEqual(credentials.minutes_text(600), "10 h")
        self.assertEqual(credentials.minutes_text(90), "1 h 30 min")       # was reported as "2 h"
        self.assertEqual(credentials.minutes_text(60), "1 h")
        self.assertEqual(credentials.minutes_text(45), "45 min")


class TestTerminalServerAccount(unittest.TestCase):
    """D54: a lab terminal server's own local account, held next to yours."""

    def test_held_and_forgotten_with_the_others(self):
        c = credentials.Credentials(600)
        self.assertFalse(c.held)
        c.set_server("labts", "lab123")
        self.assertTrue(c.held)
        self.assertEqual(c.last_server_user, "labts")
        c.set_own("timmy", "secret")
        c.forget()                                   # Ctrl-G p: everything goes
        self.assertIsNone(c.server)
        self.assertEqual(c.last_server_user, "labts")   # pre-filled next time

    def test_it_expires_like_the_password(self):
        c = credentials.Credentials(60)
        c.set_server("labts", "lab123")
        self.assertEqual(c.expire(c.server.typed_at + 61 * 60), ["terminal server account"])
        self.assertIsNone(c.server)

    def test_a_pane_failure_drops_only_the_account_it_used(self):
        c = credentials.Credentials(600)
        c.set_own("timmy", "secret")
        c.set_server("labts", "wrong")
        self.assertFalse(c.forget_server_if_older(c.server.typed_at - 5))     # typed again since
        self.assertTrue(c.forget_server_if_older(c.server.typed_at + 1))
        self.assertIsNone(c.server)
        self.assertIsNotNone(c.own)                  # your RADIUS password was not the wrong one


if __name__ == "__main__":
    unittest.main()
