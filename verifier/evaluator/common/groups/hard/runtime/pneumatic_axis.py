#!/usr/bin/env python3
"""Structural model of a dual-solenoid pneumatic axis without timing claims."""

from __future__ import annotations


class PneumaticAxis:
    """Switch end sensors on the step after a command for structural tests.

    A step here is not a measured stroke time. Physical timing must be
    supplied separately by the F1P/F2 model.
    """

    def __init__(self, initially_open: bool = True, assumed_travel_ms: float | None = None):
        if assumed_travel_ms is not None and assumed_travel_ms <= 0:
            raise ValueError("Assumed stroke time must be positive")
        self.position = 0.0 if initially_open else 1.0
        self.assumed_travel_ms = assumed_travel_ms
        self.alarm = False
        self._pending: float | None = None
        self._motion_start = self.position
        self._elapsed_ms = 0.0

    def feedback(self) -> dict[str, int]:
        return {
            "at_open": int(self.position <= 0.0),
            "at_close": int(self.position >= 1.0),
            "alarm": int(self.alarm),
        }

    def apply_command(self, open_command: bool, close_command: bool) -> None:
        if open_command and close_command:
            self.alarm = True
            self._pending = None
        elif open_command:
            self.alarm = False
            if self.position != 0.0 and self._pending != 0.0:
                self._pending = 0.0
                self._motion_start = self.position
                self._elapsed_ms = 0.0
        elif close_command:
            self.alarm = False
            if self.position != 1.0 and self._pending != 1.0:
                self._pending = 1.0
                self._motion_start = self.position
                self._elapsed_ms = 0.0

    def step(self, dt_ms: float = 0.0) -> None:
        if self._pending is None:
            return
        if self.assumed_travel_ms is None:
            self.position = self._pending
            self._pending = None
            return
        self._elapsed_ms += float(dt_ms)
        ratio = min(1.0, self._elapsed_ms / self.assumed_travel_ms)
        self.position = self._motion_start + (self._pending - self._motion_start) * ratio
        if ratio >= 1.0:
            self.position = self._pending
            self._pending = None
