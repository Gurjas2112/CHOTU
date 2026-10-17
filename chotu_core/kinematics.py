"""Differential-drive kinematics and encoder + gyro odometry."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple


def wrap_angle(a: float) -> float:
    """Wrap an angle to (-pi, pi]."""
    return math.atan2(math.sin(a), math.cos(a))


@dataclass
class Pose2D:
    x: float = 0.0
    y: float = 0.0
    theta: float = 0.0

    def copy(self) -> "Pose2D":
        return Pose2D(self.x, self.y, self.theta)

    def distance_to(self, x: float, y: float) -> float:
        return math.hypot(x - self.x, y - self.y)


class DiffDrive:
    def __init__(self, wheel_base: float, wheel_radius: float, ticks_per_rev: int):
        self.wheel_base = wheel_base
        self.wheel_radius = wheel_radius
        self.ticks_per_rev = ticks_per_rev
        self.metres_per_tick = 2 * math.pi * wheel_radius / ticks_per_rev

    def twist_to_wheels(self, v: float, w: float) -> Tuple[float, float]:
        half = self.wheel_base / 2.0
        return v - w * half, v + w * half

    def wheels_to_twist(self, v_left: float, v_right: float) -> Tuple[float, float]:
        return (v_left + v_right) / 2.0, (v_right - v_left) / self.wheel_base

    @staticmethod
    def integrate(pose: Pose2D, v: float, w: float, dt: float) -> Pose2D:
        """Exact arc integration of a unicycle model."""
        if abs(w) < 1e-6:
            return Pose2D(pose.x + v * dt * math.cos(pose.theta),
                          pose.y + v * dt * math.sin(pose.theta),
                          pose.theta)
        r = v / w
        th2 = pose.theta + w * dt
        return Pose2D(pose.x + r * (math.sin(th2) - math.sin(pose.theta)),
                      pose.y - r * (math.cos(th2) - math.cos(pose.theta)),
                      wrap_angle(th2))


class FusedOdometry:
    """Wheel-encoder odometry with MPU6050 gyro heading (complementary filter).

    The encoders on the BO motors are single-channel, so the wheel direction
    is taken from the sign of the commanded wheel speed (same as firmware).
    """

    def __init__(self, drive: DiffDrive, start: Pose2D, gyro_weight: float = 0.98):
        self.drive = drive
        self.pose = start.copy()
        self.gyro_weight = gyro_weight

    def update(self, d_ticks_left: int, d_ticks_right: int, gyro_z: float, dt: float) -> Pose2D:
        dl = d_ticks_left * self.drive.metres_per_tick
        dr = d_ticks_right * self.drive.metres_per_tick
        ds = (dl + dr) / 2.0
        dth_enc = (dr - dl) / self.drive.wheel_base
        dth = self.gyro_weight * gyro_z * dt + (1 - self.gyro_weight) * dth_enc
        mid = self.pose.theta + dth / 2.0
        self.pose = Pose2D(self.pose.x + ds * math.cos(mid),
                           self.pose.y + ds * math.sin(mid),
                           wrap_angle(self.pose.theta + dth))
        return self.pose

    def reset(self, pose: Pose2D) -> None:
        self.pose = pose.copy()
