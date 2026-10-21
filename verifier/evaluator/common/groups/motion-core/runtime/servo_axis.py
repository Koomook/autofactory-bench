#!/usr/bin/env python3
"""Generic one-dimensional servo axis.

This module has no knowledge of equipment names, PLC addresses, or actual
calibration. Calibration values are supplied by the task package.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Any, Literal


@dataclass(frozen=True)
class PositionPoint:
    number: int
    position_mm: float
    speed_mm_min: float


@dataclass(frozen=True)
class ServoCalibration:
    pulse_per_rev: int
    mm_per_rev: float
    speed_limit_mm_min: float
    accel_ms: float
    decel_ms: float
    points: dict[int, PositionPoint]

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ServoCalibration":
        points = {
            int(p["number"]): PositionPoint(
                number=int(p["number"]),
                position_mm=float(p["position_mm"]),
                speed_mm_min=float(p["speed_mm_min"]),
            )
            for p in raw["points"]
        }
        obj = cls(
            pulse_per_rev=int(raw["pulse_per_rev"]),
            mm_per_rev=float(raw["mm_per_rev"]),
            speed_limit_mm_min=float(raw["speed_limit_mm_min"]),
            accel_ms=float(raw["accel_ms"]),
            decel_ms=float(raw["decel_ms"]),
            points=points,
        )
        obj.validate()
        return obj

    def validate(self) -> None:
        if self.pulse_per_rev <= 0 or self.mm_per_rev <= 0:
            raise ValueError("pulse_per_rev and mm_per_rev must be positive")
        if self.speed_limit_mm_min <= 0 or self.accel_ms <= 0 or self.decel_ms <= 0:
            raise ValueError("Speed limit and acceleration/deceleration times must be positive")
        if not self.points:
            raise ValueError("At least one positioning point is required")
        for point in self.points.values():
            if point.speed_mm_min <= 0:
                raise ValueError(f"Point {point.number}: speed must be positive")
            if point.speed_mm_min > self.speed_limit_mm_min:
                raise ValueError(f"Point {point.number}: commanded speed exceeds the axis limit")


@dataclass(frozen=True)
class MotionProfile:
    start_mm: float
    target_mm: float
    direction: float
    accel_mm_s2: float
    decel_mm_s2: float
    peak_mm_s: float
    accel_s: float
    cruise_s: float
    decel_s: float
    accel_dist_mm: float
    cruise_dist_mm: float

    @property
    def duration_s(self) -> float:
        return self.accel_s + self.cruise_s + self.decel_s

    @classmethod
    def build(
        cls,
        start_mm: float,
        target_mm: float,
        speed_mm_s: float,
        accel_ms: float,
        decel_ms: float,
    ) -> "MotionProfile":
        if speed_mm_s <= 0 or accel_ms <= 0 or decel_ms <= 0:
            raise ValueError("Speed and acceleration/deceleration times must be positive")
        distance = abs(target_mm - start_mm)
        direction = 1.0 if target_mm >= start_mm else -1.0
        accel = speed_mm_s / (accel_ms / 1000.0)
        decel = speed_mm_s / (decel_ms / 1000.0)
        ramp_distance = speed_mm_s * (accel_ms + decel_ms) / 2000.0
        if distance >= ramp_distance:
            peak = speed_mm_s
            ta = accel_ms / 1000.0
            td = decel_ms / 1000.0
            da = 0.5 * accel * ta * ta
            dd = 0.5 * decel * td * td
            dc = max(0.0, distance - da - dd)
            tc = dc / peak
        else:
            peak = sqrt(2.0 * distance / ((1.0 / accel) + (1.0 / decel))) if distance else 0.0
            ta = peak / accel if accel else 0.0
            td = peak / decel if decel else 0.0
            da = 0.5 * accel * ta * ta
            dc = tc = 0.0
        return cls(start_mm, target_mm, direction, accel, decel, peak,
                   ta, tc, td, da, dc)

    def sample(self, elapsed_s: float) -> tuple[float, float, bool]:
        """Return absolute position (mm), signed velocity (mm/s), and completion."""
        t = max(0.0, elapsed_s)
        if t >= self.duration_s:
            return self.target_mm, 0.0, True
        if t <= self.accel_s:
            v = self.accel_mm_s2 * t
            dist = 0.5 * self.accel_mm_s2 * t * t
        elif t <= self.accel_s + self.cruise_s:
            u = t - self.accel_s
            v = self.peak_mm_s
            dist = self.accel_dist_mm + self.peak_mm_s * u
        else:
            u = t - self.accel_s - self.cruise_s
            v = max(0.0, self.peak_mm_s - self.decel_mm_s2 * u)
            dist = (self.accel_dist_mm + self.cruise_dist_mm
                    + self.peak_mm_s * u - 0.5 * self.decel_mm_s2 * u * u)
        return self.start_mm + self.direction * dist, self.direction * v, False


@dataclass(frozen=True)
class ConstantSpeedProfile:
    """Constant-speed F0 comparison profile without acceleration or deceleration."""

    start_mm: float
    target_mm: float
    direction: float
    speed_mm_s: float

    @property
    def duration_s(self) -> float:
        distance = abs(self.target_mm - self.start_mm)
        return distance / self.speed_mm_s if self.speed_mm_s > 0 else 0.0

    @property
    def decel_mm_s2(self) -> float:
        # F0 stops immediately; this value keeps the type compatible with F1S.
        return float("inf")

    @classmethod
    def build(
        cls, start_mm: float, target_mm: float, speed_mm_s: float,
    ) -> "ConstantSpeedProfile":
        if speed_mm_s <= 0:
            raise ValueError("Speed must be positive")
        direction = 1.0 if target_mm >= start_mm else -1.0
        return cls(start_mm, target_mm, direction, speed_mm_s)

    def sample(self, elapsed_s: float) -> tuple[float, float, bool]:
        t = max(0.0, elapsed_s)
        if t >= self.duration_s:
            return self.target_mm, 0.0, True
        distance = self.speed_mm_s * t
        return (
            self.start_mm + self.direction * distance,
            self.direction * self.speed_mm_s,
            False,
        )


class ServoAxis:
    """Minimal servo state machine with point start, Busy, In-position, and Stop."""

    def __init__(
        self,
        calibration: ServoCalibration,
        initial_position_mm: float = 0.0,
        profile_mode: Literal["f0", "f1s"] = "f1s",
    ):
        if profile_mode not in {"f0", "f1s"}:
            raise ValueError(f"Unsupported profile mode: {profile_mode}")
        self.calibration = calibration
        self.profile_mode = profile_mode
        self.position_mm = float(initial_position_mm)
        self.velocity_mm_s = 0.0
        self.busy = False
        self.in_position = False
        self.alarm = False
        self.active_point: int | None = None
        self._profile: MotionProfile | ConstantSpeedProfile | None = None
        self._elapsed_s = 0.0
        self._start_prev = False
        self._stopping = False

    def feedback(self) -> dict[str, int]:
        return {
            "busy": int(self.busy),
            "in_position": int(self.in_position),
            "alarm": int(self.alarm),
        }

    def apply_command(self, point_number: int, start: bool, stop: bool = False) -> None:
        rising = bool(start) and not self._start_prev
        self._start_prev = bool(start)
        if stop and self.busy:
            self._stopping = True
            self.in_position = False
        if not rising:
            return
        if self.busy:
            self.alarm = True
            return
        point = self.calibration.points.get(int(point_number))
        if point is None:
            self.alarm = True
            self.in_position = False
            return
        speed = min(point.speed_mm_min, self.calibration.speed_limit_mm_min) / 60.0
        if self.profile_mode == "f0":
            self._profile = ConstantSpeedProfile.build(
                self.position_mm, point.position_mm, speed,
            )
        else:
            self._profile = MotionProfile.build(
                self.position_mm,
                point.position_mm,
                speed,
                self.calibration.accel_ms,
                self.calibration.decel_ms,
            )
        self._elapsed_s = 0.0
        self._stopping = False
        self.active_point = point.number
        self.busy = self._profile.duration_s > 0.0
        self.in_position = not self.busy
        self.alarm = False
        if not self.busy:
            self.position_mm = point.position_mm

    def step(self, dt_ms: float) -> None:
        if not self.busy or self._profile is None:
            return
        dt_s = float(dt_ms) / 1000.0
        if self._stopping:
            if self.profile_mode == "f0":
                self.velocity_mm_s = 0.0
                self.busy = False
                self._profile = None
                return
            decel = self._profile.decel_mm_s2
            old_v = self.velocity_mm_s
            dv = min(abs(old_v), decel * dt_s)
            new_v = (abs(old_v) - dv) * (1.0 if old_v >= 0 else -1.0)
            self.position_mm += 0.5 * (old_v + new_v) * dt_s
            self.velocity_mm_s = new_v
            if abs(new_v) < 1e-12:
                self.busy = False
                self._profile = None
            return
        self._elapsed_s += dt_s
        self.position_mm, self.velocity_mm_s, done = self._profile.sample(self._elapsed_s)
        if done:
            self.busy = False
            self.in_position = True
            self.velocity_mm_s = 0.0
            self._profile = None
