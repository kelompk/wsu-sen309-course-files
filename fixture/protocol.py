"""SEN 309 device record protocol, version 1: framing helpers shared by the fixture and the host.

Every line the device sends is  <body>*<CK>  followed by CR LF, where <CK> is the XOR of
every byte of <body>, written as two upper-case hex digits. The body is comma-separated and
its first field is the record type:

    H,<device>,<boot>,<fw>,<period_ms>                        hello (sent at boot and on HELLO)
    R,<device>,<boot>,<seq>,<t_ms>,<temp_c>,<light>,<state>   one reading; state is RUN or ALM
    E,<device>,<boot>,<count>,<last_seq>                      end of run (sent on STOP)
    S,<device>,<boot>,<state>,<seq>,<period_ms>               status (sent on STATUS)
    A,<device>,<boot>,<command>,<detail>                      command accepted
    X,<device>,<boot>,<code>,<detail>                         error or warning

See the Appendix of the workbook for the full interface contract.
"""

PROTOCOL_VERSION = 1
RECORD_TYPES = "HRESAX"
FIELD_COUNTS = {"H": 5, "R": 8, "E": 5, "S": 6, "A": 5, "X": 5}


def checksum(body: str) -> int:
    """XOR of all bytes in the body (the part before '*')."""
    c = 0
    for b in body.encode("ascii"):
        c ^= b
    return c


def frame(body: str) -> str:
    """Return the full line (without the line ending) for a record body."""
    return f"{body}*{checksum(body):02X}"


def tenths(value10: int) -> str:
    """Format an integer number of tenths the way the firmware does: 246 -> '24.6', -5 -> '-0.5'."""
    sign = "-" if value10 < 0 else ""
    v = abs(value10)
    return f"{sign}{v // 10}.{v % 10}"
