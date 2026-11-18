#!/usr/bin/env python3
"""WSU-SEN 309 serial fixture: a software copy of the sen309_logger firmware.

It speaks exactly the same record protocol as the board (or the Wokwi simulation), so the host
software can be built and tested with no hardware. It can also inject faults on purpose.

Two ways to run it:

  1. Write a capture file (fast; virtual time, nothing waits):
         python fixture/device_sim.py --count 60 --out data/run_clean.txt
         python fixture/device_sim.py --count 60 --faults corrupt@12,dup@20,cut@55 --out data/run_faulty.txt

  2. Behave like a serial port on a TCP socket (real time, accepts commands):
         python fixture/device_sim.py --tcp 7000 --speed 5
     then connect the host with  --source tcp://127.0.0.1:7000

Faults (comma-separated KIND@SEQ, applied when reading SEQ is sent):
  corrupt@N   flip one character of reading N, so its checksum no longer matches
  drop@N      reading N is lost on the link (the receiver never sees it)
  dup@N       reading N is sent twice
  garbage@N   a line of noise is sent just before reading N
  range@N     reading N carries an impossible temperature (150.0 C) with a valid checksum
  conflict@N  after reading N, reading N-5 is sent again with a different light value
  reboot@N    the device resets just before reading N: new boot number, seq starts again at 0
  cut@N       the link is cut half-way through reading N (file mode: the file ends there;
              TCP mode: the connection closes, but the device keeps sampling into its buffer)

(c) 2026 Wellspring University, Faculty of Computing. For registered WSU-SEN 309 students.
"""
import argparse
import math
import random
import socket
import sys
import time
from collections import deque

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
from protocol import frame, tenths  # noqa: E402

RING_SIZE = 32
FAULT_KINDS = {"corrupt", "drop", "dup", "garbage", "range", "conflict", "reboot", "cut"}


class SimDevice:
    """The firmware's behaviour: state machine, timed sampling, ring buffer and commands."""

    def __init__(self, device="SN01", boot=1, period_ms=1000, seed=309, autostart=True):
        self.device, self.boot, self.period = device, boot, period_ms
        self.fw = "1.0"
        self.rng = random.Random(seed)
        self.state = "IDLE"
        self.seq = 0
        self.sent = 0
        self.now = 0
        self.next_due = 0
        self.ring = deque(maxlen=RING_SIZE)
        self.out = [self.body_hello()]
        if autostart:
            self.start()

    # -- record bodies
    def body_hello(self):
        return f"H,{self.device},{self.boot},{self.fw},{self.period}"

    def body_reading(self, s):
        seq, t, t10, light, alarm = s
        return f"R,{self.device},{self.boot},{seq},{t},{tenths(t10)},{light},{'ALM' if alarm else 'RUN'}"

    def ack(self, what, detail="-"):
        return f"A,{self.device},{self.boot},{what},{detail}"

    def err(self, code, detail="-"):
        return f"X,{self.device},{self.boot},{code},{detail}"

    # -- sensors: a slowly varying temperature and light level, with a little noise
    def sense(self, t_ms):
        t = t_ms / 1000.0
        temp = 26.0 + 3.0 * math.sin(t / 40.0) + self.rng.uniform(-0.2, 0.2)
        light = int(500 + 250 * math.sin(t / 25.0) + self.rng.randint(-8, 8))
        return int(round(temp * 10)), max(0, min(1023, light))

    def start(self):
        self.state = "RUN"
        self.sent = 0
        self.next_due = self.now

    def take_sample(self):
        t10, light = self.sense(self.now)
        if self.state == "RUN" and t10 >= 350:
            self.state = "ALM"
        elif self.state == "ALM" and t10 <= 330:
            self.state = "RUN"
        s = (self.seq, self.now, t10, light, self.state == "ALM")
        self.seq += 1
        self.sent += 1
        self.ring.append(s)
        return s

    def advance(self, ms):
        """Move time on by ms; return the readings taken (as tuples)."""
        taken = []
        end = self.now + ms
        while self.state != "IDLE" and self.next_due <= end:
            self.now = self.next_due
            self.next_due += self.period
            taken.append(self.take_sample())
        self.now = end
        return taken

    def command(self, text):
        """Handle one command line; return the reply bodies."""
        c = text.strip()
        if c == "START":
            if self.state == "IDLE":
                self.start()
            return [self.ack("START")]
        if c == "STOP":
            if self.state == "IDLE":
                return [self.err("NOT_RUNNING")]
            last = self.seq - 1 if self.sent else -1
            self.state = "IDLE"
            return [f"E,{self.device},{self.boot},{self.sent},{last}"]
        if c == "STATUS":
            name = {"RUN": "RUN", "ALM": "ALM", "IDLE": "IDLE"}[self.state]
            return [f"S,{self.device},{self.boot},{name},{self.seq},{self.period}"]
        if c == "HELLO":
            return [self.body_hello()]
        if c.startswith("RATE "):
            v = c[5:]
            if v.isdigit() and 200 <= int(v) <= 60000:
                self.period = int(v)
                self.next_due = self.now + self.period
                return [self.ack("RATE", v)]
            return [self.err("BAD_RATE")]
        if c.startswith("REPLAY "):
            v = c[7:]
            if not v.isdigit():
                return [self.err("BAD_SEQ")]
            frm = int(v)
            out = []
            if self.ring and frm < self.ring[0][0]:
                out.append(self.err("GONE", str(self.ring[0][0])))
            sel = [s for s in self.ring if s[0] >= frm]
            out += [self.body_reading(s) for s in sel]
            out.append(self.ack("REPLAY", str(len(sel))))
            return out
        if len(c) > 24:
            return [self.err("TOO_LONG")]
        return [self.err("UNKNOWN")]

    def reboot(self):
        self.boot += 1
        self.seq = 0
        self.ring.clear()
        self.now = 0
        self.state = "IDLE"
        hello = self.body_hello()
        self.start()
        return hello


