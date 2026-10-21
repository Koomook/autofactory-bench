"""Synthetic servo with following dynamics and braking.

Uses the Easy S geometry and stroke with synthetic following dynamics.
This model does not establish real equipment precision.
"""
from math import copysign


def clamp(x, low, high): return max(low, min(high, x))


class PrecisionDrive:
    def __init__(self, position_mm, calibration):
        self.x = float(position_mm)
        self.v = 0.0
        self.target = self.x
        self.c = calibration
        self.age_ms = float(calibration['settle_ms'])
        self.generation = 0
        self.enabled = False
        self.stopping = False

    def command(self, enable, stop, target):
        if enable and not stop and (not self.enabled or abs(target-self.target) > .01):
            self.target = float(target)
            self.generation += 1
            self.age_ms = 0.0
        self.enabled, self.stopping = bool(enable), bool(stop)

    def step(self, dt):
        before_v = self.v
        if self.enabled and not self.stopping:
            wn, zeta = self.c['natural_frequency_rad_s'], self.c['damping_ratio']
            acceleration = clamp(wn*wn*(self.target-self.x) - 2*zeta*wn*self.v,
                                 -self.c['acceleration_mm_s2'], self.c['acceleration_mm_s2'])
            self.v = clamp(self.v+acceleration*dt, -self.c['speed_mm_s'], self.c['speed_mm_s'])
        else:
            self.v = copysign(max(0.0, abs(self.v)-self.c['braking_mm_s2']*dt), self.v)
        # Trapezoidal integration: never snap actual position to the target.
        self.x += (before_v+self.v)*dt*.5
        good = abs(self.x-self.target) <= self.c['position_window_mm'] and abs(self.v) <= self.c['velocity_window_mm_s']
        self.age_ms = self.age_ms+dt*1000 if good and not self.stopping else 0.0

    @property
    def settled(self): return self.age_ms >= self.c['settle_ms']-1e-7

    def observation(self):
        quantum = self.c['position_quantum_mm']
        return dict(position_word=round(self.x/quantum), velocity_word=round(self.v),
                    busy=int(abs(self.v)>.1 if self.stopping else not self.settled and (self.enabled or abs(self.v)>.1)),
                    settled=int(self.settled), generation=self.generation)
