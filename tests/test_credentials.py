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


if __name__ == "__main__":
    unittest.main()
