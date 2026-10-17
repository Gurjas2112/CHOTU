"""Adaptive suction ("Adaptive Suction for Power Saving" - spec sheet feature 4).

The Bergmann tornado motor dominates the power budget, so it runs in ECO
mode on clean floor and ramps to BOOST when the camera reports debris
("suck" detections) ahead of the nozzle.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SuctionProfile:
    off: float = 0.0
    eco: float = 0.55
    boost: float = 1.0
    ramp_per_s: float = 2.5
    boost_hold_s: float = 1.2


class AdaptiveSuction:
    def __init__(self, profile: SuctionProfile = SuctionProfile()):
        self.p = profile
        self.duty = 0.0
        self._boost_until = -1.0
        self.mode = "OFF"

    def update(self, t: float, dt: float, cleaning: bool, debris_ahead: int) -> float:
        if not cleaning:
            target, self.mode = self.p.off, "OFF"
        else:
            if debris_ahead > 0:
                self._boost_until = t + self.p.boost_hold_s
            if t < self._boost_until:
                target, self.mode = self.p.boost, "BOOST"
            else:
                target, self.mode = self.p.eco, "ECO"
        step = self.p.ramp_per_s * dt
        self.duty += max(-step, min(step, target - self.duty))
        return self.duty
