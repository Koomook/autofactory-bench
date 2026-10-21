"""PLC device-address parsing shared by the ST evaluator backends.

The address semantics are unchanged from the frozen MELSEC IL helper. This
module does not parse or execute IL programs.
"""

import re
from dataclasses import dataclass


HEX_DEVS = {"X", "Y", "B", "W"}
BIT_PREFIXES = ("SM", "X", "Y", "M", "L", "B", "F")
WORD_PREFIXES = ("SD", "ZR", "D", "W", "R", "Z")

DEV_RE = re.compile(
    r"^(?P<u>U[0-9A-F]+(?:Z\d+)?\\G\d+(?:Z\d+)?)(?P<ubit>\.[0-9A-F]+)?$"
    r"|^(?P<pfx>SM|SD|ZR|X|Y|M|L|B|F|D|W|R|T|C|Z)(?P<num>[0-9A-F]+)"
    r"(?:(?P<bit>\.[0-9A-F]+)|(?P<idx>Z\d+))?$"
)
CONST_RE = re.compile(r"^K(-?\d+)$|^H([0-9A-F]+)$")


class DeviceAddressError(Exception):
    """A device reference cannot be parsed."""


@dataclass(frozen=True)
class Dev:
    """Normalized device reference."""

    kind: str
    pfx: str = ""
    num: int = 0
    bit: int = -1
    idx: str = ""
    value: int = 0
    raw: str = ""

    def __repr__(self):
        return f"<{self.raw}>"


def parse_operand(tok: str) -> Dev:
    """Parse a MELSEC device address or constant without parsing IL code."""
    m = CONST_RE.match(tok)
    if m:
        v = int(m.group(1)) if m.group(1) is not None else int(m.group(2), 16)
        return Dev(kind="const", value=v, raw=tok)
    m = DEV_RE.match(tok)
    if not m:
        raise DeviceAddressError(f"Cannot parse device: {tok!r}")
    if m.group("u"):
        return Dev(kind="ubuf", pfx=m.group("u"),
                   bit=int(m.group("ubit")[1:], 16) if m.group("ubit") else -1,
                   raw=tok)
    pfx, num = m.group("pfx"), m.group("num")
    n = int(num, 16) if pfx in HEX_DEVS else int(num, 10)
    if pfx in ("T", "C"):
        return Dev(kind=pfx, pfx=pfx, num=n, raw=tok)
    if m.group("bit"):
        if pfx not in WORD_PREFIXES and pfx not in ("D",):
            raise DeviceAddressError(f"Device does not support word-bit addressing: {tok!r}")
        return Dev(kind="wordbit", pfx=pfx, num=n,
                   bit=int(m.group("bit")[1:], 16), raw=tok)
    if m.group("idx"):
        kind = "bit" if pfx in BIT_PREFIXES else "word"
        return Dev(kind=kind, pfx=pfx, num=n, idx=m.group("idx"), raw=tok)
    if pfx == "Z" or pfx in ("SD", "ZR", "D", "W", "R"):
        return Dev(kind="word", pfx=pfx, num=n, raw=tok)
    return Dev(kind="bit", pfx=pfx, num=n, raw=tok)
