"""E11–E15: reduced-order, position-derived material-flow models.

No pre-timed completion flags: optical feedback comes from part coordinates;
fork/carrier endpoints come from their travel. This is not a rigid-body or
manufacturer-accurate magnetic-field simulator.
"""
from __future__ import annotations

from typing import Any
from plants import parse_operand


class MaterialEasyExtensionPlant:
    MODES = {"stopper", "count", "fork", "route", "shuttle", "turnover", "reject", "gapping"}

    def __init__(self, mode: str, binding: dict, calibration: dict,
                 parameters: dict, factor: float = 1.0):
        if mode not in self.MODES:
            raise ValueError(f"Unknown material primitive: {mode}")
        self.mode, self.binding = mode, binding
        self.speed = float(calibration["speed_per_second"]) / factor
        self.gate_ms = float(calibration.get("gate_travel_ms", 200)) * factor
        if self.speed <= 0 or self.gate_ms <= 0:
            raise ValueError("Positive physical calibration required")
        self.gap = float(parameters.get("piece_gap", .45))
        if self.gap <= .16:
            raise ValueError("Counting workpieces must be optically separable")
        self.p = 1.0 if mode == "fork" else 0.0
        self.lift = 0.0
        self.acquired = False
        self.grip = 1.0
        self.drop_distance = 0.0
        self.eject_travel = 0.0
        self.reject_requested: bool | None = None
        self.gate = 0.0  # 0 = raised, 1 = retracted below belt
        self.count = 0
        self.passed_ids: set[int] = set()
        self.dropped_ids: set[int] = set()
        self.cmd: dict[str, int] = {}
        self.operands = {key: parse_operand(address) for key, address in binding["outputs"].items()}
        self.external_operands = {key: parse_operand(address) for key, address in binding["external"].items()}
        self.complete_operand = parse_operand(binding["result"]["completion"])
        self.route_right: bool | None = None
        self.pending: list[str] = []
        self.violations: list[dict] = []
        self.emitted: set[str] = set()
        self.velocity = 0.0
        if mode == "gapping":
            initial_gap = float(parameters.get("initial_surface_gap", .04))
            if not 0 <= initial_gap <= .08:
                raise ValueError("Gapping starts with a close, non-overlapping pair")
            self.pair_x = [-.25, -.41 - initial_gap]
            self.belt_travel = [0.0, 0.0]
            self.high_speed_ratio = float(calibration.get("outfeed_high_speed_ratio", 2.5))
            if self.high_speed_ratio <= 1:
                raise ValueError("Gapping high speed must exceed infeed speed")

    def part_x(self, index: int = 0) -> float:
        if self.mode == "gapping":
            return self.pair_x[index]
        if self.mode == "count":
            return -.10 - index * self.gap + self.p
        if self.mode == "stopper":
            return -.13 + self.p
        return self.p

    def feedback(self) -> dict[str, int]:
        if self.mode == "gapping":
            states = {key: any(abs(x - sensor_x) <= .08 + 1e-9 for x in self.pair_x)
                      for key, sensor_x in [("rear_zone", .55), ("front_zone", 1.05)]}
        elif self.mode == "stopper":
            states = {"gate_down": self.gate >= 1, "exit": abs(self.part_x() - .85) <= .08 + 1e-9,
                      "buffer": abs(self.part_x() + .13) <= .08 + 1e-9}
        elif self.mode == "count":
            states = {"photo": any(abs(self.part_x(i) - .40) <= .08 + 1e-9 for i in range(4))}
        elif self.mode == "route":
            states = {"left": abs(self.p + .95) <= .08 + 1e-9, "right": abs(self.p - .95) <= .08 + 1e-9,
                      "present": abs(self.p) <= .08 + 1e-9}
        elif self.mode == "fork":
            sensor_z = -.045 + .85 * self.p
            part_z = -.32 + (.85 * self.p if self.acquired else 0)
            sensor_y = .6475 + .08 * self.lift + .02
            part_y = .6875 + (.08 * max(0, self.lift - .5) if self.acquired else 0)
            seen = abs(sensor_y - part_y) <= .08 + 1e-9 and part_z + .08 >= sensor_z - .40 - 1e-9 and part_z - .08 <= sensor_z + 1e-9
            states = {"home": self.p >= 1 - 1e-9, "target": self.p <= 1e-9,
                      "loaded": seen, "lifted": self.lift >= 1 - 1e-9}
        elif self.mode == "reject":
            z = -1.05 * self.eject_travel
            states = {"home": self.p <= 1e-9, "target": self.p >= 1 - 1e-9,
                      "present": abs(z) <= .08 + 1e-9, "ejected": abs(z + 1.05) <= .08 + 1e-9}
        elif self.mode == "turnover":
            states = {"home": self.p <= 1e-9, "target": self.p >= 1 - 1e-9,
                      "loaded": self.grip >= 1 - 1e-9 and not self.dropped_ids}
        else:
            states = {"home": self.p <= 1e-9, "target": self.p >= 1 - 1e-9,
                      "loaded": not self.dropped_ids}
        return {self.binding["inputs"][key]: int(value) for key, value in states.items()}

    def read_commands(self, memory: Any) -> dict:
        return {**{key: int(memory.read_bit(op)) for key, op in self.operands.items()},
                **{key: int(memory.read_bit(op)) for key, op in self.external_operands.items()},
                "complete": int(memory.read_bit(self.complete_operand))}

    def apply_commands(self, commands: dict) -> None:
        self.cmd = dict(commands)
        if self.mode == "reject" and commands.get("start") and self.reject_requested is None:
            self.reject_requested = bool(commands.get("reject"))
        if commands.get("start") and self.route_right is None:
            self.route_right = bool(commands.get("select_right"))

    def step_devices(self, dt_ms: float) -> None:
        self.pending = []
        old = self.p
        a, b = bool(self.cmd.get("a")), bool(self.cmd.get("b"))
        delta = self.speed * dt_ms / 1000
        if self.mode == "gapping":
            speeds = [self.speed * a, self.speed * (self.high_speed_ratio if self.cmd.get("c") else 1) * b]
            dt = dt_ms / 1000
            # Reduced-order handoff: overlap-weighted surface velocity while
            # a cube spans the belt joint. No snapping or scripted gap growth.
            for i, x in enumerate(self.pair_x):
                downstream = max(0.0, min(1.0, (x + .08) / .16))
                self.pair_x[i] += ((1 - downstream) * speeds[0] + downstream * speeds[1]) * dt
                if self.pair_x[i] > 2.52:
                    self.dropped_ids.add(i)
                    self.pending.append("workpiece_lost")
            self.belt_travel = [v + s * dt for v, s in zip(self.belt_travel, speeds)]
            self.p = self.pair_x[0] + .25
            if self.pair_x[0] - self.pair_x[1] < .16 - 1e-9:
                self.pending.append("workpiece_collision")
            if self.cmd.get("complete") and any(speeds):
                self.pending.append("moving_at_completion")
        elif self.mode == "stopper":
            gate_was_down = self.gate >= 1
            if a:
                self.gate = min(1.0, self.gate + dt_ms / self.gate_ms)
            if b and not gate_was_down:
                self.pending.append("belt_before_gate_clear")
            if b and gate_was_down:
                self.p += delta
        elif self.mode == "count":
            if a:
                self.p += delta
            for i in range(4):
                if self.part_x(i) > .48 + 1e-9 and i not in self.passed_ids:
                    self.passed_ids.add(i)
                    self.count += 1
                    self.pending.append("piece_passed")
            if self.count > 3:
                self.pending.append("excess_piece")
        elif self.mode == "fork":
            if a and b:
                self.pending.append("opposed_drives")
            elif a:
                self.p = max(0, self.p - delta)
            elif b:
                if not self.acquired:
                    self.pending.append("retract_without_load")
                elif self.lift < 1 - 1e-9:
                    self.pending.append("withdraw_before_clearance")
                self.p = min(1, self.p + delta)
            if self.cmd.get("c"):
                if self.p > 1e-9 and not self.acquired:
                    self.pending.append("lift_before_insertion")
                self.lift = min(1.0, self.lift + dt_ms / (self.gate_ms * 1.5))
            if self.p <= 1e-9 and self.lift >= .5 and not self.acquired:
                self.acquired = True
                self.pending.append("workpiece_picked")
        elif self.mode == "reject":
            if (a or b) and self.reject_requested is not True:
                self.pending.append("accepted_part_actuated")
            if a and b:
                self.pending.append("opposed_drives")
            elif a:
                self.p = min(1, self.p + delta)
                self.eject_travel = max(self.eject_travel, self.p)
            elif b:
                if self.eject_travel < 1 - 1e-9:
                    self.pending.append("return_before_ejection")
                self.p = max(0, self.p - delta)
        elif self.mode == "turnover":
            if self.cmd.get("c"):
                self.grip = max(0, self.grip - dt_ms / self.gate_ms)
                if self.grip < .98:
                    self.dropped_ids.add(0)
                    self.pending.append("workpiece_lost")
            if a and b:
                self.pending.append("opposed_drives")
            elif a or b:
                self.p = max(0, min(1, self.p + (delta if a else -delta)))
            if self.dropped_ids:
                self.drop_distance = min(.85, self.drop_distance + .8 * dt_ms / 1000)
        else:
            if a and b:
                self.pending.append("opposed_drives")
            elif a or b:
                direction = (-1 if a else 1) if self.mode == "route" else (1 if a else -1)
                if self.mode == "shuttle" and not self.cmd.get("ready"):
                    self.pending.append("transfer_before_receiver_ready")
                self.p += direction * delta
                if self.mode != "route":
                    self.p = max(0.0, min(1.0, self.p))
            if self.mode == "route" and abs(self.p) >= .87:
                if self.route_right is None or (self.p > 0) != self.route_right:
                    self.pending.append("wrong_outlet")
        # Explicit finite support: continuing past a belt edge loses the part.
        limit = 2.12 if self.mode == "count" else 1.22
        for i in range(4 if self.mode == "count" else 1):
            if self.mode in {"count", "route", "stopper"} and abs(self.part_x(i)) > limit:
                self.dropped_ids.add(i)
                self.pending.append("workpiece_lost")
        self.velocity = (self.p - old) / (dt_ms / 1000)
        if self.cmd.get("complete") and abs(self.velocity) > 1e-9:
            self.pending.append("moving_at_completion")

    def resolve_interactions(self, scan: int) -> list[dict]:
        events = []
        for kind in self.pending:
            if kind == "piece_passed" or kind not in self.emitted:
                event = {"type": kind, "scan": scan}
                events.append(event)
                self.emitted.add(kind)
                if kind not in {"piece_passed", "workpiece_picked"}:
                    self.violations.append(event)
        return events

    def snapshot(self) -> dict:
        if self.mode == "gapping":
            front, rear = self.pair_x
            goal = abs(front - 1.05) <= .08 + 1e-9 and abs(rear - .55) <= .08 + 1e-9 and front - rear - .16 >= .26 - 1e-9
        elif self.mode == "count":
            goal = self.count == 3
        elif self.mode == "stopper":
            goal = self.gate >= 1 and abs(self.part_x() - .85) <= .08 + 1e-9
        elif self.mode == "route":
            target = .95 if self.route_right else -.95
            goal = self.route_right is not None and abs(self.p - target) <= .08 + 1e-9
        elif self.mode == "reject":
            goal = self.p <= 1e-9 and (
                self.eject_travel >= 1 - 1e-9 if self.reject_requested is True else
                self.reject_requested is False and self.eject_travel <= 1e-9)
        elif self.mode == "fork":
            goal = self.p >= 1 - 1e-9 and self.acquired and self.lift >= 1 - 1e-9
        else:
            goal = self.p >= 1 - 1e-9
        parts = {
            f"PART_{i + 1:02d}": {"owner": "carrier", "status": "dropped" if i in self.dropped_ids else "idle",
                                  "x": self.part_x(i), "drop": int(i in self.dropped_ids)}
            for i in range(4 if self.mode == "count" else 2 if self.mode == "gapping" else 1)
        }
        if self.mode == "fork":
            parts["PART_01"]["owner"] = "carrier" if self.acquired else "source_jig"
        if self.mode == "turnover" and self.dropped_ids:
            parts["PART_01"]["owner"] = "dropped"
        belt_display = self.count / 4 if self.mode == "count" else (
            (self.p + 1.3) / 2.6 if self.mode == "route" else self.p / 1.35)
        return {"position": self.p, "velocity": self.velocity,
                "visual": {"gate": 1 - self.gate, "belt": max(0, min(1, belt_display)), "position": self.p,
                           "fork_lift": .08 * self.lift,
                           "load_lift": .08 * max(0, self.lift - .5) if self.acquired else 0,
                           "load_travel": self.p if self.acquired else 0, "grip": self.grip,
                           "drop_distance": self.drop_distance,
                           **({"eject_travel": self.eject_travel} if self.mode == "reject" else {}),
                           **({"infeed_travel": self.belt_travel[0] / 1.4, "outfeed_travel": self.belt_travel[1] / 2.6} if self.mode == "gapping" else {})},
                **({"surface_gap": self.pair_x[0] - self.pair_x[1] - .16} if self.mode == "gapping" else {}),
                "workpiece": parts["PART_01"], "workpieces": parts,
                "count": self.count, "goal": int(goal and not self.dropped_ids),
                "drives_off": int(not any(self.cmd.get(k) for k in self.binding["outputs"])),
                "violations": list(self.violations)}
