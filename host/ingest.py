#!/usr/bin/env python3
"""Ingest device records into SQLite (STARTER: Practical 3, Part A, complete store_reading).

    python -m host.ingest --db data/sen309.db --source data/run_clean.txt
    python -m host.ingest --db data/sen309.db --source tcp://127.0.0.1:7000 --records 30
    python -m host.ingest --db data/sen309.db --source tcp://127.0.0.1:7000 --resume
    python -m host.ingest --db data/sen309.db --source serial://COM3        (a real board; needs pyserial)

Rules (the interface contract, workbook Appendix):
  * Every line is either stored, counted as a duplicate, or written to rejected_line with a reason.
  * A reading is identified by (device, boot, seq). Storing the same reading twice changes nothing,
    so a transfer can always be repeated safely (the ingest is idempotent).
  * The same key with different values is a CONFLICT: the first stored copy is kept.
  * Work is committed in batches. A crash loses at most the current batch, never half of one,
    and the run stays marked RUNNING so the crash can be seen afterwards.

(c) 2026 Wellspring University, Faculty of Computing. For registered WSU-SEN 309 students.
"""
import argparse
import os
import socket
import sqlite3
import sys
import time

from host.records import Hello, Reading, EndOfRun, DeviceError, ParseError, parse_line

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------- sources
class Source:
    """Yields (line_no, text, complete). complete is False for a last line with no line ending."""

    def __init__(self, spec, timeout=5.0):
        self.spec, self.timeout, self.sock, self.ser, self.f = spec, timeout, None, None, None
        if spec.startswith("tcp://"):
            host, _, port = spec[6:].partition(":")
            self.sock = socket.create_connection((host, int(port)), timeout=timeout)
        elif spec.startswith("serial://"):
            try:
                import serial  # pyserial
            except ImportError:
                raise SystemExit("serial:// needs pyserial: python -m pip install pyserial")
            self.ser = serial.serial_for_url(spec[9:], baudrate=115200, timeout=timeout)
        elif spec == "-":
            self.f = sys.stdin
        else:
            self.f = open(spec, encoding="ascii", errors="replace", newline="")

    def send(self, command):
        data = (command + "\n").encode()
        if self.sock:
            self.sock.sendall(data)
        elif self.ser:
            self.ser.write(data)

    @property
    def interactive(self):
        return self.sock is not None or self.ser is not None

    def lines(self):
        n = 0
        if self.f:
            for raw in self.f:
                n += 1
                yield n, raw, raw.endswith("\n")
            return
        buf = b""
        while True:
            try:
                data = self.sock.recv(4096) if self.sock else self.ser.read(256)
            except socket.timeout:
                data = None
            if not data:                    # link closed or silent for `timeout` seconds
                if buf:
                    n += 1
                    yield n, buf.decode("ascii", "replace"), False
                return
            buf += data
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                n += 1
                yield n, raw.decode("ascii", "replace") + "\n", True

    def close(self):
        for x in (self.sock, self.ser):
            if x:
                x.close()
        if self.f and self.f is not sys.stdin:
            self.f.close()


# ---------------------------------------------------------------- database
def connect(path):
    con = sqlite3.connect(path, isolation_level=None)     # we issue BEGIN and COMMIT ourselves
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA busy_timeout = 3000")
    return con


def session_for(con, device, boot, hello=None):
    """Return the session_id for (device, boot), creating the session if needed.
    Raises ParseError('UNKNOWN_DEVICE') if the device is not registered."""
    if con.execute("SELECT 1 FROM device WHERE device_id = ?", (device,)).fetchone() is None:
        raise ParseError("UNKNOWN_DEVICE", f"{device} is not in the device table")
    con.execute("INSERT INTO boot_session (device_id, boot) VALUES (?, ?) ON CONFLICT (device_id, boot) DO NOTHING",
                (device, boot))
    if hello is not None:
        con.execute("UPDATE boot_session SET fw = ?, period_ms = ? WHERE device_id = ? AND boot = ?",
                    (hello.fw, hello.period_ms, device, boot))
    return con.execute("SELECT session_id FROM boot_session WHERE device_id = ? AND boot = ?", (device, boot)).fetchone()[0]


def store_reading(con, run_id, r):
    """Store one reading. Returns 'inserted' or 'duplicate'; raises ParseError('CONFLICT') if the
    same reading is already stored with different values."""
    sid = session_for(con, r.device, r.boot)
    # TODO A4: insert the reading with run_id, using ? placeholders (never build SQL with f-strings).
    #   Add  ON CONFLICT (session_id, seq) DO NOTHING  so a second copy is not an error.
    #   If cur.rowcount == 1 the row is new: return "inserted".
    #   Otherwise read the stored row's (t_ms, temp_c, light, state). If it equals the new one,
    #   return "duplicate"; if not, raise ParseError("CONFLICT", "...") and keep the first copy.
    raise NotImplementedError("TODO A4: store_reading")


def next_seq(con, device, boot):
    row = con.execute("SELECT MAX(r.seq) FROM reading r JOIN boot_session s USING (session_id) "
                      "WHERE s.device_id = ? AND s.boot = ?", (device, boot)).fetchone()
    return 0 if row[0] is None else row[0] + 1


