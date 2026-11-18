#!/usr/bin/env python3
"""Run SQL files or one SQL statement against a SQLite database (no sqlite3 program needed).

    python tools/sql.py data/sen309.db db/schema.sql db/seed.sql     run files in order
    python tools/sql.py data/sen309.db -c "SELECT * FROM device;"    run a statement and print rows
    python tools/sql.py data/sen309.db                              interactive prompt (end with .quit)

Foreign keys are switched on for every connection.
(c) 2026 Wellspring University, Faculty of Computing. For registered WSU-SEN 309 students.
"""
import os
import sqlite3
import sys


def show(cur):
    if cur.description is None:
        return
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    w = [max([len(c)] + [len(str(r[i])) for r in rows]) for i, c in enumerate(cols)]
    print("  ".join(c.ljust(w[i]) for i, c in enumerate(cols)))
    print("  ".join("-" * x for x in w))
    for r in rows:
        print("  ".join(("NULL" if v is None else str(v)).ljust(w[i]) for i, v in enumerate(r)))
    print(f"({len(rows)} row{'s' if len(rows) != 1 else ''})")


def statements(sql):
    """Split SQL text into complete statements (semicolons inside quotes or triggers are kept)."""
    out, buf = [], ""
    for piece in sql.split(";"):
        buf += piece + ";"
        if sqlite3.complete_statement(buf):
            out.append(buf)
            buf = ""
    rest = buf[:-1]
    return out, rest


def is_blank(stmt):
    return all(not l.strip() or l.strip().startswith("--") for l in stmt.strip().rstrip(";").splitlines())


def run_script(con, sql):
    """Run statements one by one so SELECT results are printed."""
    stmts, rest = statements(sql)
    for stmt in stmts:
        if not is_blank(stmt):
            show(con.execute(stmt))
    if not is_blank(rest):
        raise sqlite3.OperationalError("incomplete statement at the end (missing ';'?)")


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    db = argv[0]
    os.makedirs(os.path.dirname(os.path.abspath(db)), exist_ok=True)
    con = sqlite3.connect(db, isolation_level=None)
    con.execute("PRAGMA foreign_keys = ON")
    try:
        if len(argv) >= 3 and argv[1] == "-c":
            run_script(con, argv[2])
        elif len(argv) > 1:
            for path in argv[1:]:
                with open(path, encoding="utf-8") as f:
                    run_script(con, f.read())
                print(f"ok: {path}")
        else:
            print(f"SQLite {sqlite3.sqlite_version} on {db}. End statements with ';'. Type .quit to leave.")
            buf = ""
            while True:
                try:
                    line = input("sql> " if not buf else "...> ")
                except EOFError:
                    break
                if line.strip() in (".quit", ".exit"):
                    break
                buf += line + "\n"
                if sqlite3.complete_statement(buf):
                    try:
                        run_script(con, buf)
                    except sqlite3.Error as e:
                        print("error:", e)
                    buf = ""
    except sqlite3.Error as e:
        print("error:", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
