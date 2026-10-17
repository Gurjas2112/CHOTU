"""Reactive safety layer: runs every control tick *after* the planner.

Inputs are the 3 x HC-SR04 + VL53L0X ranges (measured from the chassis rim),
2 x IR cliff sensors and the SW-420 vibration/bump switch.  It can only make
a command safer (slow down, stop, refuse forward motion) - never faster.
The same rules are mirrored in the ESP32 firmware (``safety.h``) so the base
stops even if the Pi crashes.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class RangeReading:
    angle: float        # rad, relative to robot heading
    distance: float     # m, from chassis edge
    max_range: float
    source: str = "us"  # us | tof

    @property
    def valid_hit(self) -> bool:
        return self.distance < self.max_range * 0.98


@dataclass
class SafetyStatus:
    level: str          # clear | slow | blocked | cliff | bump
    min_front: float


class ReactiveSafety:
    def __init__(self, stop_distance: float, slow_distance: float,
                 robot_radius: float = 0.17, front_half_angle: float = math.radians(60)):
        self.stop = stop_distance
        self.slow = slow_distance
        self.radius = robot_radius
        self.front = front_half_angle

    def forward_clearance(self, r: RangeReading) -> float:
        """Distance the round chassis can drive straight before touching the echo.

        The echo point sits at (R + d)(cos a, sin a) in the robot frame.  If its
        lateral offset is outside the swept corridor (|y| >= R) driving
        straight never touches it - e.g. a wall parallel to the lane seen by
        the 35° side sensor - so it does not block forward motion.
        """
        if not r.valid_hit or abs(r.angle) > self.front:
            return math.inf
        R = self.radius
        fx = (R + r.distance) * math.cos(r.angle)
        fy = (R + r.distance) * math.sin(r.angle)
        if abs(fy) >= R:
            return math.inf
        return max(0.0, fx - math.sqrt(R * R - fy * fy))

    def front_clearance(self, readings: List[RangeReading]) -> float:
        d = [self.forward_clearance(r) for r in readings]
        return min(d) if d else math.inf

    def filter(self, v: float, w: float, readings: List[RangeReading],
               cliff: bool = False, bump: bool = False) -> Tuple[float, float, SafetyStatus]:
        front = self.front_clearance(readings)
        if cliff:
            return min(v, 0.0), w, SafetyStatus("cliff", front)
        if bump and v > 0:
            return 0.0, w, SafetyStatus("bump", front)
        if v > 0 and front < self.stop:
            return 0.0, w, SafetyStatus("blocked", front)
        if v > 0 and front < self.slow:
            scale = max(0.5, (front - self.stop) / (self.slow - self.stop))
            return v * scale, w, SafetyStatus("slow", front)
        return v, w, SafetyStatus("clear", front)

    @staticmethod
    def escape_direction(readings: List[RangeReading]) -> int:
        """VFH-lite: +1 turn left (CCW), -1 turn right, based on free space."""
        left = sum(min(r.distance, r.max_range) for r in readings if r.angle > 0.05)
        right = sum(min(r.distance, r.max_range) for r in readings if r.angle < -0.05)
        return 1 if left >= right else -1
