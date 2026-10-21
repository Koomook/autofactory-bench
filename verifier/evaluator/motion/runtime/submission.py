#!/usr/bin/env python3
"""Run ST submissions through the common PLC scan and memory interface."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Protocol

HERE = Path(__file__).resolve().parent
ADDRESS = re.compile(r"^(?:SM|SD|ZR|X|Y|M|L|B|F|D|W|R|T|C|Z)[0-9A-F]+$", re.I)


class PlcMemory(Protocol):
    def read_bit(self, device: Any) -> int: ...
    def read_word(self, device: Any) -> int: ...


class ProgramRuntime(Protocol):
    language: str
    memory: PlcMemory
    missing_symbols: tuple[str, ...]

    def run_scan(self, inputs: dict[str, int]) -> None: ...
    def close(self) -> None: ...


class _StMemory:
    def __init__(self) -> None:
        self.values: dict[str, int] = {}

    def read_bit(self, device: Any) -> int:
        return int(bool(self.values.get(str(device.raw).upper(), 0)))

    def read_word(self, device: Any) -> int:
        return int(self.values.get(str(device.raw).upper(), 0))


def _bridge_output() -> Path:
    return HERE / "st_runtime/st_bridge.js"


def _ensure_st_bridge() -> Path:
    """Use the packaged, sealed bridge; never rebuild a frozen release."""
    output = _bridge_output()
    if not output.is_file():
        raise RuntimeError("Missing sealed ST bridge; restore the release package")
    return output


class StRuntime:
    language = "st"

    def __init__(self, source: str, scan_ms: float, watch: tuple[str, ...]):
        self.memory = _StMemory()
        self._process = subprocess.Popen(
            ["node", str(_ensure_st_bridge())],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        try:
            reply = self._request({
                "op": "init", "source": source, "scan_ms": scan_ms, "watch": list(watch),
            })
        except Exception:
            # Invalid external submissions must not leave a bridge subprocess.
            self.close()
            raise
        self.missing_symbols = tuple(str(item) for item in reply.get("missing", []))
        if self.missing_symbols:
            self.close()
            raise ValueError(f"Required I/O symbols are missing from the ST submission: {', '.join(self.missing_symbols)}")

    def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._process.stdin is None or self._process.stdout is None:
            raise RuntimeError("ST bridge pipe is closed")
        self._process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self._process.stdin.flush()
        line = self._process.stdout.readline()
        if not line:
            stderr = self._process.stderr.read() if self._process.stderr else ""
            raise RuntimeError(f"ST bridge exited: {stderr}")
        reply = json.loads(line)
        if not reply.get("ok"):
            raise RuntimeError(
                f"ST runtime error L{reply.get('line', 0)}:{reply.get('col', 0)}: {reply.get('error')}"
            )
        return reply

    def run_scan(self, inputs: dict[str, int]) -> None:
        reply = self._request({"op": "scan", "inputs": inputs})
        self.memory.values = {
            str(name).upper(): int(value) for name, value in reply["values"].items()
        }

    def close(self) -> None:
        try:
            if self._process.poll() is None:
                self._request({"op": "close"})
                self._process.wait(timeout=2)
        finally:
            if self._process.poll() is None:
                self._process.terminate()
                self._process.wait(timeout=2)
            for stream in (
                self._process.stdin, self._process.stdout, self._process.stderr,
            ):
                if stream is not None and not stream.closed:
                    stream.close()


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


def create_runtime(
    program: Path, scan_ms: float, binding: dict[str, Any],
) -> ProgramRuntime:
    suffix = program.suffix.lower()
    source = program.read_text(encoding="utf-8")
    watch = binding_addresses(binding)
    if suffix == ".st":
        return StRuntime(source, scan_ms, watch)
    raise ValueError(f"Unsupported submission extension: {program.suffix}")
