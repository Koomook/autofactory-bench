"""Typed ST memory image and registered I/O address collection."""
from __future__ import annotations
import re
from typing import Any

ADDRESS = re.compile(r"^(?:SM|SD|ZR|X|Y|M|L|B|F|D|W|R|T|C|Z)[0-9A-F]+$", re.I)

class _StMemory:
    def __init__(self) -> None:
        self.values: dict[str, int] = {}

    def read_bit(self, device: Any) -> int:
        return int(bool(self.values.get(str(device.raw).upper(), 0)))

    def read_word(self, device: Any) -> int:
        return int(self.values.get(str(device.raw).upper(), 0))

def binding_addresses(binding: dict[str, Any]) -> tuple[str, ...]:
    values: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
        elif isinstance(value, str) and ADDRESS.fullmatch(value):
            values.add(value.upper())

    visit(binding)
    return tuple(sorted(values))
