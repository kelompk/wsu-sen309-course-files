#!/usr/bin/env python3
"""Reconcile what the devices sent with what the database holds (STARTER: Practical 3, Part B).

    python -m host.reconcile --db data/sen309.db
    python -m host.reconcile --db data/sen309.db --device SN01

For every boot session it reports the readings stored, the gaps in the sequence numbers, and
whether the stored rows agree with the device's own end-of-run summary (the E line). It also
lists rejected lines by reason and any ingest run that never finished.
Exit code 0 when every session is RECONCILED, 1 otherwise.

(c) 2026 Wellspring University, Faculty of Computing. For registered WSU-SEN 309 students.
"""
import argparse
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# TODO B1: write a query that returns one row (gap_from, gap_to) for every run of missing seq
#   numbers INSIDE one session (the ? is the session_id). Hint: the window function
#   LAG(seq) OVER (ORDER BY seq) gives the previous stored seq; a gap is where seq - prev > 1.
GAPS_SQL = """
SELECT NULL AS gap_from, NULL AS gap_to WHERE 0 AND ? IS NOT NULL
"""


def gaps(con, sid, reported_last):
    """List of (from, to) ranges of missing seq numbers, including any at the start or the end."""
    out = [tuple(r) for r in con.execute(GAPS_SQL, (sid,))]
    lo, hi = con.execute("SELECT MIN(seq), MAX(seq) FROM reading WHERE session_id = ?", (sid,)).fetchone()
    if lo is None:
        return [(0, reported_last)] if reported_last is not None and reported_last >= 0 else []
    if lo > 0:
        out.insert(0, (0, lo - 1))
    if reported_last is not None and reported_last > hi:
        out.append((hi + 1, reported_last))
    return out


def fmt(ranges):
    return ", ".join(str(a) if a == b else f"{a}-{b}" for a, b in ranges) or "none"


def reconcile(con, device=None, out=print):
    q = "SELECT session_id, device_id, boot, reported_count, reported_last_seq FROM boot_session"
    rows = con.execute(q + (" WHERE device_id = ?" if device else "") + " ORDER BY device_id, boot",
                       (device,) if device else ()).fetchall()
    all_ok = True
    results = []
    for sid, dev, boot, rep_count, rep_last in rows:
        stored, first, last = con.execute("SELECT COUNT(*), MIN(seq), MAX(seq) FROM reading WHERE session_id = ?", (sid,)).fetchone()
        g = gaps(con, sid, rep_last)
        missing = sum(b - a + 1 for a, b in g)
        if rep_count is None:
            verdict = "OPEN"                      # no E line: the device never confirmed its count
        elif missing == 0 and stored == rep_count:
            verdict = "RECONCILED"
        else:
            verdict = "MISMATCH"
        all_ok &= verdict == "RECONCILED"
        results.append({"device": dev, "boot": boot, "stored": stored, "first": first, "last": last,
                        "reported_count": rep_count, "reported_last": rep_last, "gaps": g, "missing": missing, "verdict": verdict})
        out(f"{dev} boot {boot}: stored {stored} (seq {first}..{last}); device reported "
            f"{'nothing (no E line)' if rep_count is None else f'{rep_count}, last seq {rep_last}'}; "
            f"missing {missing} [{fmt(g)}] -> {verdict}")
    for reason, n in con.execute("SELECT reason, COUNT(*) FROM rejected_line GROUP BY reason ORDER BY reason"):
        out(f"rejected: {reason} x{n}")
    for run_id, status, src in con.execute("SELECT run_id, status, source FROM ingest_run WHERE status <> 'DONE' ORDER BY run_id"):
        out(f"run {run_id} ({src}) is {status}" + (": it never finished, probably a crash" if status == "RUNNING" else ""))
    return all_ok, results


def main(argv=None):
    ap = argparse.ArgumentParser(description="Reconcile device records with stored rows")
    ap.add_argument("--db", default=os.path.join(ROOT, "data", "sen309.db"))
    ap.add_argument("--device")
    args = ap.parse_args(argv)
    con = sqlite3.connect(args.db)
    ok, _ = reconcile(con, args.device)
    print("ALL SESSIONS RECONCILED" if ok else "NOT RECONCILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