# ---------------------------------------------------------------- the ingest loop
class Ingest:
    def __init__(self, con, source_name, batch=20, crash_after=None, log=print):
        self.con, self.batch, self.crash_after, self.log = con, batch, crash_after, log
        self.counts = {"lines_read": 0, "inserted": 0, "duplicates": 0, "rejected": 0}
        self.in_batch = 0
        self.ended = False                 # an E line was received
        self.cut = False                   # the last line was incomplete
        self.last_hello = None
        cur = con.execute("INSERT INTO ingest_run (source) VALUES (?)", (source_name,))
        self.run_id = cur.lastrowid
        con.execute("BEGIN")

    def reject(self, line_no, raw, reason, detail):
        self.con.execute("INSERT INTO rejected_line (run_id, line_no, raw, reason, detail) VALUES (?, ?, ?, ?, ?)",
                         (self.run_id, line_no, raw.rstrip("\r\n")[:200], reason, detail))
        self.counts["rejected"] += 1

    def commit(self):
        c = self.counts
        self.con.execute("UPDATE ingest_run SET lines_read = ?, inserted = ?, duplicates = ?, rejected = ? WHERE run_id = ?",
                         (c["lines_read"], c["inserted"], c["duplicates"], c["rejected"], self.run_id))
        self.con.execute("COMMIT")
        self.in_batch = 0

    def handle(self, line_no, raw, complete):
        self.counts["lines_read"] += 1
        try:
            if not complete:
                raise ParseError("TRUNCATED", "last line has no line ending: the transfer was cut")
            rec = parse_line(raw)
            if isinstance(rec, Reading):
                self.counts["duplicates" if store_reading(self.con, self.run_id, rec) == "duplicate" else "inserted"] += 1
            elif isinstance(rec, Hello):
                session_for(self.con, rec.device, rec.boot, hello=rec)
                self.last_hello = rec
            elif isinstance(rec, EndOfRun):
                sid = session_for(self.con, rec.device, rec.boot)
                self.con.execute("UPDATE boot_session SET reported_count = ?, reported_last_seq = ? WHERE session_id = ?",
                                 (rec.count, rec.last_seq, sid))
                self.ended = True
            elif isinstance(rec, DeviceError):
                self.log(f"  device reports {rec.code} {rec.detail}")
        except ParseError as e:
            self.reject(line_no, raw, e.reason, e.detail)
        except sqlite3.IntegrityError as e:          # the schema caught something the parser let through
            self.reject(line_no, raw, "RANGE", f"database refused it: {e}")
            if e.reason == "TRUNCATED":
                self.cut = True
        self.in_batch += 1
        if self.in_batch >= self.batch:
            self.commit()
            self.con.execute("BEGIN")
        if self.crash_after and self.counts["lines_read"] >= self.crash_after:
            self.log(f"  simulated crash after line {line_no} (nothing after the last batch is committed)")
            os._exit(3)

    def finish(self):
        self.commit()
        status = "DONE" if self.ended and not self.cut else "INCOMPLETE"
        self.con.execute("UPDATE ingest_run SET status = ?, finished_at = datetime('now') WHERE run_id = ?", (status, self.run_id))
        return status


def main(argv=None):
    ap = argparse.ArgumentParser(description="Ingest WSU-SEN 309 device records into SQLite")
    ap.add_argument("--db", default=os.path.join(ROOT, "data", "sen309.db"))
    ap.add_argument("--source", required=True, help="a capture file, '-', tcp://HOST:PORT or serial://PORT")
    ap.add_argument("--batch", type=int, default=20, help="lines per transaction (default 20)")
    ap.add_argument("--records", type=int, help="live sources: send STOP after this many readings")
    ap.add_argument("--resume", action="store_true", help="live sources: ask the device to REPLAY what we have not stored")
    ap.add_argument("--timeout", type=float, default=5.0, help="live sources: give up after this many silent seconds")
    ap.add_argument("--crash-after", type=int, help="testing only: stop dead after this many lines, without committing")
    args = ap.parse_args(argv)

    con = connect(args.db)
    src = Source(args.source, args.timeout)
    ing = Ingest(con, args.source, args.batch, args.crash_after)
    print(f"run {ing.run_id}: reading {args.source}")
    if src.interactive:
        src.send("HELLO")
    seen = 0
    stop_sent = False
    try:
        for line_no, raw, complete in src.lines():
            ing.handle(line_no, raw, complete)
            if ing.last_hello and args.resume and src.interactive:
                h, ing.last_hello = ing.last_hello, None
                ing.commit(); con.execute("BEGIN")
                n = next_seq(con, h.device, h.boot)
                print(f"  resume: asking {h.device} boot {h.boot} to replay from seq {n}")
                src.send(f"REPLAY {n}")
            if raw.startswith("R,") and complete:
                seen += 1
            if args.records and src.interactive and seen >= args.records and not stop_sent:
                src.send("STOP")
                stop_sent = True
            if ing.ended and src.interactive:
                break
    except KeyboardInterrupt:
        print("  interrupted by the user")
    finally:
        status = ing.finish()
        src.close()
    c = ing.counts
    print(f"run {ing.run_id} {status}: {c['lines_read']} lines, {c['inserted']} inserted, "
          f"{c['duplicates']} duplicates, {c['rejected']} rejected")
    return 0 if status == "DONE" else 1


if __name__ == "__main__":
    sys.exit(main())
