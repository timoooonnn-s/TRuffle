"""The per-user files: favourites, history, saved results, auth failures."""

import errno
import os
import subprocess
import sys
import threading
import unittest

from support import SRC, TempDir
from truffle import state
from truffle.results import PING_UP, WAIT, Results


class TestUserState(TempDir):
    def test_recent_persists(self):
        st = state.UserState(os.path.join(self.tmp, "state"))
        st.touch("sw2")
        again = state.UserState(os.path.join(self.tmp, "state"))
        self.assertIn("sw2", again.recent)
        mode = os.stat(os.path.join(self.tmp, "state", "recent")).st_mode & 0o777
        self.assertEqual(mode, 0o600)

    def test_an_old_favorites_file_is_ignored(self):
        """Favourites were cut (D50); a file left from before must not break anything."""
        d = os.path.join(self.tmp, "state")
        os.makedirs(d)
        with open(os.path.join(d, "favorites"), "w") as f:
            f.write("sw1\n")
        st = state.UserState(d)
        self.assertIsNone(st.error)
        self.assertFalse(hasattr(st, "favorites"))

    def test_history_is_trimmed_and_tolerates_garbage(self):
        d = os.path.join(self.tmp, "state")
        os.makedirs(d)
        with open(os.path.join(d, "recent"), "w") as f:
            f.write("garbage\nnot-a-number\tsw9\n100\tsw1\n")
        self.assertEqual(state.UserState(d).recent, {"sw1": 100.0})
        with open(os.path.join(d, "recent"), "w") as f:
            f.write("".join("%d\tx%d\n" % (i, i) for i in range(state.UserState.MAX_RECENT + 20)))
        state.UserState(d).touch("newest")
        self.assertEqual(len(state.UserState(d).recent), state.UserState.MAX_RECENT)
        self.assertIn("newest", state.UserState(d).recent)

    def results(self, *entries):
        r = Results()
        for kind, host, word, when, detail in entries:
            r.set(kind, host, word, when, detail)
        return r

    def test_check_results_are_saved_and_merged(self):
        d = os.path.join(self.tmp, "state")
        first = self.results(("ping", "10.0.0.1", "up", 100, ""), ("ssh", "10.0.0.1", "failed", 100, ""))
        first.states["ping"]["10.0.0.2"] = WAIT
        state.UserState(d).save_results(first)
        state.UserState(d).save_results(self.results(("ping", "10.0.0.1", "down", 50, "")))   # older
        saved = state.UserState(d).load_results()
        self.assertEqual(saved.states["ping"], {"10.0.0.1": "up"})          # "wait" is never saved
        self.assertEqual(saved.states["ssh"], {"10.0.0.1": "failed"})
        self.assertEqual(saved.taken("ping", "10.0.0.1"), 100)

    def test_a_new_result_drops_the_old_reason(self):
        r = self.results(("ssh", "h", "failed", 100, "Connection timed out"))
        r.set("ssh", "h", "ok", 200)
        self.assertEqual(r.why("ssh", "h"), "")
        self.assertEqual(r.detail, {})

    def test_the_detail_field_round_trips_and_stays_backward_compatible(self):
        """The 5th field carries a detail - today the reason a ssh attempt failed.
        Rows without it must keep working - an older TRuffle writes only 4 fields,
        and a row with no detail is still written with 4 so an older one can read it."""
        d = os.path.join(self.tmp, "state")
        state.UserState(d).save_results(self.results(
            ("ping", "10.0.0.1", "up", 100, "1.25"),
            ("ssh", "10.0.0.1", "failed", 100, "Connection timed out (exit 255)")))
        saved = state.UserState(d).load_results()
        self.assertEqual(saved.why("ping", "10.0.0.1"), "1.25")
        self.assertEqual(saved.why("ssh", "10.0.0.1"), "Connection timed out (exit 255)")
        # a result with no detail is written as 4 fields, readable by an older TRuffle
        state.UserState(d).save_results(self.results(("ping", "10.0.0.2", "down", 200, "")))
        with open(os.path.join(d, "status"), encoding="utf-8") as f:
            rows = dict((line.split("\t")[0], line.rstrip("\n").split("\t")) for line in f)
        self.assertEqual(len(rows["10.0.0.2"]), 4)
        self.assertEqual(len(rows["10.0.0.1"]), 5)
        # and a hand-written 4-field file still loads completely
        with open(os.path.join(d, "status"), "w", encoding="utf-8") as f:
            f.write("10.0.0.9\tping\tup\t300\n")
        saved = state.UserState(d).load_results()
        self.assertEqual(saved.states["ping"], {"10.0.0.9": "up"})
        self.assertEqual(saved.detail, {})

    def test_saving_survives_results_the_batch_threads_change(self):
        """BatchPing._restore deletes hosts from the very dict a save walks, from its
        worker threads.  Iterating it live raised "dictionary changed size during
        iteration" and painted a traceback over the curses screen."""
        st = state.UserState(os.path.join(self.tmp, "state"))
        r = Results()
        for i in range(2000):
            r.set("ping", "10.0.%d.%d" % (i // 250, i % 250), PING_UP, 100, "1.0")
        ping = r.states["ping"]
        stop = []
        old = sys.getswitchinterval()

        def churn():                                   # what a cancelled batch ping does
            while not stop:
                for host in list(ping):
                    ping.pop(host, None) if host in ping else ping.setdefault(host, PING_UP)
        sys.setswitchinterval(1e-6)                    # make the thread switch, reliably
        worker = threading.Thread(target=churn, daemon=True)
        worker.start()
        try:
            for _ in range(40):
                st.save_results(r)                     # must not raise
        finally:
            stop.append(True)
            worker.join(timeout=5)
            sys.setswitchinterval(old)

    def test_a_filesystem_without_locks_still_saves(self):
        """D45 review: NFS without a lock manager refuses flock - saving must go on
        unlocked instead of crashing TRuffle."""
        def refuse(fd, op):
            raise OSError(errno.ENOLCK, "No locks available")
        original, state.fcntl.flock = state.fcntl.flock, refuse
        try:
            st = state.UserState(os.path.join(self.tmp, "state"))
            st.touch("sw1")
            self.assertIn("sw1", st.recent)
            r = Results()
            r.set("ssh", "10.0.0.1", "ok", 100)
            st.save_results(r)
        finally:
            state.fcntl.flock = original
        self.assertEqual(state.UserState(os.path.join(self.tmp, "state")).load_results().get("ssh", "10.0.0.1"), "ok")

    def test_writers_in_parallel_lose_nothing(self):
        """D44: TRuffle windows and tmux panes all merge into one status file.  Without
        a lock, two that read before either wrote dropped one side's results."""
        d = os.path.join(self.tmp, "state")
        code = ("import sys; sys.path.insert(0, %r)\n"
                "from truffle.state import UserState\nfrom truffle.results import Results\n"
                "st = UserState(%r)\n"
                "for i in range(15):\n"
                "    r = Results(); r.set('ssh', 'h%%s-%%d' %% (sys.argv[1], i), 'ok', 100 + i)\n"
                "    st.save_results(r)\n" % (SRC, d))
        writers = [subprocess.Popen([sys.executable, "-c", code, str(n)]) for n in range(8)]
        for w in writers:
            self.assertEqual(w.wait(timeout=60), 0)
        self.assertEqual(len(state.UserState(d).load_results().states["ssh"]), 8 * 15)

    def test_a_pane_login_failure_is_reported_and_read_back(self):
        """The handover socket is closed before a pane ever logs in, so a wrong password
        comes back through this file - TRuffle then drops the password it holds."""
        d = os.path.join(self.tmp, "state")
        st = state.UserState(d)
        self.assertEqual(state.UserState(d).load_auth_failure(), (0.0, ""))
        st.note_auth_failure("10.0.0.7")
        stamp, host = state.UserState(d).load_auth_failure()
        self.assertEqual(host, "10.0.0.7")
        self.assertGreater(stamp, 0)
        self.assertEqual(os.stat(os.path.join(d, "authfail")).st_mode & 0o777, 0o600)

    def test_unwritable_directory_reports_error(self):
        blocker = os.path.join(self.tmp, "file")
        open(blocker, "w").close()
        st = state.UserState(os.path.join(blocker, "state"))     # a file is in the way
        st.touch("sw1")
        self.assertIsNotNone(st.error)
        self.assertIn("sw1", st.recent)                       # still works in memory


if __name__ == "__main__":
    unittest.main()
