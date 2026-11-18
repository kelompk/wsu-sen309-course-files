#!/usr/bin/env python3
"""Create a fresh database from db/schema.sql and db/seed.sql (deletes the old one first).

    python tools/new_db.py                  makes data/sen309.db
    python tools/new_db.py data/test.db

(c) 2026 Wellspring University, Faculty of Computing. For registered WSU-SEN 309 students.
"""
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def new_db(path, schema=None, seed=None):
    if os.path.exists(path):
        os.remove(path)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(open(schema or os.path.join(ROOT, "db", "schema.sql"), encoding="utf-8").read())
    con.executescript(open(seed or os.path.join(ROOT, "db", "seed.sql"), encoding="utf-8").read())
    con.commit()
    con.close()
    return path


if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "data", "sen309.db")
    new_db(p)
    print(f"created {p} from db/schema.sql and db/seed.sql")
