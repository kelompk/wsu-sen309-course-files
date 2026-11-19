"""Practical 4: interruption, malformed input and recovery (STARTER: write the TODO tests).
Run:  python -m unittest tests.test_recovery -v

Each test sets up one failure on purpose, then checks two things:
1. nothing wrong reached the reading table, and nothing was lost without being reported;
2. after the recovery step the database reconciles (or the loss is reported, if it cannot).

(c) 2026 Wellspring University, Faculty of Computing. For registered WSU-SEN 309 students.
"""
import time  # noqa: F401  (you need it in E2)
import unittest

from tests.helpers import (temp_dir, fresh_db, capture, ingest, reconcile, one, query,
                           free_port, start_fixture)


class Interruption(unittest.TestCase):
    def setUp(self):
        self.dir = temp_dir()
        self.db = fresh_db(self.dir)

    # ---------------------------------------------------------------- guided task (Part A)
    def test_cut_transfer_is_flagged_then_recovered(self):
        """G1. The link is cut half-way through reading 37."""
        code, out = ingest(self.db, capture(self.dir, "cut.txt", faults="cut@37"))
        self.assertEqual(code, 1, out)                                         # not a clean run ...
        self.assertEqual(one(self.db, "SELECT status FROM ingest_run"), "INCOMPLETE")
        self.assertEqual(one(self.db, "SELECT COUNT(*) FROM reading"), 37)     # ... but every complete line kept
        self.assertEqual(one(self.db, "SELECT reason FROM rejected_line"), "TRUNCATED")
        self.assertEqual(reconcile(self.db)[0], 1)                             # and reconcile does not pass it
        ingest(self.db, capture(self.dir, "full.txt"))                         # recovery: transfer again
        self.assertEqual(one(self.db, "SELECT COUNT(*) FROM reading"), 60)
        self.assertEqual(one(self.db, "SELECT duplicates FROM ingest_run WHERE run_id = 2"), 37)
        self.assertEqual(reconcile(self.db)[0], 0)

    def test_crash_leaves_only_whole_batches(self):
        """G2. The ingest program dies after line 47 with batches of 20 lines.
        Run ingest(self.db, f, "--batch", 20, "--crash-after", 47) on a clean 60-reading capture.
        Assert: exit code 3; how many readings are stored (work it out first: which lines were
        committed?); the run is still RUNNING. Then ingest the same file again and assert that all
        60 readings are stored, reconcile passes, and its report still shows the crash."""
        f = capture(self.dir, "clean.txt")
        code, out = ingest(self.db, f, "--batch", 20, "--crash-after", 47)
        self.assertEqual(code, 3, out)
        self.assertEqual(one(self.db, "SELECT COUNT(*) FROM reading"), 39)
        self.assertEqual(one(self.db, "SELECT status FROM ingest_run"), "RUNNING")

        code2, out2 = ingest(self.db, f)
        self.assertEqual(code2, 0, out2)
        self.assertEqual(one(self.db, "SELECT COUNT(*) FROM reading"), 60)
        rc, rec_out = reconcile(self.db)
        self.assertEqual(rc, 0, rec_out)
        self.assertIn("is RUNNING", rec_out)

    def test_reboot_starts_a_new_session(self):
        """G3. Use faults="reboot@30". Assert there are two boot sessions with 30 readings each,
        seq 0..29 in both, and that reconcile reports boot 1 as OPEN (why?) and boot 2 as RECONCILED."""
        f = capture(self.dir, "reboot.txt", faults="reboot@30")
        code, out = ingest(self.db, f)
        self.assertEqual(code, 0, out)
        sessions = query(
            self.db,
            "SELECT b.boot, COUNT(r.seq), MIN(r.seq), MAX(r.seq) "
            "FROM boot_session b JOIN reading r ON b.session_id = r.session_id "
            "GROUP BY b.boot ORDER BY b.boot",
        )
        self.assertEqual(sessions, [(1, 30, 0, 29), (2, 30, 0, 29)])
        rc, rec_out = reconcile(self.db)
        self.assertEqual(rc, 1, rec_out)
        self.assertIn("boot 1: stored 30 (seq 0..29); device reported nothing (no E line); missing 0 [none] -> OPEN", rec_out)
        self.assertIn("boot 2: stored 30 (seq 0..29); device reported 30, last seq 29; missing 0 [none] -> RECONCILED", rec_out)

    def test_bad_lines_never_reach_the_reading_table(self):
        """G4. Use faults="corrupt@5,range@6,garbage@7,conflict@20". Assert that seq 5 and 6 are not
        stored, no stored temperature is impossible, and exactly 4 lines were rejected."""
        f = capture(self.dir, "bad.txt", faults="corrupt@5,range@6,garbage@7,conflict@20")
        ingest(self.db, f)
        self.assertEqual(one(self.db, "SELECT COUNT(*) FROM reading WHERE seq IN (5, 6)"), 0)
        self.assertEqual(one(self.db, "SELECT COUNT(*) FROM reading WHERE temp_c < -40.0 OR temp_c > 125.0"), 0)
        self.assertEqual(one(self.db, "SELECT COUNT(*) FROM rejected_line"), 4)

    def test_batch_size_does_not_change_the_result(self):
        """G5. Ingest the same faulty capture into two fresh databases, once with --batch 1 and once
        with --batch 500, and assert the two reading tables are identical."""
        f = capture(self.dir, "faulty.txt", faults="corrupt@12,drop@25,dup@30,garbage@33,range@40,conflict@50")
        db1 = fresh_db(temp_dir())
        db500 = fresh_db(temp_dir())
        ingest(db1, f, "--batch", 1)
        ingest(db500, f, "--batch", 500)
        cols = "SELECT session_id, seq, t_ms, temp_c, light, state FROM reading ORDER BY session_id, seq"
        self.assertEqual(query(db1, cols), query(db500, cols))

    # ---------------------------------------------------------------- extension (Part B)
    def test_live_link_cut_is_recovered_by_replay(self):
        """E1. port = free_port(); fx = start_fixture(port, "--speed", 20, "--faults", "cut@15").
        Ingest from f"tcp://127.0.0.1:{port}" (it ends at the cut), then ingest again with --resume
        and --records 10. Always fx.terminate() in a finally block. Assert reconcile passes."""
        port = free_port()
        fx = start_fixture(port, "--speed", 20, "--faults", "cut@15")
        try:
            src = f"tcp://127.0.0.1:{port}"
            code1, out1 = ingest(self.db, src, "--timeout", 2)
            self.assertEqual(code1, 1, out1)
            code2, out2 = ingest(self.db, src, "--resume", "--records", 10, "--timeout", 2)
            self.assertEqual(code2, 0, out2)
            rc, rec_out = reconcile(self.db)
            self.assertEqual(rc, 0, rec_out)
        finally:
            fx.terminate()
            fx.wait()

    def test_outage_longer_than_the_buffer_is_reported(self):
        """E2. As E1 but cut@10 and wait 3 s (about 60 readings at 20x) before you resume.
        Assert the device said GONE and that reconcile reports a MISMATCH rather than passing."""
        port = free_port()
        fx = start_fixture(port, "--speed", 20, "--faults", "cut@10")
        try:
            src = f"tcp://127.0.0.1:{port}"
            code1, out1 = ingest(self.db, src, "--timeout", 2)
            self.assertEqual(code1, 1, out1)
            time.sleep(3)
            code2, out2 = ingest(self.db, src, "--resume", "--records", 10, "--timeout", 2)
            self.assertIn("GONE", out2)
            rc, rec_out = reconcile(self.db)
            self.assertEqual(rc, 1, rec_out)
            self.assertIn("MISMATCH", rec_out)
        finally:
            fx.terminate()
            fx.wait()


if __name__ == "__main__":
    unittest.main()