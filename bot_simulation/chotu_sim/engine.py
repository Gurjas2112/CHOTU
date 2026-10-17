"""Physics + sensor simulation that drives the *real* ``chotu_core`` brain.

Each tick (20 Hz):
  1. ground-truth sensors -> noisy HC-SR04 / VL53L0X / gyro / encoder readings
  2. encoder + gyro odometry (FusedOdometry, same as the robot)
  3. CleaningMission.step(observation) -> command
  4. motor first-order dynamics, collision handling, debris pick-up, battery
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from chotu_core.autonomy import CleaningMission, Command, Observation
from chotu_core.battery_model import BatteryModel
from chotu_core.config import GARBAGE_TYPES, PROTOTYPE_BOM_INR, ChotuConfig, DEFAULT_CONFIG
from chotu_core.coverage_planner import CoverageTracker
from chotu_core.kinematics import DiffDrive, FusedOdometry, Pose2D, wrap_angle
from chotu_core.mission_fsm import MissionState
from chotu_core.obstacle_avoidance import RangeReading
from chotu_core.occupancy_grid import dilate
from chotu_core.perception import MockDetector
from chotu_core.scoring import RunResult, ScoreCard, score

from .world import RASTER_RES, Room, generate_room


@dataclass
class TickRecord:
    t: float
    true_pose: Pose2D
    est_pose: Pose2D
    cmd: Command
    soc: float
    power_w: float
    coverage: float
    collected_g: float
    rays: List[tuple]


@dataclass
class SimResult:
    seed: int
    docked: bool
    elapsed_s: float
    coverage: float
    collisions: int
    cable_incidents: int
    recoveries: int
    replans: int
    energy_wh: float
    avg_power_w: float
    eco_energy_saving_pct: float
    efficiency_by_type: Dict[str, float]
    collected_g: Dict[str, float]
    spawned_g: Dict[str, float]
    final_dock_error_m: float
    score: Dict = field(default_factory=dict)


def point_segment_dist(px, py, ax, ay, bx, by) -> float:
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


class Simulation:
    def __init__(self, seed: int = 2025, cfg: ChotuConfig = DEFAULT_CONFIG,
                 vision: bool = True, noise: bool = True, room: Optional[Room] = None):
        self.cfg = cfg
        self.seed = seed
        self.rng = random.Random(seed * 7919 + 1)
        self.room = room or generate_room(seed, cfg)
        self.vision = vision
        self.noise = noise
        self.dt = 1.0 / cfg.mission.control_rate_hz
        r = cfg.robot
        self.drive = DiffDrive(r.wheel_base, r.wheel_radius, r.encoder_ticks_per_rev)
        self.true_pose = Pose2D(cfg.room.dock_x, cfg.room.dock_y, cfg.room.dock_theta)
        self.odom = FusedOdometry(self.drive, self.true_pose)
        self.mission = CleaningMission(cfg)
        self.battery = BatteryModel(cfg.power)
        self.detector = MockDetector(cfg.sensors.camera_fov_deg, cfg.sensors.camera_range,
                                     rng=random.Random(seed + 99))
        self.v_act = 0.0
        self.w_act = 0.0
        self._tick_acc = [0.0, 0.0]
        self._gyro_bias = self.rng.gauss(0, 0.0004) if noise else 0.0
        self.t = 0.0
        self.collisions = 0
        self.cable_incidents = 0
        self._in_collision = False
        self._on_cable = False
        self.bump = False
        self.trail: List[tuple] = []
        self.history: List[TickRecord] = []
        self.last_cmd = Command()
        self.last_rays: List[tuple] = []
        self._eco_ref_wh = 0.0       # what constant 100 % suction would have used
        res = cfg.mission.grid_resolution
        self.truth_cov = CoverageTracker(self.room.width, self.room.height, res, r.cleaning_width)
        self.cleanable = self._cleanable_mask(res)
        self.done = False
        self.mission.start(self.t)

    # ------------------------------------------------------------ helpers
    def _cleanable_mask(self, res: float) -> np.ndarray:
        nx, ny = self.truth_cov.nx, self.truth_cov.ny
        xs = ((np.arange(nx) + 0.5) * res / RASTER_RES).astype(int)
        ys = ((np.arange(ny) + 0.5) * res / RASTER_RES).astype(int)
        xs = np.clip(xs, 0, self.room.raster.shape[1] - 1)
        ys = np.clip(ys, 0, self.room.raster.shape[0] - 1)
        d = self.room.dist_m[np.ix_(ys, xs)]
        centre_free = d >= self.cfg.robot.radius + 0.01
        half = int(round(self.cfg.robot.cleaning_width / 2 / res))
        return dilate(centre_free, half) & (d > 0.0)

    def _to_odom(self, x: float, y: float):
        """Ground-truth world point -> robot odometry frame."""
        dth = self.odom.pose.theta - self.true_pose.theta
        dx, dy = x - self.true_pose.x, y - self.true_pose.y
        c, s = math.cos(dth), math.sin(dth)
        return self.odom.pose.x + c * dx - s * dy, self.odom.pose.y + s * dx + c * dy

    def _sense(self) -> List[RangeReading]:
        sc, r = self.cfg.sensors, self.cfg.robot.radius
        p = self.true_pose
        readings, rays = [], []
        for ang_deg in sc.ultrasonic_angles_deg:
            base = p.theta + math.radians(ang_deg)
            ox, oy = p.x + r * math.cos(base), p.y + r * math.sin(base)
            half = math.radians(sc.ultrasonic_cone_deg) / 2
            d = min(self.room.raycast(ox, oy, base + k * half / 2, sc.ultrasonic_max) for k in (-2, -1, 0, 1, 2))
            if self.noise and d < sc.ultrasonic_max:
                d = max(sc.ultrasonic_min, d + self.rng.gauss(0, sc.ultrasonic_noise))
                if self.rng.random() < 0.01:
                    d = sc.ultrasonic_max  # missed echo
            readings.append(RangeReading(math.radians(ang_deg), d, sc.ultrasonic_max, "us"))
            rays.append((ox, oy, base, d, sc.ultrasonic_max, "us"))
        base = p.theta + math.radians(sc.tof_angle_deg)
        ox, oy = p.x + r * math.cos(base), p.y + r * math.sin(base)
        d = self.room.raycast(ox, oy, base, sc.tof_max)
        if self.noise and d < sc.tof_max:
            d = max(0.0, d + self.rng.gauss(0, sc.tof_noise))
        readings.append(RangeReading(math.radians(sc.tof_angle_deg), d, sc.tof_max, "tof"))
        rays.append((ox, oy, base, d, sc.tof_max, "tof"))
        self.last_rays = rays
        return readings

    def _camera(self):
        if not self.vision or int(round(self.t / self.dt)) % 4:   # 5 FPS YOLO on the Pi
            return []
        objs = [(g.kind, g.x, g.y, 0.03) for g in self.room.garbage if not g.collected]
        for c in self.room.cables:
            for (ax, ay), (bx, by) in zip(c.points, c.points[1:]):
                for k in range(3):
                    f = k / 3
                    objs.append(("power_cable", ax + f * (bx - ax), ay + f * (by - ay), 0.07))
        dets = self.detector.detect(self.true_pose, objs)
        for d in dets:   # report in the odometry frame the robot actually uses
            d.x, d.y = self._to_odom(d.x, d.y)
        return dets

    # ------------------------------------------------------------ main loop
    def step(self) -> bool:
        if self.done:
            return False
        ranges = self._sense()
        beacon = None
        dock_x, dock_y = self.cfg.room.dock_x, self.cfg.room.dock_y
        if math.hypot(self.true_pose.x - dock_x, self.true_pose.y - dock_y) < 0.7:
            beacon = self._to_odom(dock_x, dock_y)
        obs = Observation(self.t, self.odom.pose.copy(), ranges, cliff=False, bump=self.bump,
                          detections=self._camera(), battery_soc=self.battery.soc, dock_beacon=beacon)
        cmd = self.mission.step(obs)
        self.last_cmd = cmd
        self._physics(cmd)
        self._debris(cmd)
        sample = self.battery.step(self.dt, abs(self.v_act), self.cfg.robot.max_linear, cmd.suction, cmd.brush > 0)
        self._eco_ref_wh += self.battery.power(abs(self.v_act), self.cfg.robot.max_linear,
                                               1.0 if cmd.suction > 0.05 else 0.0, cmd.brush > 0) * self.dt / 3600
        if self.mission.state != MissionState.DOCKED and self.mission.state != MissionState.IDLE:
            self.truth_cov.mark(self.true_pose.x, self.true_pose.y) if cmd.suction > 0.05 else None
        self.t += self.dt
        if int(self.t / self.dt) % 2 == 0:
            self.trail.append((self.true_pose.x, self.true_pose.y))
        self.history.append(TickRecord(self.t, self.true_pose.copy(), self.odom.pose.copy(), cmd,
                                       self.battery.soc, sample.power_w,
                                       self.truth_cov.coverage_ratio(self.cleanable),
                                       sum(self.room.collected_mass().values()), list(self.last_rays)))
        if self.mission.state == MissionState.DOCKED or self.t > self.cfg.mission.time_budget_s + 30:
            self.done = True
        return not self.done

    def _physics(self, cmd: Command) -> None:
        tau = 0.12
        k = min(1.0, self.dt / tau)
        self.v_act += (cmd.v - self.v_act) * k
        self.w_act += (cmd.w - self.w_act) * k
        v, w = self.v_act, self.w_act
        if self.noise:
            v *= 1.0 + self.rng.gauss(0, 0.01)
            w *= 1.0 + self.rng.gauss(0, 0.01)
        new = DiffDrive.integrate(self.true_pose, v, w, self.dt)
        r = self.cfg.robot.radius
        collided = self.room.dist_at(new.x, new.y) < r
        if collided:
            new = Pose2D(self.true_pose.x, self.true_pose.y, new.theta)
            if not self._in_collision:      # count each contact episode once
                self.collisions += 1
                self._in_collision = True
        elif self.room.dist_at(new.x, new.y) > r + 0.03:
            self._in_collision = False
        self.bump = collided
        # encoders see the wheels turning (they slip if blocked)
        vl, vr = self.drive.twist_to_wheels(v if not collided else 0.1 * v, w)
        ticks = []
        for i, wv in enumerate((vl, vr)):
            self._tick_acc[i] += abs(wv) * self.dt / self.drive.metres_per_tick
            n = int(self._tick_acc[i])
            self._tick_acc[i] -= n
            ticks.append(n if wv >= 0 else -n)
        dth_true = wrap_angle(new.theta - self.true_pose.theta)
        gyro = dth_true / self.dt + (self._gyro_bias + self.rng.gauss(0, 0.004) if self.noise else 0.0)
        self.true_pose = new
        self.odom.update(ticks[0], ticks[1], gyro, self.dt)
        # cable incidents (brush tangles when driving over a power cable)
        on_cable = any(point_segment_dist(new.x, new.y, ax, ay, bx, by) < r * 0.6
                       for c in self.room.cables for (ax, ay), (bx, by) in zip(c.points, c.points[1:]))
        if on_cable and not self._on_cable:
            self.cable_incidents += 1
            self.mission._event(self.t, "warn", "Brush tangled on power cable!")
        self._on_cable = on_cable

    def _debris(self, cmd: Command) -> None:
        half = self.cfg.robot.cleaning_width / 2
        p = self.true_pose
        for g in self.room.garbage:
            if g.collected:
                continue
            inside = math.hypot(g.x - p.x, g.y - p.y) < half
            if inside and not g.inside and cmd.suction > 0.05:
                g.attempts += 1
                prob = GARBAGE_TYPES[g.kind].pickup_eff * (0.55 + 0.45 * cmd.suction)
                if self.rng.random() < prob:
                    g.collected = True
            g.inside = inside

    # ------------------------------------------------------------ results
    def run(self, max_steps: int = 100000) -> SimResult:
        n = 0
        while self.step() and n < max_steps:
            n += 1
        return self.result()

    def result(self) -> SimResult:
        spawned = self.room.spawned_mass()
        collected = self.room.collected_mass()
        docked = self.mission.state == MissionState.DOCKED
        elapsed = self.mission.elapsed
        avg_p = self.battery.consumed_wh * 3600 / max(self.t, 1e-6)
        rr = RunResult(docked, elapsed, self.cfg.mission.time_budget_s, collected, spawned,
                       True, self.collisions, self.cable_incidents, 0,
                       self.battery.runtime_minutes(avg_p), PROTOTYPE_BOM_INR)
        card: ScoreCard = score(rr)
        dock_err = math.hypot(self.true_pose.x - self.cfg.room.dock_x, self.true_pose.y - self.cfg.room.dock_y)
        saving = 100.0 * (1 - self.battery.consumed_wh / self._eco_ref_wh) if self._eco_ref_wh else 0.0
        return SimResult(
            seed=self.seed, docked=docked, elapsed_s=round(elapsed, 1),
            coverage=round(self.truth_cov.coverage_ratio(self.cleanable), 4),
            collisions=self.collisions, cable_incidents=self.cable_incidents,
            recoveries=self.mission.recoveries, replans=self.mission.replans,
            energy_wh=round(self.battery.consumed_wh, 3), avg_power_w=round(avg_p, 2),
            eco_energy_saving_pct=round(saving, 1),
            efficiency_by_type={k: round(collected[k] / spawned[k], 3) if spawned[k] else 1.0 for k in spawned},
            collected_g={k: round(v, 2) for k, v in collected.items()},
            spawned_g={k: round(v, 2) for k, v in spawned.items()},
            final_dock_error_m=round(dock_err, 3),
            score=card.as_dict())
