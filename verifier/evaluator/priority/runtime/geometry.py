"""Unchanged position and bounded-step helpers for material mechanics."""

def approach(value, target, delta):
    return min(target,value+delta) if value < target else max(target,value-delta)

def pose(pos, size=None, yaw=0):
    return dict(pos=list(pos), yaw=yaw, **({'size':size} if size else {}))
