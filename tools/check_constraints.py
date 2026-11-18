#!/usr/bin/env python3
"""Run db/constraint_tests.sql against a schema and show what the database accepted or rejected.

    python tools/check_constraints.py db/schema.sql
    python tools/check_constraints.py db/schema.sql --expect     also compare with the [expect: ...] tags

(c) 2026 Wellspring University, Faculty of Computing. For registered WSU-SEN 309 students.
"""
import os
import re
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_tests(path):
    setup, tests, cur = [], [], None
    for line in open(path, encoding="utf-8"):
        m = re.match(r"--\s*(T\d+)\s+(.*?)\s*(?:\[expect:\s*(\w+)\])?\s*$", line)
        if m:
            cur = {"id": m.group(1), "what": m.group(2), "expect": m.group(3), "sql": ""}
            tests.append(cur)
        elif line.startswith("-- SETUP"):
            cur = None
        elif line.startswith("--") or not line.strip():
            continue
        elif cur is None:
            setup.append(line)
        else:
            cur["sql"] += line
    return "".join(setup), tests


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    schema = argv[0]
    use_expect = "--expect" in argv
    con = sqlite3.connect(":memory:", isolation_level=None)
    con.execute("PRAGMA foreign_keys = ON")
    try:
        con.executescript(open(schema, encoding="utf-8").read())
        con.executescript(open(os.path.join(ROOT, "db", "seed.sql"), encoding="utf-8").read())
    except sqlite3.Error as e:
        print(f"Your schema or the seed data did not load: {e}")
        return 1
    setup, tests = load_tests(os.path.join(ROOT, "db", "constraint_tests.sql"))
    try:
        con.executescript(setup)
    except sqlite3.Error as e:
        print(f"The SETUP block failed, so the schema is not yet usable: {e}")
        return 1
    bad = 0
    print(f"{'Test':<5} {'Outcome':<9} What was tried  (SQLite's message underneath)")
    for t in tests:
        con.execute("SAVEPOINT t")
        try:
            con.execute(t["sql"])
            outcome, msg = "ACCEPTED", ""
        except sqlite3.Error as e:
            outcome, msg = "REJECTED", str(e)
        con.execute("ROLLBACK TO t")
        con.execute("RELEASE t")
        mark = ""
        if use_expect and t["expect"]:
            ok = outcome == t["expect"]
            bad += not ok
            mark = "" if ok else f"   <-- expected {t['expect']}"
        print(f"{t['id']:<5} {outcome:<9} {t['what']}{mark}")
        if msg:
            print(f"{'':<15} {msg[:70]}")
    if use_expect:
        print(f"\n{len(tests) - bad} of {len(tests)} tests behave as the reference schema does.")
        return 1 if bad else 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
