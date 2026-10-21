#!/usr/bin/env python3
"""Shared layer projecting both logical state and replay scenes from PlantSpec."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: a JSON object is required")
    return value


def dotted(value: dict[str, Any], path: str) -> Any:
    """Read a dotted path; fail immediately on a missing key as a specification error."""
    current: Any = value
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            raise ValueError(f"PlantSpec source not found: {path}")
        current = current[part]
    return current


def vector3(value: Any, field: str) -> list[float]:
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"{field}: an array of length 3 is required")
    return [float(item) for item in value]


@dataclass(frozen=True)
class PlantPackage:
    task_dir: Path
    task: dict[str, Any]
    plant: dict[str, Any]
    binding: dict[str, Any]
    calibration: dict[str, Any]
    requirement: dict[str, Any]
    oracle: dict[str, Any]

    @classmethod
    def load(cls, task_dir: Path) -> "PlantPackage":
        task = read_object(task_dir / "task.json")
        return cls(
            task_dir=task_dir,
            task=task,
            plant=read_object(task_dir / str(task["plant"])),
            binding=read_object(task_dir / str(task["binding"])),
            calibration=read_object(task_dir / str(task["calibration"])),
            requirement=read_object(task_dir / str(task["requirement"])),
            oracle=read_object(task_dir / str(task["oracle"])),
        )

    def scene(self) -> "SceneProjector":
        return SceneProjector(self.plant, self.binding)


class SceneProjector:
    """Convert an execution frame to a canonical replay frame.

    Coordinate expressions and part-attachment rules belong only in PlantSpec.
    This projector is the sole conversion point so the renderer and logical
    plant do not independently reimplement coordinates.
    """

    def __init__(self, plant_spec: dict[str, Any], binding: dict[str, Any]):
        if plant_spec.get("schema_version") != "plant-spec/0.2":
            raise ValueError("Unsupported PlantSpec version")
        scene = plant_spec.get("scene")
        if not isinstance(scene, dict):
            raise ValueError("PlantSpec.scene is required")
        self.plant_spec = plant_spec
        self.binding = binding
        self.spec = scene
        self._validate()

    def _validate(self) -> None:
        declared = {str(item["id"]) for item in self.plant_spec["devices"]}
        visual_ids: set[str] = set()
        for device in self.spec.get("devices", []):
            device_id = str(device["id"])
            if device_id in visual_ids:
                raise ValueError(f"Duplicate scene device: {device_id}")
            visual_ids.add(device_id)
            vector3(device["pos"], f"scene.devices.{device_id}.pos")
            vector3(device["size"], f"scene.devices.{device_id}.size")
            if "source_device" in device and device["source_device"] not in declared:
                raise ValueError(f"Unknown source_device: {device['source_device']}")
            if "world_position" in device:
                self._validate_position(device["world_position"], device_id)
        for part in self.spec.get("workpieces", []):
            if "rotation" in part:
                self._validate_position(part["rotation"], f"{part['id']}.rotation")
            for owner, pose in part.get("owner_poses", {}).items():
                if "attach_to" in pose and pose["attach_to"] not in visual_ids:
                    raise ValueError(f"{part['id']}/{owner}: Unknown attach_to")
                if "position" in pose:
                    self._validate_position(pose["position"], f"{part['id']}/{owner}")
                if "offset" in pose:
                    vector3(pose["offset"], f"{part['id']}/{owner}.offset")
        part_ids = {str(item["id"]) for item in self.spec.get("workpieces", [])}
        mounted_pairs: set[frozenset[str]] = set()
        intentional_contact_pairs: set[frozenset[str]] = set()
        mounted_parent: dict[str, str] = {}
        for relation in self.spec.get("relations", []):
            kind = str(relation["type"])
            if kind == "mounted_on":
                child = str(relation["child"])
                parent = str(relation["parent"])
                if child not in (visual_ids | part_ids) or parent not in visual_ids or child == parent:
                    raise ValueError(f"Invalid mounted_on relation: {child} -> {parent}")
                if child in visual_ids:
                    mounted_pairs.add(frozenset((child, parent)))
                    mounted_parent[child] = parent
            elif kind == "works_at":
                child = str(relation["child"])
                parent = str(relation["parent"])
                if child not in visual_ids or parent not in visual_ids or child == parent:
                    raise ValueError(f"Invalid works_at relation: {child} -> {parent}")
                intentional_contact_pairs.add(frozenset((child, parent)))
            elif kind == "holds":
                device = str(relation["device"])
                part = str(relation["part"])
                if device not in visual_ids or part not in part_ids:
                    raise ValueError(f"Invalid holds relation: {device} -> {part}")
            elif kind == "delivers_to":
                child = str(relation["child"])
                parent = str(relation["parent"])
                if child not in visual_ids or parent not in visual_ids or child == parent:
                    raise ValueError(f"Invalid delivers_to relation: {child} -> {parent}")
                intentional_contact_pairs.add(frozenset((child, parent)))
            elif kind in {"supports", "secures"}:
                device = str(relation["device"])
                part = str(relation["part"])
                if device not in visual_ids or part not in part_ids:
                    raise ValueError(f"Invalid {kind} relation: {device} -> {part}")
            elif kind != "interlock":
                raise ValueError(f"Unsupported scene relation: {kind}")
        visual_devices = list(self.spec.get("devices", []))
        support_ids = {
            str(item["id"]) for item in visual_devices
            if str(item["ui"]) == "support_frame" or (item.get('grounded_support') and item['ui']=='fixture')
        }
        # An integrated assembly may combine a gantry with independently grounded
        # Easy bases. validate_scene_geometry checks each actual ground path.
        if any(item['ui']=='support_frame' for item in visual_devices) and self.spec.get("moving_assembly") != "easy-reuse/1":
            for item in visual_devices:
                if str(item["ui"]) in {"fixture", "support_frame", "sensor"}:
                    continue
                device_id = str(item["id"])
                current = device_id
                seen: set[str] = set()
                while current in mounted_parent and current not in seen:
                    seen.add(current)
                    current = mounted_parent[current]
                if current not in support_ids:
                    raise ValueError(
                        f"Moving device has no support-frame connection: {device_id}"
                    )

        def shares_mount_chain(first: str, second: str) -> bool:
            def is_ancestor(ancestor: str, child: str) -> bool:
                seen: set[str] = set()
                current = child
                while current in mounted_parent and current not in seen:
                    seen.add(current)
                    current = mounted_parent[current]
                    if current == ancestor:
                        return True
                return False

            return is_ancestor(first, second) or is_ancestor(second, first)

        def half_extents(device: dict[str, Any]) -> tuple[float, float, float]:
            """Return the device world-AABB half extent after Y-axis rotation."""
            if self.spec.get("moving_assembly") == "easy-reuse/1":
                from motion_assembly import rotate
                q = device["assembly_reference_quaternion"]
                axes = [rotate(q, [float(device['size'][j])/2 if i == j else 0 for j in range(3)]) for i in range(3)]
                return tuple(sum(abs(v[j]) for v in axes) for j in range(3))
            size_x, size_y, size_z = (float(value) for value in device["size"])
            rotation = float(device.get("rot", 0.0))
            cosine = abs(math.cos(rotation))
            sine = abs(math.sin(rotation))
            return (
                (cosine * size_x + sine * size_z) / 2.0,
                size_y / 2.0,
                (sine * size_x + cosine * size_z) / 2.0,
            )

        def collision_boxes(device):
            if self.spec.get('geometry_profile') == 'material-extension/8':
                # Initial physical pieces match the dedicated renderer. Empty
                # pocket/nip volumes are not solid bounding cuboids.
                v=device.get('visual_variant')
                pieces=None
                if v=='v8-carousel':
                    pieces=[([0,0,0],[1.24,.04,1.24]),([0,.035,0],[.36,.03,.36])]
                    for i in range(4):
                        x=.52*math.cos(i*math.pi/2);z=.52*math.sin(i*math.pi/2)
                        pieces.append(([x,.027,z],[.16,.014,.15] if i%2==0 else [.15,.014,.16]))
                        pieces.extend(([x,.054,z+k*.073],[.15,.04,.015]) if i%2==0 else ([x+k*.073,.054,z],[.015,.04,.15]) for k in (-1,1))
                elif v=='v8-receiver-nip':
                    pieces=[([0,-.027,0],[.054,.054,.26]),([0,.11,0],[.054,.054,.26])]
                    pieces.extend(([0,.07,z],[.07,.24,.05]) for z in (-.18,.18))
                if pieces is not None:
                    return [([a+b for a,b in zip(device['pos'],p)],[v/2 for v in size]) for p,size in pieces]
            if self.spec.get('geometry_profile') == 'pallet-locate/1' and device['id'] == 'STOPPER':
                # Actual fork housing and raised blade, not its empty middle.
                pieces = [([s*.06125, -.14*.685, 0], [.0575,.14*.83,.072]) for s in (-1,1)]
                pieces += [([0,-.14*1.125,0],[.18,.14*.05,.072]),
                           ([0,.14*.20,0],[.055,.14*.58,.10])]
                return [([a+b for a,b in zip(device['pos'], p)], [v/2 for v in size]) for p,size in pieces]
            if device.get('visual_variant') == 'material-pallet-locator':
                # The center-opening locator is not a solid bounding cuboid.
                # Match the fixed bodies and home plate in PalletLocatorAssembly;
                # moving plate/pin/support clearances are checked in its task audit.
                pieces = [([0, -.01, 0], [.36, .02, .26]),
                          ([0, .065, 0], [.10, .13, .10]),
                          ([0, .21, 0], [.34, .03, .24])]
                pieces += [([x, .065, z], [.038, .13, .038]) for x in (-.135,.135) for z in (-.085,.085)]
                return [([a+b for a,b in zip(device['pos'], p)], [v/2 for v in size]) for p,size in pieces]
            if self.spec.get("moving_assembly") != "easy-reuse/1":
                return [(device['pos'], half_extents(device))]
            from motion_assembly import rotate
            q = device['assembly_reference_quaternion']
            w, h, d = device['size']
            pieces = [([0, 0, 0], [w, h, d])]
            if device['ui'] == 'robot':
                # Robot.pos is its base, whereas the other Easy profiles use
                # their bounding centre. Its published size stays unchanged.
                pieces = [([0, h/2, 0], [w, h, d])]
            elif device['ui'] == 'gripper':
                # Easy housing y=+/- .08; fingers span -.26 .. -.06.
                pieces = [([0, -.09, 0], [w, .34, d])]
            elif device['ui'] == 'support_frame':
                # A gantry's empty opening is not solid material.
                edge = max(.08, min(.14, w*.09))
                pieces = [([side*(w/2-edge/2), 0, 0], [edge, h, edge]) for side in (-1, 1)]
                pieces += [([0, side*(h/2-edge/2), 0], [w, edge, max(edge, d*.72)]) for side in (-1, 1)]
            boxes = []
            for center, size in pieces:
                position = [a+b for a,b in zip(device['pos'], rotate(q, center))]
                axes = [rotate(q, [size[j]/2 if i == j else 0 for j in range(3)]) for i in range(3)]
                boxes.append((position, [sum(abs(v[j]) for v in axes) for j in range(3)]))
            return boxes

        device_boxes = {item['id']: collision_boxes(item) for item in visual_devices}
        contact_epsilon = 1e-8 if self.spec.get('moving_assembly') == 'easy-reuse/1' or self.spec.get('geometry_profile') == 'material-extension/8' else 0.0
        for index, first in enumerate(visual_devices):
            for second in visual_devices[index + 1:]:
                pair = frozenset((str(first["id"]), str(second["id"])))
                if pair in mounted_pairs or pair in intentional_contact_pairs or shares_mount_chain(
                    str(first["id"]), str(second["id"]),
                ):
                    continue
                if any(all(abs(fp[axis]-sp[axis]) < fe[axis]+se[axis]-contact_epsilon for axis in range(3))
                       for fp,fe in device_boxes[first['id']] for sp,se in device_boxes[second['id']]):
                    raise ValueError(
                        f"Unrelated scene devices overlap: {first['id']} / {second['id']}"
                    )
        for signal in self.spec.get("signals", []):
            address = self.address(str(signal["address_ref"]))
            if not isinstance(address, str) or not address:
                raise ValueError("Scene signal address must be a string")

    @staticmethod
    def _validate_position(spec: dict[str, Any], field: str) -> None:
        vector3(spec["origin"], f"{field}.origin")
        for term in spec.get("terms", []):
            if not isinstance(term.get("source"), str):
                raise ValueError(f"{field}.terms.source is required")
            vector3(term["vector"], f"{field}.terms.vector")
        orbit = spec.get("orbit")
        if orbit is not None:
            if not isinstance(orbit.get("source"), str):
                raise ValueError(f"{field}.orbit.source is required")
            float(orbit["radius"])
            float(orbit["start_degrees"])
            float(orbit["sweep_degrees"])

    def address(self, reference: str | None) -> str | None:
        if reference is None:
            return None
        return str(dotted(self.binding, reference))

    @staticmethod
    def _position(spec: dict[str, Any], frame: dict[str, Any]) -> list[float]:
        result = vector3(spec["origin"], "position.origin")
        for term in spec.get("terms", []):
            value = float(dotted(frame, str(term["source"])))
            scale = float(term.get("scale", 1.0))
            vector = vector3(term["vector"], "position.term.vector")
            result = [a + value * scale * b for a, b in zip(result, vector)]
        orbit = spec.get("orbit")
        if orbit is not None:
            value = float(dotted(frame, str(orbit["source"])))
            angle = math.radians(
                float(orbit["start_degrees"]) + value * float(orbit["sweep_degrees"])
            )
            radius = float(orbit["radius"])
            result[0] += math.cos(angle) * radius
            result[2] += math.sin(angle) * radius
        return [round(value, 6) for value in result]

    def device_definitions(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for item in self.spec.get("devices", []):
            result.append({
                "id": str(item["id"]),
                # Fixed housings and mounts are visual structures, not 0%-position actuators.
                "kind": "static" if item.get("visual_only", False) or str(item["ui"]) in {"fixture", "support_frame"} else "act",
                "ui": str(item["ui"]),
                "drive": self.address(item.get("drive_ref")),
                "at_max": self.address(item.get("at_max_ref")),
                "at_min": self.address(item.get("at_min_ref")),
                "pos": vector3(item["pos"], f"{item['id']}.pos"),
                "size": vector3(item["size"], f"{item['id']}.size"),
                "rot": float(item.get("rot", 0.0)),
                "dynamic_world_position": "world_position" in item,
                **({"dynamic_world_rotation": True} if "world_yaw_source" in item else {}),
                **({"motion_axis": item["motion_axis"]} if "motion_axis" in item else {}),
                **({"visual_variant": item["visual_variant"]} if "visual_variant" in item else {}),
                **({"web_geometry": item["web_geometry"]} if "web_geometry" in item else {}),
                **({"state_display": item["state_display"]} if "state_display" in item else {}),
                **({"actuator_ref": item["actuator_ref"]} if "actuator_ref" in item else {}),
                **({"rod_base_extension": item["rod_base_extension"]} if "rod_base_extension" in item else {}),
                **({"press_max_travel": item["press_max_travel"]} if "press_max_travel" in item else {}),
                **({"sensor_visual": item["sensor_visual"]} if "sensor_visual" in item else {}),
                **({"sensor_beam_length": item["sensor_beam_length"]} if "sensor_beam_length" in item else {}),
                **({"sensor_target": vector3(item["sensor_target"], f"{item['id']}.sensor_target")} if "sensor_target" in item else {}),
                **({"sensor_receiver": item["sensor_receiver"]} if "sensor_receiver" in item else {}),
                **({"sensor_purpose": item["sensor_purpose"]} if "sensor_purpose" in item else {}),
            })
        return result

    def io_labels(self) -> dict[str, str]:
        return {
            str(self.address(reference)): str(label)
            for reference, label in self.spec.get("io_labels", {}).items()
        }

    def observed(self) -> list[str]:
        return [self.address(str(ref)) for ref in self.spec.get("observed_refs", [])]

    def relations(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self.spec.get("relations", [])]

    def project_frame(self, frame: dict[str, Any]) -> dict[str, Any]:
        y: dict[str, int] = {}
        for signal in self.spec.get("signals", []):
            address = self.address(str(signal["address_ref"]))
            y[str(address)] = int(bool(dotted(frame, str(signal["source"]))))

        state: dict[str, float] = {}
        for item in self.spec.get("devices", []):
            if "state_source" in item:
                value = float(dotted(frame, str(item["state_source"])))
            elif item.get("ui") == "sensor" and item.get("at_max_ref"):
                address = self.address(str(item["at_max_ref"]))
                value = float(bool(frame["input_image"].get(str(address), 0)))
            else:
                value = 0.0
            state[str(item["id"])] = value
        world_devices: dict[str, Any] = {}
        positions: dict[str, list[float]] = {}
        for item in self.spec.get("devices", []):
            device_id = str(item["id"])
            position = (
                self._position(item["world_position"], frame)
                if "world_position" in item else vector3(item["pos"], f"{device_id}.pos")
            )
            positions[device_id] = position
            world_devices[device_id] = {"pos": position}
            if "world_yaw_source" in item:
                yaw = float(dotted(frame, item['world_yaw_source']))
                world_devices[device_id]['quaternion'] = [0, math.sin(yaw / 2), 0, math.cos(yaw / 2)]

        # Rigid Easy attachments are opt-in; existing scene projection is unchanged.
        if self.spec.get("moving_assembly") == "easy-reuse/1":
            from motion_assembly import resolve
            pose_scene = self.spec
            if self.spec.get("geometry_profile") == "motion-medium/0.7":
                pose_scene = {**self.spec, "devices": [{**d, "pos": positions[d["id"]]} for d in self.spec["devices"]]}
            world_devices = resolve(pose_scene, state)
            positions = {name: pose["pos"] for name, pose in world_devices.items()}

        parts: dict[str, Any] = {}
        for item in self.spec.get("workpieces", []):
            owner = str(dotted(frame, str(item["owner_source"])))
            pose = item.get("owner_poses", {}).get(owner)
            if pose is None:
                raise ValueError(f"{item['id']}: Owner pose is missing: {owner}")
            held_by = pose.get("held_by")
            if "attach_to" in pose:
                anchor = positions[str(pose["attach_to"])]
                offset = vector3(pose.get("offset", [0, 0, 0]), "workpiece.offset")
                position = [round(a + b, 6) for a, b in zip(anchor, offset)]
            else:
                position = self._position(pose["position"], frame)
            raw_status = (
                str(dotted(frame, str(item["status_source"])))
                if item.get("status_source") else "idle"
            )
            status = "held" if held_by else "dropped" if raw_status == "dropped" else "idle"
            parts[str(item["id"])] = {
                "pos": position,
                "owner": owner,
                "held_by": held_by,
                "status": status,
                **({"color": str(item["color"])} if "color" in item else {}),
                **({"color": str(dotted(frame,item['color_source']))} if item.get('color_source') else {}),
                **({"render_variant": item['render_variant']} if item.get('render_variant') else {}),
                **({"material_dimensions": vector3(item['material_dimensions'], 'material_dimensions')} if self.spec.get('geometry_profile') in ('material-redesign/6','material-extension/7','material-extension/8') and item.get('material_dimensions') else {}),
                **({"motion_dimensions": item['motion_dimensions']} if self.spec.get('geometry_profile') == 'motion-function/0.5' and item.get('motion_dimensions') else {}),
                **({"visible": bool(dotted(frame, item['visible_source']))} if self.spec.get('geometry_profile') in ('motion-function/0.5','material-extension/7','material-extension/8') and item.get('visible_source') else {}),
                **({"rotation": self._position(item["rotation"], frame)} if "rotation" in item else {}),
                **({"orientation_marker": True} if item.get("orientation_marker") else {}),
                **({"machining_depths": list(dotted(frame,item['machining_depths_source']))} if item.get('machining_depths_source') else {}),
            }

        velocity_source = self.spec.get("velocity_source")
        velocity = float(dotted(frame, str(velocity_source))) if velocity_source else 0.0
        return {
            "k": int(frame["scan"]),
            "y": y,
            "x": {name: int(bool(value)) for name, value in frame["input_image"].items()},
            **({'words': {name: int(value) for name, value in frame['input_image'].items() if name.startswith('D')}} if self.spec.get('geometry_profile') in ('material-web-index/1','material-redesign/6','material-extension/8') else {}),
            "s": state,
            "v": velocity,
            "world": {
                "devices": world_devices,
                "parts": parts,
                "events": [str(event["type"]) for event in frame["events"]],
                **({"motion_hard": frame["plant"]["motion_hard"]} if self.spec.get("geometry_profile")=="motion-hard/1" else {}),
                **({"precision": frame["plant"]["precision"]} if self.spec.get("geometry_profile")=="motion-precision/0.6" else {}),
                **({"motion_medium": frame["plant"]["motion_medium"]} if self.spec.get("geometry_profile")=="motion-medium/0.7" else {}),
                **({"motion_easy": frame["plant"]["motion_easy"]} if self.spec.get("geometry_profile")=="motion-easy/0.3" else {}),
                **({"motion_easy_unit": frame["plant"]["motion_easy_unit"]} if self.spec.get("geometry_profile")=="motion-easy/0.4" else {}),
                **({'web_index': {k: frame['plant'][k] for k in ('carriage_mm','web_mm','delivered_mm','request_mm','grip','receiver')}} if self.spec.get('geometry_profile')=='material-web-index/1' else {}),
                **({'coordination': frame['plant']['coordination']} if self.spec.get('geometry_profile')=='material-coordination/1' else {}),
                **({'tending': {
                    'cells': {name: {'token': cell['token'], 'status': 'Machining' if cell['busy'] else 'Machining complete' if cell['done'] else 'Ready' if cell['token'] else 'Waiting'} for name, cell in frame['plant']['cells'].items()},
                    'robot': next((p['token'] for p in frame['plant']['parts'].values() if p['owner']=='tool'),0),
                    'buffer': next((p['token'] for p in frame['plant']['parts'].values() if p['owner']=='buffer'),0),
                    'resultToken': frame['plant']['inspection']['token'],
                    'resultValid': frame['plant']['inspection']['valid'],
                    'measuring': frame['plant']['inspection']['busy'],
                    'depths': frame['plant']['inspection']['depths'],
                    'delivered': len(frame['plant']['accepted']),
                }} if self.spec.get('geometry_profile')=='dual-machine-tending/1' else {}),
                **({'quality': dotted(frame, self.spec['quality_source'])} if self.spec.get('quality_source') else {}),
                **({'inspection': {
                    'height_mm': None if frame['plant']['probe']['measured_height'] is None else round(frame['plant']['probe']['measured_height']*1000,3),
                    'contact': frame['plant']['probe']['contact'],
                    'phase': frame['plant']['probe']['phase'],
                    'good': frame['plant']['probe']['good'],
                    'done': frame['plant']['probe']['done'],
                }} if self.spec.get('geometry_profile')=='pallet-locate/1' and 'probe' in frame['plant'] else {}),
            },
        }
