"""The small checks the security of the rest depends on: hosts, users, prompts, argv."""

import unittest

from support import args
from truffle import config, inventory, session


class TestSecurityHelpers(unittest.TestCase):
    def test_valid_host(self):
        for ok in ("10.0.0.1", "sw1.example.com", "fe80::1%eth0", "SW_01"):
            self.assertTrue(inventory.valid_host(ok), ok)
        for bad in ("", "-oProxyCommand=sh", "a b", "x;rm -rf /", "$(id)", "a\nb"):
            self.assertFalse(inventory.valid_host(bad), bad)

    def test_valid_user(self):
        self.assertTrue(config.valid_user("timmy.r"))
        for bad in ("", "-l", "a b", "a@b"):
            self.assertFalse(config.valid_user(bad), bad)

    def test_password_prompt_detection(self):
        for p in ("Password:", "admin@10.0.0.1's password: ", "Enter Password : ", "PASSWORD:"):
            self.assertTrue(session.is_password_prompt(p), p)
        for p in ("Enter passphrase for key '/home/u/.ssh/id_rsa': ", "Verification code:",
                  "password policy updated", "login:"):
            self.assertFalse(session.is_password_prompt(p), p)

    def test_ssh_argv(self):
        cfg = config.load_config(args())
        cfg.ssh_options = ["-o", "StrictHostKeyChecking=yes"]
        argv = session.build_ssh_argv(cfg, "timmy", "10.0.0.1", inject_password=True)
        self.assertEqual(argv[:3], ["ssh", "-o", "StrictHostKeyChecking=yes"])   # user options first
        self.assertIn("NumberOfPasswordPrompts=1", argv)
        self.assertEqual(argv[-4:], ["-l", "timmy", "--", "10.0.0.1"])
        self.assertNotIn("NumberOfPasswordPrompts=1", session.build_ssh_argv(cfg, "t", "h", inject_password=False))


if __name__ == "__main__":
    unittest.main()
