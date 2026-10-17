"""Gazebo adapter: makes Gazebo look exactly like serial_bridge_node.

* narrow gpu_lidar beams  -> sensor_msgs/Range on /range/{left,center,right,tof}
* /gz/odom + /imu -> /odom + TF in the *room* frame, fused exactly like the real
  robot (wheel distance from the drive, heading from the gyro/IMU), so wheel
  slip does not rotate the robot's belief - same as serial_bridge_node
* bump / cliff / battery placeholders
"""
from __future__ import annotations

import math

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from geometry_msgs.msg import TransformStamped
from nav_msgs.msg import Odometry
from sensor_msgs.msg import BatteryState, Imu, LaserScan, Range
from std_msgs.msg import Bool
from tf2_ros import TransformBroadcaster

from chotu_core.config import DEFAULT_CONFIG

BEAMS = {"us_left": "left", "us_center": "center", "us_right": "right", "tof": "tof"}


class GzSensorAdapter(Node):
    def __init__(self):
        super().__init__("chotu_gz_sensor_adapter")
        self.pubs = {}
        for gz_name, name in BEAMS.items():
            self.pubs[name] = self.create_publisher(Range, f"range/{name}", qos_profile_sensor_data)
            self.create_subscription(LaserScan, f"/gz/{gz_name}",
                                     lambda m, n=name: self.on_scan(n, m), qos_profile_sensor_data)
        room = DEFAULT_CONFIG.room
        self.declare_parameter("dock_x", room.dock_x)
        self.declare_parameter("dock_y", room.dock_y)
        self.declare_parameter("dock_theta", room.dock_theta)
        self.odom_pub = self.create_publisher(Odometry, "odom", 20)
        self.tf = TransformBroadcaster(self)
        self.create_subscription(Odometry, "/gz/odom", self.on_gz_odom, 20)
        self.create_subscription(Imu, "/imu", self.on_imu, qos_profile_sensor_data)
        self.imu_yaw = None        # heading from the IMU (relative to boot, like a gyro)
        self.imu_yaw0 = None
        self.last_gz = None        # previous drive-odometry position (for distance)
        self.pose = None           # fused (x, y, theta) in the room frame
        self.bump_pub = self.create_publisher(Bool, "chotu/bump", 10)
        self.cliff_pub = self.create_publisher(Bool, "chotu/cliff", 10)
        self.batt_pub = self.create_publisher(BatteryState, "battery_state", 10)
        self.create_timer(0.1, self.tick)

    @staticmethod
    def _yaw(q) -> float:
        return math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))

    def on_imu(self, msg: Imu):
        yaw = self._yaw(msg.orientation)
        if self.imu_yaw0 is None:
            self.imu_yaw0 = yaw
        self.imu_yaw = yaw - self.imu_yaw0

    def on_gz_odom(self, msg: Odometry):
        dx, dy, dth = (self.get_parameter(n).value for n in ("dock_x", "dock_y", "dock_theta"))
        p = msg.pose.pose.position
        wheel_yaw = self._yaw(msg.pose.pose.orientation)
        heading = (self.imu_yaw if self.imu_yaw is not None else wheel_yaw) + dth
        if self.pose is None:
            self.pose = (dx, dy, heading)
        else:
            ds = math.hypot(p.x - self.last_gz[0], p.y - self.last_gz[1])
            ds = math.copysign(ds, msg.twist.twist.linear.x) if abs(msg.twist.twist.linear.x) > 1e-4 else 0.0
            mid = math.atan2(math.sin(heading) + math.sin(self.pose[2]), math.cos(heading) + math.cos(self.pose[2]))
            self.pose = (self.pose[0] + ds * math.cos(mid), self.pose[1] + ds * math.sin(mid), heading)
        self.last_gz = (p.x, p.y)
        x, y, th = self.pose
        out = Odometry()
        out.header.stamp = msg.header.stamp
        out.header.frame_id, out.child_frame_id = "odom", "base_footprint"
        out.pose.pose.position.x, out.pose.pose.position.y = x, y
        out.pose.pose.orientation.z, out.pose.pose.orientation.w = math.sin(th / 2), math.cos(th / 2)
        out.twist = msg.twist
        self.odom_pub.publish(out)
        tf = TransformStamped()
        tf.header = out.header
        tf.child_frame_id = out.child_frame_id
        tf.transform.translation.x, tf.transform.translation.y = x, y
        tf.transform.rotation = out.pose.pose.orientation
        self.tf.sendTransform(tf)

    def on_scan(self, name: str, scan: LaserScan):
        valid = [r for r in scan.ranges if math.isfinite(r)]
        r = Range()
        r.header = scan.header
        r.radiation_type = Range.INFRARED if name == "tof" else Range.ULTRASOUND
        r.field_of_view = max(0.02, scan.angle_max - scan.angle_min)
        r.min_range, r.max_range = scan.range_min, scan.range_max
        r.range = min(valid) if valid else scan.range_max
        self.pubs[name].publish(r)

    def tick(self):
        self.bump_pub.publish(Bool(data=False))
        self.cliff_pub.publish(Bool(data=False))
        b = BatteryState()
        b.header.stamp = self.get_clock().now().to_msg()
        b.voltage, b.percentage, b.present = 12.2, 0.9, True
        self.batt_pub.publish(b)


def main(args=None):
    rclpy.init(args=args)
    node = GzSensorAdapter()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
