"""ESP32-S3 <-> ROS 2 bridge (runs on the Raspberry Pi 4).

Subscribes   /cmd_vel (geometry_msgs/Twist)        -> CMD_VEL frame
             /chotu/actuators (chotu_interfaces/Actuators) -> ACTUATORS frame
             /chotu/estop (std_msgs/Bool)          -> ESTOP frame
Publishes    /odom (nav_msgs/Odometry) + TF odom->base_footprint
             /range/{left,center,right,tof} (sensor_msgs/Range)
             /imu (sensor_msgs/Imu, gyro z), /chotu/bump, /chotu/cliff (std_msgs/Bool)
             /battery_state (sensor_msgs/BatteryState)

The wire format lives in chotu_core.protocol (shared with the firmware tests).
"""
from __future__ import annotations

import math

import rclpy
from geometry_msgs.msg import TransformStamped, Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import BatteryState, Imu, Range
from std_msgs.msg import Bool
from tf2_ros import TransformBroadcaster

from chotu_core import protocol as P
from chotu_core.config import DEFAULT_CONFIG
from chotu_core.kinematics import DiffDrive, FusedOdometry, Pose2D
from chotu_interfaces.msg import Actuators

try:
    import serial  # pyserial
except ImportError:  # pragma: no cover - documented dependency
    serial = None


def yaw_to_quat(yaw: float):
    return 0.0, 0.0, math.sin(yaw / 2), math.cos(yaw / 2)


