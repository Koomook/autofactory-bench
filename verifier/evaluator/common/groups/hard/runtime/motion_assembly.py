"""Rigid mounts for reused Easy mechanisms; no new mesh or stroke geometry.

Opt-in scene.moving_assembly only. Ports reproduce the existing Easy renderer's
moving groups. All descendants (including sensors) inherit the complete pose.
"""
from __future__ import annotations

import math


def qmul(a, b):
    x, y, z, w = a
    X, Y, Z, W = b
    return [w*X+x*W+y*Z-z*Y, w*Y-x*Z+y*W+z*X,
            w*Z+x*Y-y*X+z*W, w*W-x*X-y*Y-z*Z]


def quat(euler):
    x, y, z = (v/2 for v in euler)
    return qmul(qmul([math.sin(x), 0, 0, math.cos(x)],
                     [0, math.sin(y), 0, math.cos(y)]),
                [0, 0, math.sin(z), math.cos(z)])


def rotate(q, v):
    return qmul(qmul(q, [*v, 0]), [-q[0], -q[1], -q[2], q[3]])[:3]


def combine(a, b):
    return ([x+y for x, y in zip(a[0], rotate(a[1], b[0]))], qmul(a[1], b[1]))


def port(device, name, s):
    w, h, d = device['size']
    p, r = [0, 0, 0], [0, 0, 0]
    if name == 'servo_carriage':
        p = [(s-.5)*(w-.3), h*.38 + max(.09, h*.36) + .03, 0]
    elif name == 'lift_deck':
        p = [0, -h/2+.1+s*(h-.2)+.035, 0]
    elif name == 'slide_carriage':
        p = [0, -h*.27+s*h*.54+.02, d*.64]
    elif name == 'fork_carriage':
        p = [0, -.0525, -d/2+.06-s*.18]
    elif name == 'turntable_top':
        p, r = [0, h/2, 0], [0, -s*math.pi/3, 0]
    elif name == 'robot_wrist':
        swing, elbow = -.9+1.8*s, -.6+.9*s
        q = qmul(quat([0, swing, 0]), quat([0, 0, elbow]))
        local = rotate(q, [.66, -.06, 0])
        return ([local[0], .94+local[1], local[2]], q)
    elif name == 'press_ram':
        p = [0, -h*.18-.06-s*h*.72, 0]
    elif name == 'cylinder_plate':
        p = [0, 0, -d*.475-s*d*.75]
    elif name != 'body':
        raise ValueError(f'Unknown Easy mount port: {name}')
    return p, quat(r)


def resolve(scene, states):
    """Resolve a mount DAG independently of declaration order, rejecting cycles."""
    devices = {d['id']: d for d in scene['devices']}
    result, visiting = {}, set()

    def one(name):
        if name in result:
            return result[name]
        if name in visiting:
            raise ValueError(f'Cyclic Easy attachment: {name}')
        visiting.add(name)
        d = devices[name]
        mount = d.get('assembly_mount')
        if mount:
            parent = devices[mount['parent']]
            parent_pose = one(parent['id'])
            moving = port(parent, mount['port'], states.get(parent['id'], 0))
            local = (mount['offset'], quat(mount.get('rotation', [0, 0, 0])))
            pose = combine(combine(parent_pose, moving), local)
        else:
            pose = (d['pos'], quat(d.get('assembly_rotation', [0, d.get('rot', 0), 0])))
        result[name] = pose
        visiting.remove(name)
        return pose

    for name in devices:
        one(name)
    return {name: {'pos': [round(v, 6) for v in p],
                   'quaternion': [round(v, 9) for v in q]}
            for name, (p, q) in result.items()}


def replay_view(task):
    """Frame the entire recorded travel, including a lifted mast's highest pose."""
    low, high = [math.inf]*3, [-math.inf]*3
    devices = {d['id']: d for d in task['devices']}
    for run in task['runs'].values():
        for frame in run['frames']:
            for name, pose in frame['world']['devices'].items():
                d = devices[name]
                size = list(d['size'])
                offset = [0, 0, 0]
                if d['ui'] == 'robot':
                    offset[1] = size[1]/2
                elif d['ui'] == 'press':
                    size[1] = max(.8, size[1])
                elif d['ui'] == 'fork':
                    offset = [0, .05, -.37]; size = [.7, .34, .95]
                elif d['ui'] == 'door':
                    size[0] *= 1.8
                q = pose.get('quaternion', [0, 0, 0, 1])
                center = [a+b for a,b in zip(pose['pos'], rotate(q, offset))]
                axes = [rotate(q, [size[j]/2 if i == j else 0 for j in range(3)]) for i in range(3)]
                extents = [sum(abs(v[j]) for v in axes) for j in range(3)]
                for i in range(3):
                    low[i] = min(low[i], center[i]-extents[i])
                    high[i] = max(high[i], center[i]+extents[i])
    low[1] = min(0, low[1])
    radius = .5*max(math.hypot(high[0]-low[0], high[2]-low[2]), high[1]-low[1])
    return {'dist': max(2.8, radius/math.tan(math.radians(42)/2)*1.30),
            'target': [(a+b)/2 for a,b in zip(low, high)]}
