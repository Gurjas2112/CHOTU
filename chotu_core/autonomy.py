"""CleaningMission - the autonomy "brain" shared by ROS 2 and the simulator.

Call :meth:`CleaningMission.step` at ``control_rate_hz`` with an
:class:`Observation`; it returns a :class:`Command`.  The ROS 2
``mission_manager_node`` and ``bot_simulation`` both drive exactly this class,
so every simulated run is a test of the code that ships on the robot.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .config import ChotuConfig, DEFAULT_CONFIG
from .coverage_planner import BoustrophedonPlanner, CoverageTracker, CoverageWaypoint
from .kinematics import Pose2D, wrap_angle
from .mission_fsm import MissionFSM, MissionState as S
from .obstacle_avoidance import RangeReading, ReactiveSafety
from .occupancy_grid import OccupancyGrid, flood_fill
from .path_planner import GridPlanner, path_length
from .perception import Detection, debris_ahead
from .suction_controller import AdaptiveSuction


@dataclass
class Observation:
    t: float
    pose: Pose2D                       # odometry estimate (encoders + gyro)
    ranges: List[RangeReading]
    cliff: bool = False
    bump: bool = False
    detections: List[Detection] = field(default_factory=list)
    battery_soc: float = 1.0
    dock_beacon: Optional[Tuple[float, float]] = None  # IR beacon fix near the dock


@dataclass
class Command:
    v: float = 0.0
    w: float = 0.0
    suction: float = 0.0
    brush: float = 0.0
    state: str = "IDLE"
    safety: str = "clear"


@dataclass
class MissionEvent:
    t: float
    kind: str
    text: str


class CleaningMission:
    def __init__(self, cfg: ChotuConfig = DEFAULT_CONFIG):
        self.cfg = cfg
        r, m, room = cfg.robot, cfg.mission, cfg.room
        self.grid = OccupancyGrid(room.width, room.height, m.grid_resolution)
        self.clearance = r.radius + m.inflation_margin
        self.planner = GridPlanner(self.grid, self.clearance)
        self.coverage = CoverageTracker(room.width, room.height, m.grid_resolution, r.cleaning_width)
        self.safety = ReactiveSafety(m.stop_distance, m.slow_distance, r.radius)
        self.suction = AdaptiveSuction()
        self.fsm = MissionFSM()
        self.dock = Pose2D(room.dock_x, room.dock_y, room.dock_theta)
        self.dock_approach = (room.dock_x, room.dock_y + m.undock_distance)
        self.waypoints: List[CoverageWaypoint] = BoustrophedonPlanner(
            room.width, room.height, m.lane_spacing, m.wall_margin, m.waypoint_step
        ).generate(start_x=room.dock_x)
        self.wp_index: Optional[int] = None
        self._lane: Optional[int] = None
        self._lane_dir = 0
        self.path: List[Tuple[float, float]] = []
        self.target: Optional[Tuple[float, float]] = None
        self.target_kind = ""
        self.spot_targets: List[Tuple[float, float]] = []
        self.keepouts: List[Detection] = []
        self.no_go: List[Tuple[float, float, float, float]] = []
        self.events: List[MissionEvent] = []
        self.pose = self.dock.copy()
        self.t = 0.0
        self.start_t: Optional[float] = None
        self.scan_accum = 0.0
        self._last_theta = 0.0
        self._blocked_since: Optional[float] = None
        self._recovery_phase = 0
        self._recovery_dir = 1
        self._recover_count = 0
        self._last_return_check = -10.0
        self._return_eta = 0.0
        self._last_replan = -10.0
        self._last_progress_t = 0.0
        self._last_progress_d = 1e9
        self._progress_anchor = None
        self._trap_cache = (-1, False)
        self.replans = 0
        self.recoveries = 0
        self.last_detections: List[Detection] = []
        self.last_ranges: List[RangeReading] = []

    # ================================================================ API
    def start(self, t: float) -> None:
        self.start_t = t
        self.fsm.transition(S.UNDOCK, t, "mission start")
        self._event(t, "state", "Mission start - undocking")

    def add_no_go(self, x0: float, y0: float, x1: float, y1: float) -> None:
        """User no-go zone (Flutter app -> /chotu/set_zones). Treated like a
        permanent obstacle: never entered, never planned through, and its
        floor is excluded from the coverage target."""
        rect = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
        self.no_go.append(rect)
        self.grid.mark_rect(*rect)
        self._event(self.t, "state", f"No-go zone set ({rect[2] - rect[0]:.2f} x {rect[3] - rect[1]:.2f} m)")

    def in_no_go(self, x: float, y: float) -> bool:
        return any(a <= x <= c and b <= y <= d for a, b, c, d in self.no_go)

    @property
    def elapsed(self) -> float:
        return 0.0 if self.start_t is None else self.t - self.start_t

    @property
    def time_left(self) -> float:
        return self.cfg.mission.time_budget_s - self.elapsed

    @property
    def state(self) -> S:
        return self.fsm.state

    def step(self, obs: Observation) -> Command:
        dt = 1.0 / self.cfg.mission.control_rate_hz
        self.t = obs.t
        self.pose = obs.pose
        self.last_ranges = obs.ranges
        self.last_detections = obs.detections
        self._update_map(obs)
        cleaning = self.state in (S.COVER, S.SPOT_CLEAN, S.STUCK_RECOVERY, S.RETURN_TO_DOCK, S.SCAN)
        if cleaning:
            self.coverage.mark(self.pose.x, self.pose.y)

        v, w = self._run_state(obs)

        # Reactive safety layer (docking deliberately touches the dock)
        level = "clear"
        if self.state not in (S.DOCKING, S.DOCKED, S.IDLE):
            v, w, st = self.safety.filter(v, w, obs.ranges, obs.cliff, obs.bump)
            level = st.level
            self._handle_safety(level, obs)
        duty = self.suction.update(obs.t, dt, cleaning, debris_ahead(obs.detections, self.pose))
        return Command(v, w, duty, 1.0 if duty > 0.05 else 0.0, self.state.value, level)

    # ================================================================ map
    def _update_map(self, obs: Observation) -> None:
        r = self.cfg.robot.radius
        cone = math.radians(self.cfg.sensors.ultrasonic_cone_deg) / 2
        for rd in obs.ranges:
            a = self.pose.theta + rd.angle
            ox = self.pose.x + r * math.cos(a)
            oy = self.pose.y + r * math.sin(a)
            # HC-SR04 has a ~15° beam: the echo may come from anywhere on the
            # arc.  If any point of the arc lies on a known wall, the wall
            # explains the echo; otherwise the whole arc is marked.
            spread = (-cone, 0.0, cone) if rd.source == "us" else (0.0,)
            explained = rd.valid_hit and any(
                self.grid.near_wall(ox + rd.distance * math.cos(a + da),
                                                    oy + rd.distance * math.sin(a + da), 0.13) for da in spread)
            for da in spread:
                # beam edges carry less energy: weaker free-space evidence, so
                # thin objects (chair legs) seen by the beam centre survive
                self.grid.update_ray(ox, oy, a + da, rd.distance, rd.max_range,
                                     mark_hit=not explained,
                                     free_scale=1.0 if da == 0.0 else 0.3)
        if obs.bump:
            self.grid.mark_disc(self.pose.x + (r + 0.04) * math.cos(self.pose.theta),
                                self.pose.y + (r + 0.04) * math.sin(self.pose.theta), 0.05)
        for d in obs.detections:
            if d.action == "avoid":
                if not any(math.hypot(d.x - k.x, d.y - k.y) < 0.08 for k in self.keepouts):
                    if not any(math.hypot(d.x - k.x, d.y - k.y) < 0.6 for k in self.keepouts):
                        self._event(obs.t, "vision", f"AI vision: AVOID '{d.label}' -> keep-out zone")
                    self.keepouts.append(d)
                self.grid.mark_disc(d.x, d.y, d.radius, keepout=True)
            elif d.action == "suck" and self.state in (S.COVER, S.SPOT_CLEAN):
                if not any(math.hypot(d.x - sx, d.y - sy) < 0.15 for sx, sy in self.spot_targets):
                    self.spot_targets.append((d.x, d.y))

    # ================================================================ states
    def _run_state(self, obs: Observation) -> Tuple[float, float]:
        st = self.state
        m = self.cfg.mission
        if st in (S.IDLE, S.DOCKED, S.ABORTED):
            return 0.0, 0.0
        # time / battery driven return
        if st in (S.COVER, S.SPOT_CLEAN, S.SCAN, S.UNDOCK):
            if self._must_return(obs):
                self._go_home(obs.t, "time budget" if obs.battery_soc > 0.15 else "low battery")
                return 0.0, 0.0
        if st == S.UNDOCK:
            d = self.dock.distance_to(self.pose.x, self.pose.y)
            if d >= m.undock_distance:
                self.fsm.transition(S.SCAN, obs.t, "undocked")
                self.scan_accum = 0.0
                self._last_theta = self.pose.theta
                self._event(obs.t, "state", "360° ToF/ultrasonic mapping scan")
                return 0.0, 0.0
            return self._drive_heading(self.dock.theta, 0.18)
        if st == S.SCAN:
            self.scan_accum += abs(wrap_angle(self.pose.theta - self._last_theta))
            self._last_theta = self.pose.theta
            if self.scan_accum >= 2 * math.pi:
                self.fsm.transition(S.COVER, obs.t, "scan complete")
                self._event(obs.t, "state", f"Boustrophedon coverage: {len(self.waypoints)} waypoints")
                return 0.0, 0.0
            return 0.0, m.scan_turn_rate
        if st == S.COVER:
            return self._cover(obs)
        if st == S.SPOT_CLEAN:
            return self._spot_clean(obs)
        if st == S.STUCK_RECOVERY:
            return self._recover(obs)
        if st == S.RETURN_TO_DOCK:
            return self._return(obs)
        if st == S.DOCKING:
            return self._docking(obs)
        return 0.0, 0.0

    # --------------------------------------------------------------- cover
    def _cover(self, obs: Observation) -> Tuple[float, float]:
        """Greedy lane-biased boustrophedon.

        The lanes give the zig-zag structure; instead of visiting them in a
        rigid order (which forces long detours when an obstacle splits a
        lane) the next waypoint is the cheapest pending one under an
        anisotropic metric: moving *along* a lane costs 1, changing lanes
        costs 2.5, reversing the current sweep direction costs extra.  The
        robot therefore finishes the region it is in before crossing over -
        an online equivalent of boustrophedon cell decomposition.
        """
        m = self.cfg.mission
        for wp in self.waypoints:
            if wp.status == "pending" and math.hypot(wp.x - self.pose.x, wp.y - self.pose.y) < m.waypoint_tolerance + 0.05:
                wp.status = "done"
        plan_failures = 0
        for _ in range(len(self.waypoints)):
            wp = self.waypoints[self.wp_index] if self.wp_index is not None else None
            if wp is None or wp.status != "pending" or wp.retry_after > obs.t:
                self.wp_index = self._select_waypoint(obs.t)
                self.path = []
                if self.wp_index is None:
                    break
                continue
            if not self.grid.is_free(wp.x, wp.y, self.clearance):
                snapped = self.grid.nearest_free(wp.x, wp.y, self.clearance, search_m=0.12)
                if snapped is None or math.hypot(snapped[0] - wp.x, snapped[1] - wp.y) > 0.12:
                    wp.status = "skipped"
                    continue
                wp.x, wp.y = snapped
                self.path = []
            if self.target != (wp.x, wp.y) or not self.path:
                if not self._plan_to(wp.x, wp.y, "lane", snap=False):
                    plan_failures += 1
                    if self._trapped():
                        # the robot is boxed in by fresh map evidence - not the
                        # waypoint's fault: wiggle so the sensors refresh the map
                        return 0.0, 0.8
                    wp.fails += 1
                    if wp.fails >= 3:
                        wp.status = "skipped"
                    else:
                        wp.retry_after = obs.t + 4.0
                    if plan_failures >= 3:
                        return 0.0, 0.6   # rotate in place: let the sensors refresh the map
                    continue
            if math.hypot(wp.x - self.pose.x, wp.y - self.pose.y) < m.waypoint_tolerance:
                wp.status = "done"
                continue
            if wp.lane != self._lane:
                self._lane, self._lane_dir = wp.lane, 0
            elif abs(wp.x - self.pose.x) > 0.05:
                self._lane_dir = 1 if wp.x > self.pose.x else -1
            return self._follow()
        if any(w.status == "pending" for w in self.waypoints):
            return 0.0, 0.6
        self.fsm.transition(S.SPOT_CLEAN, obs.t, "lanes complete")
        self._event(obs.t, "state", "Lanes done - spot clean & frontier fill")
        self.target, self.path = None, []
        return 0.0, 0.0

    def _trapped(self) -> bool:
        """True if less than a quarter of the known-free area is reachable."""
        if self._trap_cache[0] == self.grid._version:
            return self._trap_cache[1]
        hard, soft = self.planner.masks()
        blocked = soft.copy()
        sx, sy = self.grid.world_to_cell(self.pose.x, self.pose.y)
        r = self.planner.escape_cells
        y0, y1 = max(0, sy - r), min(soft.shape[0], sy + r + 1)
        x0, x1 = max(0, sx - r), min(soft.shape[1], sx + r + 1)
        blocked[y0:y1, x0:x1] = hard[y0:y1, x0:x1]
        reach = flood_fill(blocked, (sx, sy)).sum()
        trapped = reach < 0.25 * max(1, int((~soft).sum()))
        self._trap_cache = (self.grid._version, trapped)
        return trapped

    def _select_waypoint(self, t: float) -> Optional[int]:
        best, best_cost = None, 1e18
        spacing = self.cfg.mission.lane_spacing
        for i, wp in enumerate(self.waypoints):
            if wp.status != "pending" or wp.retry_after > t:
                continue
            dx, dy = wp.x - self.pose.x, wp.y - self.pose.y
            lane_jump = abs(wp.lane - self._lane) if self._lane is not None else 0
            cost = abs(dx) + 2.5 * abs(dy) + 0.15 * lane_jump * spacing
            if self._lane_dir and wp.lane == self._lane and dx * self._lane_dir < -0.05:
                cost += 0.6
            if cost < best_cost:
                best, best_cost = i, cost
        return best

    # --------------------------------------------------------------- spot
    def _spot_clean(self, obs: Observation) -> Tuple[float, float]:
        m = self.cfg.mission
        if self.target is not None and self.path:
            if math.hypot(self.target[0] - self.pose.x, self.target[1] - self.pose.y) < m.waypoint_tolerance:
                self.target, self.path = None, []
            else:
                return self._follow()
        # drop debris targets that were swept already
        self.spot_targets = [(x, y) for x, y in self.spot_targets
                             if not self._is_cleaned(x, y)]
        centre_free = ~self.grid.inflated_mask(self.clearance)
        candidates: List[Tuple[float, float, str]] = []
        for x, y in sorted(self.spot_targets, key=lambda p: math.hypot(p[0] - self.pose.x, p[1] - self.pose.y)):
            candidates.append((x, y, "debris"))
        for x, y, _n in self.coverage.frontier_targets(centre_free, self.pose.x, self.pose.y,
                                                        m.min_frontier_cells)[:6]:
            candidates.append((x, y, "frontier"))
        for x, y, kind in candidates:
            if self._plan_to(x, y, kind, snap=True):
                self.spot_targets = [p for p in self.spot_targets if p != (x, y)]
                return self._follow()
            if kind == "debris":
                self.spot_targets = [p for p in self.spot_targets if p != (x, y)]
            else:
                self.coverage.mark(x, y)  # unreachable pocket: stop retrying it
        self._go_home(obs.t, "room complete")
        return 0.0, 0.0

    def _is_cleaned(self, x: float, y: float) -> bool:
        ix, iy = int(x / self.coverage.res), int(y / self.coverage.res)
        if 0 <= ix < self.coverage.nx and 0 <= iy < self.coverage.ny:
            return bool(self.coverage.cleaned[iy, ix])
        return True

    # --------------------------------------------------------------- return
    def _must_return(self, obs: Observation) -> bool:
        if obs.battery_soc < 0.12:
            return True
        if self.t - self._last_return_check > 1.0:
            self._last_return_check = self.t
            pts = self.planner.plan(self.pose.x, self.pose.y, *self.dock_approach)
            dist = path_length([(self.pose.x, self.pose.y)] + pts) if pts else \
                1.5 * math.hypot(self.pose.x - self.dock_approach[0], self.pose.y - self.dock_approach[1])
            self._return_eta = dist / (0.75 * self.cfg.robot.max_linear) + 6.0
        return self.time_left < self._return_eta + self.cfg.mission.return_margin_s

    def request_dock(self, t: float) -> bool:
        """Operator 'return to dock' (Flutter app button / StartMission abort=true)."""
        if self.state in (S.UNDOCK, S.SCAN, S.COVER, S.SPOT_CLEAN, S.STUCK_RECOVERY):
            self._go_home(t, "app request")
            return True
        return False

    def _go_home(self, t: float, reason: str) -> None:
        if self.state in (S.RETURN_TO_DOCK, S.DOCKING, S.DOCKED):
            return
        self.fsm.transition(S.RETURN_TO_DOCK, t, reason)
        self._event(t, "state", f"Returning to dock ({reason})")
        self.target, self.path = None, []

    def _return(self, obs: Observation) -> Tuple[float, float]:
        ax, ay = self.dock_approach
        if math.hypot(ax - self.pose.x, ay - self.pose.y) < 0.08:
            self.fsm.transition(S.DOCKING, obs.t, "at dock approach")
            self._event(obs.t, "state", "IR-beacon docking")
            return 0.0, 0.0
        if self.target != (ax, ay) or not self.path:
            if not self._plan_to(ax, ay, "dock", snap=True) and                     not self._plan_to(ax, ay, "dock", snap=True, relaxed=True):
                return self._drive_to_point(ax, ay, 0.12)
        return self._follow()

    def _docking(self, obs: Observation) -> Tuple[float, float]:
        tx, ty = self.dock.x, self.dock.y
        if obs.dock_beacon is not None:
            tx, ty = obs.dock_beacon
        heading = math.atan2(ty - self.pose.y, tx - self.pose.x)
        err = wrap_angle(heading - self.pose.theta)
        d = math.hypot(tx - self.pose.x, ty - self.pose.y)
        if d < 0.03:
            self.fsm.transition(S.DOCKED, obs.t, "contacts closed")
            self._event(obs.t, "state", f"DOCKED at t={self.elapsed:.1f}s")
            return 0.0, 0.0
        if abs(err) > 0.25:
            return 0.0, max(-1.2, min(1.2, 2.5 * err))
        return min(0.10, 0.6 * d + 0.02), 2.0 * err

    # --------------------------------------------------------------- recovery
    def _handle_safety(self, level: str, obs: Observation) -> None:
        if self.state in (S.STUCK_RECOVERY, S.SCAN):
            self._blocked_since = None
            return
        if level in ("blocked", "bump", "cliff"):
            if self._blocked_since is None:
                self._blocked_since = obs.t
                self.path = []  # force a replan around the new obstacle
            elif obs.t - self._blocked_since > self.cfg.mission.stuck_timeout_s:
                self._blocked_since = None
                self._enter_recovery(obs, level)
        else:
            self._blocked_since = None
        # no-progress watchdog: the robot must translate 5 cm every 5 s
        if self._progress_anchor is None or math.hypot(self.pose.x - self._progress_anchor[0],
                                                       self.pose.y - self._progress_anchor[1]) > 0.05:
            self._progress_anchor = (self.pose.x, self.pose.y)
            self._last_progress_t = obs.t
        elif obs.t - self._last_progress_t > 5.0 and self.state in (S.COVER, S.SPOT_CLEAN, S.RETURN_TO_DOCK):
            self._last_progress_t = obs.t
            self._enter_recovery(obs, "no progress")

    def _enter_recovery(self, obs: Observation, why: str) -> None:
        self.recoveries += 1
        self._recover_count += 1
        self._recovery_dir = self.safety.escape_direction(obs.ranges)
        self._recovery_phase = 0
        self.fsm.transition(S.STUCK_RECOVERY, obs.t, why)
        self._event(obs.t, "warn", f"Stuck recovery ({why}) - reverse & turn")
        # give up on the current coverage waypoint after repeated failures
        if self._recover_count > self.cfg.mission.max_recoveries_per_target:
            if self.fsm.resume_state == S.COVER and self.wp_index is not None:
                self.waypoints[self.wp_index].status = "skipped"
            self._recover_count = 0
        self.path = []

    def _recover(self, obs: Observation) -> Tuple[float, float]:
        tin = self.fsm.time_in_state(obs.t)
        if tin < 0.6:
            return -0.10, 0.0
        if tin < 1.6:
            return 0.0, 1.4 * self._recovery_dir
        resume = self.fsm.resume_state or S.COVER
        self.fsm.transition(resume, obs.t, "recovered")
        self._last_progress_t = obs.t
        self._last_progress_d = 1e9
        return 0.0, 0.0

    # --------------------------------------------------------------- motion
    def _plan_to(self, x: float, y: float, kind: str, snap: bool, relaxed: bool = False) -> bool:
        pts = self.planner.plan(self.pose.x, self.pose.y, x, y, snap_goal=snap, relaxed=relaxed)
        self.replans += 1
        if not pts:
            self.path = []
            return False
        if self.target != (x, y):
            self._last_progress_d, self._last_progress_t = 1e9, self.t
        self.path = pts
        self.target = (x, y)
        self.target_kind = kind
        return True

    def _follow(self) -> Tuple[float, float]:
        tol = 0.06
        while len(self.path) > 1 and math.hypot(self.path[0][0] - self.pose.x,
                                                self.path[0][1] - self.pose.y) < tol:
            self.path.pop(0)
        if not self.path:
            return 0.0, 0.0
        x, y = self.path[0]
        return self._drive_to_point(x, y, self.cfg.robot.max_linear)

    def _drive_to_point(self, x: float, y: float, vmax: float) -> Tuple[float, float]:
        heading = math.atan2(y - self.pose.y, x - self.pose.x)
        err = wrap_angle(heading - self.pose.theta)
        wmax = self.cfg.robot.max_angular
        if abs(err) > 1.1:
            return 0.0, max(-wmax, min(wmax, 3.0 * err))
        d = math.hypot(x - self.pose.x, y - self.pose.y)
        # arc through turns instead of stopping: speed falls with heading error
        v = vmax * max(0.0, math.cos(err)) ** 2 * (1.0 if len(self.path) > 1 else min(1.0, 0.4 + d / 0.3))
        return v, max(-wmax, min(wmax, 3.0 * err))

    def _drive_heading(self, heading: float, v: float) -> Tuple[float, float]:
        err = wrap_angle(heading - self.pose.theta)
        if abs(err) > 0.4:
            return 0.0, max(-1.5, min(1.5, 2.5 * err))
        return v, 2.5 * err

    def _event(self, t: float, kind: str, text: str) -> None:
        self.events.append(MissionEvent(t, kind, text))
