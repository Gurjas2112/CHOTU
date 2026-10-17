"""CHOTU mission manager - ROS 2 wrapper around chotu_core.CleaningMission.

This is the exact autonomy code that bot_simulation validates; the node only
converts ROS messages into an ``Observation`` and the resulting ``Command``
back into ROS messages.

Subscribes  /odom, /range/{left,center,right,tof}, /chotu/bump, /chotu/cliff,
            /chotu/detections, /battery_state
Publishes   /cmd_vel, /chotu/actuators, /chotu/status, /map (1 Hz), /chotu/plan
Services    /chotu/start_mission (chotu_interfaces/StartMission)
"""
from __future__ import annotations

import math
from dataclasses import replace

import numpy as np
import rclpy
from geometry_msgs.msg import PoseStamped, Twist
from nav_msgs.msg import OccupancyGrid, Odometry, Path
from rclpy.node import Node
from rclpy.qos import QoSDurabilityPolicy, QoSProfile, qos_profile_sensor_data
from sensor_msgs.msg import BatteryState, Range
from std_msgs.msg import Bool

from chotu_core.autonomy import CleaningMission, Observation
from chotu_core.config import DEFAULT_CONFIG
from chotu_core.kinematics import Pose2D
from chotu_core.mission_fsm import MissionState
from chotu_core.obstacle_avoidance import RangeReading
from chotu_core.perception import Detection
from chotu_interfaces.msg import Actuators, CleaningStatus, DetectionArray
from chotu_interfaces.srv import StartMission

RANGE_ANGLES = {"left": 35.0, "center": 0.0, "right": -35.0, "tof": 0.0}


def quat_to_yaw(q) -> float:
    return math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))