def parse_faults(spec):
    faults = {}
    if not spec:
        return faults
    for item in spec.split(","):
        kind, _, n = item.strip().partition("@")
        if kind not in FAULT_KINDS or not n.isdigit():
            raise SystemExit(f"bad fault '{item}': use KIND@SEQ with KIND one of {', '.join(sorted(FAULT_KINDS))}")
        faults.setdefault(int(n), []).append(kind)
    return faults


class Link:
    """Applies the fault plan to the device's output and produces the text the receiver gets."""

    def __init__(self, dev, faults, rng):
        self.dev, self.faults, self.rng = dev, faults, rng
        self.count = 0          # readings sent so far (fault positions count readings, so reboots work too)
        self.cut = False

    def reading_lines(self, s):
        """Text for one reading after faults; may set self.cut."""
        n = self.count
        self.count += 1
        kinds = self.faults.get(n, [])
        line = frame(self.dev.body_reading(s))
        out = []
        if "garbage" in kinds:
            out.append("~~ #@! line noise 0x7F ~~\r\n")
        if "range" in kinds:
            bad = (s[0], s[1], 1500, s[3], s[4])
            line = frame(self.dev.body_reading(bad))
        if "corrupt" in kinds:
            body, star, ck = line.partition("*")
            k = body.rfind(",", 0, body.rfind(",")) - 1         # the last digit of the temperature field
            ch = "7" if body[k] != "7" else "3"
            line = body[:k] + ch + body[k + 1:] + star + ck
        if "drop" in kinds:
            return out
        if "cut" in kinds:
            out.append(line[: len(line) // 2])
            self.cut = True
            return out
        out.append(line + "\r\n")
        if "dup" in kinds:
            out.append(line + "\r\n")
        if "conflict" in kinds and s[0] >= 5:
            old = [x for x in self.dev.ring if x[0] == s[0] - 5]
            if old:
                o = old[0]
                out.append(frame(self.dev.body_reading((o[0], o[1], o[2], (o[3] + 37) % 1024, o[4]))) + "\r\n")
        return out

    def pending_reboot(self):
        return "reboot" in self.faults.get(self.count, [])


def run_file(args):
    faults = parse_faults(args.faults)
    dev = SimDevice(args.device, args.boot, args.period, args.seed)
    link = Link(dev, faults, random.Random(args.seed))
    chunks = [frame(b) + "\r\n" for b in dev.out]
    while link.count < args.count and not link.cut:
        if link.pending_reboot():
            faults[link.count].remove("reboot")
            chunks.append(frame(dev.reboot()) + "\r\n")
        for s in dev.advance(dev.period):
            chunks += link.reading_lines(s)
            if link.cut or link.count >= args.count:
                break
    if not link.cut:
        chunks += [frame(b) + "\r\n" for b in dev.command("STOP")]
    text = "".join(chunks)
    if args.out:
        with open(args.out, "w", newline="") as f:
            f.write(text)
        print(f"wrote {args.out}: {text.count(chr(10))} complete lines" + (" (link cut: last line incomplete)" if link.cut else ""),
              file=sys.stderr)
    else:
        sys.stdout.write(text)


def run_tcp(args):
    faults = parse_faults(args.faults)
    dev = SimDevice(args.device, args.boot, args.period, args.seed)
    link = Link(dev, faults, random.Random(args.seed))
    srv = socket.create_server(("127.0.0.1", args.tcp))
    print(f"fixture: device {dev.device} boot {dev.boot} listening on tcp://127.0.0.1:{args.tcp} (speed x{args.speed}); Ctrl+C to stop",
          file=sys.stderr, flush=True)
    pending = [frame(b) + "\r\n" for b in dev.out]      # what the device has printed since power-up
    last = time.monotonic()
    srv_conn = None
    try:
        while True:
            conn, addr = srv_conn or srv.accept()
            srv_conn = None
            conn.settimeout(0.02)
            print(f"fixture: host connected from {addr[0]}:{addr[1]}", file=sys.stderr, flush=True)
            link.cut = False
            rx = b""
            try:
                for chunk in pending:
                    conn.sendall(chunk.encode())
                pending = []
                while not link.cut:
                    now = time.monotonic()
                    for s in dev.advance(int((now - last) * 1000 * args.speed)):
                        for chunk in link.reading_lines(s):
                            conn.sendall(chunk.encode())
                        if link.cut:
                            break
                    last = now
                    if link.cut:
                        break
                    try:
                        data = conn.recv(256)
                        if not data:
                            break
                        rx += data
                        while b"\n" in rx:
                            line, rx = rx.split(b"\n", 1)
                            for b in dev.command(line.decode(errors="replace").replace("\r", "")):
                                conn.sendall((frame(b) + "\r\n").encode())
                    except socket.timeout:
                        pass
            except (BrokenPipeError, ConnectionResetError):
                pass
            conn.close()
            print("fixture: link closed" + (" (cut fault)" if link.cut else "") + "; device keeps sampling", file=sys.stderr, flush=True)
            # readings taken while nobody listens are lost from the link but kept in the ring buffer
            conn, addr = srv.accept()
            for _ in dev.advance(int((time.monotonic() - last) * 1000 * args.speed)):
                link.count += 1
            last = time.monotonic()
            srv_conn = (conn, addr)
    except KeyboardInterrupt:
        print("fixture: stopped", file=sys.stderr)


def main(argv=None):
    ap = argparse.ArgumentParser(description="WSU-SEN 309 serial fixture (software copy of the sen309_logger firmware)")
    ap.add_argument("--device", default="SN01", help="device id, SN followed by two digits (default SN01)")
    ap.add_argument("--boot", type=int, default=1, help="boot number reported in the records (default 1)")
    ap.add_argument("--period", type=int, default=1000, help="sampling period in ms (default 1000)")
    ap.add_argument("--seed", type=int, default=309, help="random seed for the sensor noise (default 309)")
    ap.add_argument("--count", type=int, default=60, help="file mode: number of readings (default 60)")
    ap.add_argument("--faults", default="", help="fault plan, for example corrupt@12,dup@20,cut@55")
    ap.add_argument("--out", help="file mode: write here instead of standard output")
    ap.add_argument("--tcp", type=int, metavar="PORT", help="serve on 127.0.0.1:PORT like a serial port, in real time")
    ap.add_argument("--speed", type=float, default=1.0, help="TCP mode: run the device clock this many times faster")
    args = ap.parse_args(argv)
    if not (len(args.device) == 4 and args.device.startswith("SN") and args.device[2:].isdigit()):
        ap.error("--device must be SN followed by two digits, for example SN07")
    run_tcp(args) if args.tcp else run_file(args)


if __name__ == "__main__":
    main()