class SerialBridge(Node):
    def __init__(self):
        super().__init__("chotu_serial_bridge")
        self.declare_parameter("port", "/dev/ttyUSB0")
        self.declare_parameter("baud", 115200)
        self.declare_parameter("heartbeat_hz", 10.0)
        self.declare_parameter("odom_frame", "odom")
        self.declare_parameter("base_frame", "base_footprint")
        port = self.get_parameter("port").value
        baud = self.get_parameter("baud").value
        if serial is None:
            raise RuntimeError("pyserial missing: pip install pyserial")
        self.ser = serial.Serial(port, baud, timeout=0)
        self.get_logger().info(f"ESP32 link on {port} @ {baud}")

        r = DEFAULT_CONFIG.robot
        self.drive = DiffDrive(r.wheel_base, r.wheel_radius, r.encoder_ticks_per_rev)
        room = DEFAULT_CONFIG.room
        self.odom = FusedOdometry(self.drive, Pose2D(room.dock_x, room.dock_y, room.dock_theta))
        self.enc = P.Encoder()
        self.dec = P.StreamDecoder()
        self.prev_ticks = None
        self.prev_t_ms = None
        self.sensors = DEFAULT_CONFIG.sensors

        self.odom_pub = self.create_publisher(Odometry, "odom", 10)
        self.imu_pub = self.create_publisher(Imu, "imu", qos_profile_sensor_data)
        self.bump_pub = self.create_publisher(Bool, "chotu/bump", 10)
        self.cliff_pub = self.create_publisher(Bool, "chotu/cliff", 10)
        self.batt_pub = self.create_publisher(BatteryState, "battery_state", 10)
        self.range_pubs = {name: self.create_publisher(Range, f"range/{name}", qos_profile_sensor_data)
                           for name in ("left", "center", "right", "tof")}
        self.tf = TransformBroadcaster(self)

        self.create_subscription(Twist, "cmd_vel", self.on_cmd_vel, 10)
        self.create_subscription(Actuators, "chotu/actuators", self.on_actuators, 10)
        self.create_subscription(Bool, "chotu/estop", self.on_estop, 10)
        self.create_timer(0.005, self.poll_serial)
        self.create_timer(1.0 / self.get_parameter("heartbeat_hz").value, self.heartbeat)

    # ------------------------------------------------------------ Pi -> ESP32
    def on_cmd_vel(self, msg: Twist):
        self.ser.write(self.enc.cmd_vel(msg.linear.x, msg.angular.z))

    def on_actuators(self, msg: Actuators):
        self.ser.write(self.enc.actuators(msg.suction, msg.brush))

    def on_estop(self, msg: Bool):
        self.ser.write(self.enc.estop(msg.data))

    def heartbeat(self):
        self.ser.write(self.enc.heartbeat())

    # ------------------------------------------------------------ ESP32 -> Pi
    def poll_serial(self):
        data = self.ser.read(self.ser.in_waiting or 1)
        for payload in self.dec.feed(data):
            msg_id, _seq, body = P.parse_payload(payload)
            if msg_id == P.MSG_TELEMETRY:
                self.on_telemetry(body)

    def on_telemetry(self, t: P.Telemetry):
        now = self.get_clock().now().to_msg()
        if self.prev_ticks is None:
            self.prev_ticks, self.prev_t_ms = (t.ticks_left, t.ticks_right), t.t_ms
            return
        dt = max(1e-3, (t.t_ms - self.prev_t_ms) / 1000.0)
        dl = t.ticks_left - self.prev_ticks[0]
        dr = t.ticks_right - self.prev_ticks[1]
        self.prev_ticks, self.prev_t_ms = (t.ticks_left, t.ticks_right), t.t_ms
        pose = self.odom.update(dl, dr, t.gyro_z, dt)
        v = (dl + dr) / 2 * self.drive.metres_per_tick / dt

        q = yaw_to_quat(pose.theta)
        odom = Odometry()
        odom.header.stamp = now
        odom.header.frame_id = self.get_parameter("odom_frame").value
        odom.child_frame_id = self.get_parameter("base_frame").value
        odom.pose.pose.position.x, odom.pose.pose.position.y = pose.x, pose.y
        (odom.pose.pose.orientation.x, odom.pose.pose.orientation.y,
         odom.pose.pose.orientation.z, odom.pose.pose.orientation.w) = q
        odom.twist.twist.linear.x = v
        odom.twist.twist.angular.z = t.gyro_z
        self.odom_pub.publish(odom)

        tf = TransformStamped()
        tf.header = odom.header
        tf.child_frame_id = odom.child_frame_id
        tf.transform.translation.x, tf.transform.translation.y = pose.x, pose.y
        (tf.transform.rotation.x, tf.transform.rotation.y,
         tf.transform.rotation.z, tf.transform.rotation.w) = q
        self.tf.sendTransform(tf)

        imu = Imu()
        imu.header.stamp = now
        imu.header.frame_id = "imu_link"
        imu.angular_velocity.z = t.gyro_z
        imu.orientation_covariance[0] = -1.0
        self.imu_pub.publish(imu)

        s = self.sensors
        for name, dist, mx, fov in (("left", t.us_left, s.ultrasonic_max, s.ultrasonic_cone_deg),
                                    ("center", t.us_centre, s.ultrasonic_max, s.ultrasonic_cone_deg),
                                    ("right", t.us_right, s.ultrasonic_max, s.ultrasonic_cone_deg),
                                    ("tof", t.tof, s.tof_max, 2.0)):
            r = Range()
            r.header.stamp = now
            r.header.frame_id = "tof_link" if name == "tof" else f"us_{name}_link"
            r.radiation_type = Range.INFRARED if name == "tof" else Range.ULTRASOUND
            r.field_of_view = math.radians(fov)
            r.min_range, r.max_range = 0.02, mx
            r.range = float(dist)
            self.range_pubs[name].publish(r)

        self.bump_pub.publish(Bool(data=t.bump))
        self.cliff_pub.publish(Bool(data=t.cliff))
        b = BatteryState()
        b.header.stamp = now
        b.voltage = t.battery_v
        b.percentage = max(0.0, min(1.0, (t.battery_v - 9.9) / 2.7))
        b.present = True
        self.batt_pub.publish(b)
        if t.flags & P.FLAG_WATCHDOG:
            self.get_logger().warn("ESP32 watchdog active - motors stopped", throttle_duration_sec=2.0)


def main(args=None):
    rclpy.init(args=args)
    node = SerialBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.ser.write(node.enc.cmd_vel(0.0, 0.0))
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