class MissionManager(Node):
    def __init__(self):
        super().__init__("chotu_mission_manager")
        self.declare_parameter("auto_start", False)
        self.declare_parameter("time_budget_s", 300.0)
        self.declare_parameter("room_width_m", DEFAULT_CONFIG.room.width)
        self.declare_parameter("room_height_m", DEFAULT_CONFIG.room.height)
        self.declare_parameter("dock_x", DEFAULT_CONFIG.room.dock_x)
        self.declare_parameter("dock_y", DEFAULT_CONFIG.room.dock_y)
        self.declare_parameter("lane_spacing", DEFAULT_CONFIG.mission.lane_spacing)
        self.declare_parameter("max_linear", DEFAULT_CONFIG.robot.max_linear)
        self.cfg = self._config_from_params()
        self.mission = CleaningMission(self.cfg)
        self.started = False

        self.pose = None
        self.ranges = {}
        self.bump = False
        self.cliff = False
        self.detections = []
        self.soc = 1.0

        self.create_subscription(Odometry, "odom", self.on_odom, 20)
        for name in RANGE_ANGLES:
            self.create_subscription(Range, f"range/{name}", lambda m, n=name: self.on_range(n, m),
                                     qos_profile_sensor_data)
        self.create_subscription(Bool, "chotu/bump", lambda m: setattr(self, "bump", m.data), 10)
        self.create_subscription(Bool, "chotu/cliff", lambda m: setattr(self, "cliff", m.data), 10)
        self.create_subscription(DetectionArray, "chotu/detections", self.on_detections, 10)
        self.create_subscription(BatteryState, "battery_state",
                                 lambda m: setattr(self, "soc", float(m.percentage)), 10)

        self.cmd_pub = self.create_publisher(Twist, "cmd_vel", 10)
        self.act_pub = self.create_publisher(Actuators, "chotu/actuators", 10)
        self.status_pub = self.create_publisher(CleaningStatus, "chotu/status", 10)
        self.path_pub = self.create_publisher(Path, "chotu/plan", 10)
        latched = QoSProfile(depth=1, durability=QoSDurabilityPolicy.TRANSIENT_LOCAL)
        self.map_pub = self.create_publisher(OccupancyGrid, "map", latched)
        self.create_service(StartMission, "chotu/start_mission", self.on_start)

        self.dt = 1.0 / self.cfg.mission.control_rate_hz
        self.create_timer(self.dt, self.control_tick)
        self.create_timer(0.2, self.publish_status)
        self.create_timer(1.0, self.publish_map)
        self.get_logger().info("CHOTU mission manager ready - call /chotu/start_mission")

    def _config_from_params(self):
        g = lambda n: self.get_parameter(n).value  # noqa: E731
        c = DEFAULT_CONFIG
        return replace(
            c,
            room=replace(c.room, width=g("room_width_m"), height=g("room_height_m"),
                         dock_x=g("dock_x"), dock_y=g("dock_y")),
            mission=replace(c.mission, time_budget_s=g("time_budget_s"), lane_spacing=g("lane_spacing")),
            robot=replace(c.robot, max_linear=g("max_linear")),
        )

    # ------------------------------------------------------------ inputs
    def on_odom(self, msg: Odometry):
        p = msg.pose.pose
        self.pose = Pose2D(p.position.x, p.position.y, quat_to_yaw(p.orientation))

    def on_range(self, name: str, msg: Range):
        dist = msg.range if math.isfinite(msg.range) else msg.max_range
        self.ranges[name] = RangeReading(math.radians(RANGE_ANGLES[name]),
                                         max(0.0, dist - 0.0), msg.max_range,
                                         "tof" if name == "tof" else "us")

    def on_detections(self, msg: DetectionArray):
        self.detections = [Detection(d.label, d.action, d.confidence, d.position.x, d.position.y, d.radius)
                           for d in msg.detections]

    def on_start(self, req, res):
        if req.abort:
            if self.started and self.mission.state not in (MissionState.DOCKED, MissionState.ABORTED):
                self.mission.fsm.transition(MissionState.ABORTED, self.now(), "operator abort")
            res.accepted, res.message = True, "mission aborted"
            return res
        if self.started and self.mission.state not in (MissionState.DOCKED, MissionState.ABORTED):
            res.accepted, res.message = False, f"already running ({self.mission.state.value})"
            return res
        if req.time_budget_s > 0:
            self.cfg = replace(self.cfg, mission=replace(self.cfg.mission, time_budget_s=req.time_budget_s))
        self.mission = CleaningMission(self.cfg)
        self.mission.start(self.now())
        self.started = True
        res.accepted, res.message = True, "mission started"
        self.get_logger().info("Mission started")
        return res

    def now(self) -> float:
        return self.get_clock().now().nanoseconds * 1e-9

    # ------------------------------------------------------------ control
    def control_tick(self):
        if self.pose is None or len(self.ranges) < 4:
            return
        if not self.started:
            if self.get_parameter("auto_start").value:
                self.mission.start(self.now())
                self.started = True
            else:
                return
        obs = Observation(self.now(), self.pose, list(self.ranges.values()), self.cliff, self.bump,
                          self.detections, self.soc)
        self.detections = []
        cmd = self.mission.step(obs)
        tw = Twist()
        tw.linear.x, tw.angular.z = float(cmd.v), float(cmd.w)
        self.cmd_pub.publish(tw)
        self.act_pub.publish(Actuators(suction=float(cmd.suction), brush=float(cmd.brush)))

    def publish_status(self):
        m = self.mission
        s = CleaningStatus()
        s.header.stamp = self.get_clock().now().to_msg()
        s.state = m.state.value
        s.elapsed_s = float(m.elapsed)
        s.time_left_s = float(m.time_left)
        free = ~m.grid.inflated_mask(m.clearance)
        s.coverage_estimate = float(m.coverage.coverage_ratio(free | m.coverage.cleaned))
        s.waypoints_total = len(m.waypoints)
        s.waypoints_done = sum(w.status == "done" for w in m.waypoints)
        s.waypoints_skipped = sum(w.status == "skipped" for w in m.waypoints)
        s.recoveries, s.replans = m.recoveries, m.replans
        s.suction_duty, s.suction_mode = float(m.suction.duty), m.suction.mode
        s.battery_soc = float(self.soc)
        s.last_event = m.events[-1].text if m.events else ""
        self.status_pub.publish(s)
        path = Path()
        path.header.stamp = s.header.stamp
        path.header.frame_id = "odom"
        for x, y in m.path:
            ps = PoseStamped()
            ps.header = path.header
            ps.pose.position.x, ps.pose.position.y = x, y
            path.poses.append(ps)
        self.path_pub.publish(path)

    def publish_map(self):
        g = self.mission.grid
        msg = OccupancyGrid()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "odom"
        msg.info.resolution = g.res
        msg.info.width, msg.info.height = g.nx, g.ny
        msg.info.origin.orientation.w = 1.0
        msg.data = np.asarray(g.to_ros_data(), dtype=np.int8).tolist()
        self.map_pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = MissionManager()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.cmd_pub.publish(Twist())
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
