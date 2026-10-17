"""YOLOv8n "suck / avoid" detector node (VLM-Vac inspired).

Subscribes  /camera/image_raw (sensor_msgs/Image), /odom
Publishes   /chotu/detections (chotu_interfaces/DetectionArray)
            /chotu/detections/image (annotated, optional)

Parameters
  weights   path to the fine-tuned model (training/train_suck_avoid.py);
            falls back to the stock COCO yolov8n.pt (avoid-only classes)
  device    "cpu" on the Raspberry Pi 4, "0" for the RTX 3060 dev machine
  imgsz     320 on the Pi (~4-6 FPS), 640 on GPU
  max_fps   rate limit so the Pi keeps CPU for the planner
"""
from __future__ import annotations

import math
import os
import time

import rclpy
from cv_bridge import CvBridge
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image

from chotu_core.kinematics import Pose2D
from chotu_core.perception import CameraModel, YoloSuckAvoidDetector
from chotu_interfaces.msg import Detection, DetectionArray


class YoloDetectorNode(Node):
    def __init__(self):
        super().__init__("chotu_yolo_detector")
        self.declare_parameter("weights", "models/chotu_suck_avoid_yolov8n.pt")
        self.declare_parameter("device", "cpu")
        self.declare_parameter("imgsz", 320)
        self.declare_parameter("conf", 0.35)
        self.declare_parameter("max_fps", 5.0)
        self.declare_parameter("publish_annotated", False)
        weights = self.get_parameter("weights").value
        if not os.path.exists(weights):
            self.get_logger().warn(f"{weights} not found - using stock yolov8n.pt (COCO avoid classes only)")
            weights = "yolov8n.pt"
        self.detector = YoloSuckAvoidDetector(weights, conf=self.get_parameter("conf").value,
                                              imgsz=self.get_parameter("imgsz").value,
                                              device=self.get_parameter("device").value,
                                              camera=CameraModel())
        self.bridge = CvBridge()
        self.pose = Pose2D()
        self.last_t = 0.0
        self.min_period = 1.0 / max(0.1, self.get_parameter("max_fps").value)
        self.pub = self.create_publisher(DetectionArray, "chotu/detections", 10)
        self.img_pub = self.create_publisher(Image, "chotu/detections/image", 2)
        self.create_subscription(Odometry, "odom", self.on_odom, 10)
        self.create_subscription(Image, "camera/image_raw", self.on_image, qos_profile_sensor_data)

    def on_odom(self, msg: Odometry):
        p, q = msg.pose.pose.position, msg.pose.pose.orientation
        self.pose = Pose2D(p.x, p.y, math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z)))

    def on_image(self, msg: Image):
        now = time.monotonic()
        if now - self.last_t < self.min_period:
            return
        self.last_t = now
        frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
        dets = self.detector.detect(frame, self.pose)
        out = DetectionArray()
        out.header = msg.header
        out.header.frame_id = "odom"
        for d in dets:
            m = Detection()
            m.label, m.action, m.confidence, m.radius = d.label, d.action, float(d.confidence), float(d.radius)
            m.position.x, m.position.y = float(d.x), float(d.y)
            out.detections.append(m)
        self.pub.publish(out)
        if self.get_parameter("publish_annotated").value:
            res = self.detector.model.predict(frame, imgsz=self.detector.imgsz, verbose=False)[0]
            self.img_pub.publish(self.bridge.cv2_to_imgmsg(res.plot(), encoding="bgr8"))


def main(args=None):
    rclpy.init(args=args)
    node = YoloDetectorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
