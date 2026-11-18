"""Parse and validate one line of the WSU-SEN 309 device record protocol (STARTER: Practical 3, Part A).

parse_line(text) returns a record object, returns None for a blank line, or raises ParseError
with a reason the ingest program stores in the rejected_line table:

    TRUNCATED  the line has no complete '*CK' ending (the link was cut, or it was never framed)
    CHECKSUM   the checksum does not match the body: the line was damaged on the way
    FORMAT     not a record: unknown type, wrong number of fields, or a field is not a number
    RANGE      a well-formed record whose value is impossible (for example 150.0 C)

(c) 2026 Wellspring University, Faculty of Computing. For registered WSU-SEN 309 students.
"""
import os
import re
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixture"))
from protocol import FIELD_COUNTS, checksum  # noqa: E402

DEVICE_RE = re.compile(r"SN\d\d")
TEMP_RE = re.compile(r"-?\d{1,3}\.\d")
TEMP_MIN, TEMP_MAX = -40.0, 125.0
LIGHT_MIN, LIGHT_MAX = 0, 1023
PERIOD_MIN, PERIOD_MAX = 200, 60000
STATES = ("RUN", "ALM")


class ParseError(ValueError):
    def __init__(self, reason, detail):
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class Hello:
    device: str
    boot: int
    fw: str
    period_ms: int


@dataclass(frozen=True)
class Reading:
    device: str
    boot: int
    seq: int
    t_ms: int
    temp_c: float
    light: int
    state: str


@dataclass(frozen=True)
class EndOfRun:
    device: str
    boot: int
    count: int
    last_seq: int


@dataclass(frozen=True)
class Status:
    device: str
    boot: int
    state: str
    seq: int
    period_ms: int


@dataclass(frozen=True)
class Ack:
    device: str
    boot: int
    command: str
    detail: str


@dataclass(frozen=True)
class DeviceError:
    device: str
    boot: int
    code: str
    detail: str


def _int(text, name):
    if not re.fullmatch(r"-?\d+", text):
        raise ParseError("FORMAT", f"{name} is not a whole number: {text!r}")
    return int(text)


def _check(ok, name, value):
    if not ok:
        raise ParseError("RANGE", f"{name} out of range: {value}")


def parse_line(text):
    line = text.rstrip("\r\n")
    if not line.strip():
        return None

    # 1. Framing: a record starts with a known type letter and a comma ...
    if len(line) < 2 or line[0] not in FIELD_COUNTS or line[1] != ",":
        raise ParseError("FORMAT", "not a record")
    # ... and ends with '*' and exactly two hex digits.
    # TODO A1: split the line at its LAST '*' into body and ck. If there is no '*', or ck is not
    #   exactly two hex digits (upper or lower case), raise ParseError("TRUNCATED", "...").
    body, ck = line, ""

    # 2. Integrity: the checksum must match the body.
    # TODO A2: if checksum(body) is not equal to int(ck, 16), raise ParseError("CHECKSUM", "...").

    # 3. Structure: the right number of fields for the type, and a valid device id and boot number.
    f = body.split(",")
    kind = f[0]
    if len(f) != FIELD_COUNTS[kind]:
        raise ParseError("FORMAT", f"{kind} record needs {FIELD_COUNTS[kind]} fields, has {len(f)}")
    if not DEVICE_RE.fullmatch(f[1]):
        raise ParseError("FORMAT", f"bad device id {f[1]!r}")
    device, boot = f[1], _int(f[2], "boot")
    _check(boot >= 0, "boot", boot)

    # 4. Content: convert each field and check its domain.
    if kind == "R":
        # TODO A3: convert the reading's fields and check each one, then return a Reading.
        #   seq and t_ms:  whole numbers (use _int), both >= 0
        #   temp_c:        must match TEMP_RE (else FORMAT), then TEMP_MIN <= temp <= TEMP_MAX (else RANGE)
        #   light:         whole number, LIGHT_MIN..LIGHT_MAX          state: one of STATES
        #   Use _check(condition, name, value) for every RANGE test. Look at the H branch below.
        raise NotImplementedError("TODO A3: parse an R line")
    if kind == "H":
        period = _int(f[4], "period_ms")
        _check(PERIOD_MIN <= period <= PERIOD_MAX, "period_ms", period)
        return Hello(device, boot, f[3], period)
    if kind == "E":
        count, last = _int(f[3], "count"), _int(f[4], "last_seq")
        _check(count >= 0, "count", count)
        _check(last >= -1, "last_seq", last)
        return EndOfRun(device, boot, count, last)
    if kind == "S":
        _check(f[3] in ("IDLE",) + STATES, "state", f[3])
        return Status(device, boot, f[3], _int(f[4], "seq"), _int(f[5], "period_ms"))
    if kind == "A":
        return Ack(device, boot, f[3], f[4])
    return DeviceError(device, boot, f[3], f[4])
