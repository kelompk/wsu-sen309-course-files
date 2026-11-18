#!/usr/bin/env python3
"""Check a capture of device output against the record protocol (Practical 1).

    python tools/check_capture.py data/my_wokwi.txt

For every line it checks the framing and the checksum, then checks that reading numbers (seq)
follow on without gaps and reports the time between readings. It does not store anything.
(c) 2026 Wellspring University, Faculty of Computing. For registered WSU-SEN 309 students.
"""
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixture"))
from protocol import FIELD_COUNTS, checksum  # noqa: E402


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    good = bad = 0
    last = {}
    gaps, deltas, kinds = [], [], {}
    with open(argv[0], encoding="ascii", errors="replace", newline="") as f:
        for n, raw in enumerate(f, 1):
            line = raw.rstrip("\r\n")
            if not line.strip():
                continue
            body, star, ck = line.rpartition("*")
            problem = None
            if not star or not re.fullmatch(r"[0-9A-Fa-f]{2}", ck):
                problem = "no *CK ending"
            elif checksum(body) != int(ck, 16):
                problem = f"checksum should be {checksum(body):02X}, line says {ck}"
            elif body[:1] not in FIELD_COUNTS or len(body.split(",")) != FIELD_COUNTS[body[0]]:
                problem = f"wrong type or number of fields ({len(body.split(','))})"
            if problem:
                bad += 1
                print(f"line {n}: BAD  {problem}:  {line[:60]}")
                continue
            good += 1
            f_ = body.split(",")
            kinds[f_[0]] = kinds.get(f_[0], 0) + 1
            if f_[0] == "R":
                key, seq, t = (f_[1], f_[2]), int(f_[3]), int(f_[4])
                if key in last and seq <= last[key][0]:
                    kinds["R repeated"] = kinds.get("R repeated", 0) + 1
                    continue
                if key in last:
                    pseq, pt = last[key]
                    if seq == pseq + 1:
                        deltas.append(t - pt)
                    elif seq > pseq + 1:
                        gaps.append(f"{pseq + 1}-{seq - 1}" if seq - pseq > 2 else str(pseq + 1))
                last[key] = (seq, t)
    print(f"{good} good lines, {bad} bad lines; record types: " + ", ".join(f"{k} x{v}" for k, v in sorted(kinds.items())))
    print("seq gaps: " + (", ".join(gaps) if gaps else "none"))
    if deltas:
        print(f"time between readings (ms): min {min(deltas)}, max {max(deltas)}, mean {statistics.mean(deltas):.1f}, "
              f"spread {max(deltas) - min(deltas)}  ({len(deltas)} intervals)")
    print("CAPTURE OK" if bad == 0 and not gaps and good else "CAPTURE HAS PROBLEMS")
    return 0 if bad == 0 and not gaps and good else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
