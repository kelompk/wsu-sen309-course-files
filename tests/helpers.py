"""Shared helpers for the WSU-SEN 309 tests: fresh databases, fixture captures and ingest runs.

(c) 2026 Wellspring University, Faculty of Computing. For registered WSU-SEN 309 students.
"""
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from new_db import new_db  # noqa: E402

PY = sys.executable


def temp_dir():
    return tempfile.mkdtemp(prefix="sen309_")


def fresh_db(folder):
    return new_db(os.path.join(folder, "test.db"))


def capture(folder, name="run.txt", count=60, faults="", **kw):
    """Run the fixture in file mode and return the path of the capture file."""
    path = os.path.join(folder, name)
    cmd = [PY, os.path.join(ROOT, "fixture", "device_sim.py"), "--count", str(count), "--out", path]
    if faults:
        cmd += ["--faults", faults]
    for k, v in kw.items():
        cmd += ["--" + k.replace("_", "-"), str(v)]
    subprocess.run(cmd, check=True, capture_output=True)
    return path


def ingest(db, source, *extra):
    """Run the ingest program as a separate process (so a simulated crash cannot kill the test).
    Returns (exit code, printed output)."""
    p = subprocess.run([PY, "-m", "host.ingest", "--db", db, "--source", source, *map(str, extra)],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    return p.returncode, p.stdout + p.stderr


def reconcile(db):
    p = subprocess.run([PY, "-m", "host.reconcile", "--db", db], cwd=ROOT, capture_output=True, text=True, timeout=60)
    return p.returncode, p.stdout


def query(db, sql, *args):
    con = sqlite3.connect(db)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def one(db, sql, *args):
    return query(db, sql, *args)[0][0]


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_fixture(port, *extra):
    """Start the fixture as a TCP 'serial port' and wait until it says it is listening.
    (Do not test the port by connecting: the device would send its first lines to that connection.)"""
    p = subprocess.Popen([PY, "-u", os.path.join(ROOT, "fixture", "device_sim.py"), "--tcp", str(port), *map(str, extra)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    p.stderr.readline()          # "fixture: device ... listening on ..."
    return p
