#!/usr/bin/env python3
"""Check that this computer is ready for WSU-SEN 309.   Run from the course folder:  python tools/check_setup.py

(c) 2026 Wellspring University, Faculty of Computing. For registered WSU-SEN 309 students.
"""
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ok = True


def report(good, label, detail, optional=False):
    global ok
    if not good and not optional:
        ok = False
    print(f"{'OK     ' if good else ('OPTIONAL' if optional else 'MISSING')}  {label}: {detail}")


v = sys.version_info
report(v >= (3, 10), "Python 3.10 or later", sys.version.split()[0])
sv = tuple(int(x) for x in sqlite3.sqlite_version.split("."))
report(sv >= (3, 25), "SQLite 3.25 or later (inside Python)", sqlite3.sqlite_version)
git = shutil.which("git")
out = subprocess.run([git, "--version"], capture_output=True, text=True).stdout.strip() if git else "not found"
report(bool(git), "Git", out)
try:
    import serial  # noqa: F401
    report(True, "pyserial (only for a real board)", "installed")
except ImportError:
    report(False, "pyserial (only for a real board)", "not installed; python -m pip install pyserial", optional=True)
report(bool(shutil.which("sqlite3")), "sqlite3 command-line program", "found" if shutil.which("sqlite3") else "not found; use python tools/sql.py instead", optional=True)

# the fixture and the parser must agree on this computer
try:
    tmp = tempfile.mkdtemp()
    cap = os.path.join(tmp, "check.txt")
    subprocess.run([sys.executable, os.path.join(ROOT, "fixture", "device_sim.py"), "--count", "5", "--out", cap],
                   check=True, capture_output=True)
    lines = open(cap).read().splitlines()
    report(len(lines) == 7 and lines[0].startswith("H,SN01"), "Serial fixture", f"{len(lines)} lines written, first: {lines[0]}")
except Exception as e:  # noqa: BLE001
    report(False, "Serial fixture", str(e))

print("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED: fix the MISSING lines above")
sys.exit(0 if ok else 1)
