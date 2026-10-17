"""AI vision: "suck vs avoid" object classification (VLM-Vac inspired).

The VLM-Vac paper (essential_docs/essential_research_paper_docs) fine-tunes
YOLOv8n on two *actionable* classes - things to vacuum and things to avoid.
CHOTU follows the same idea:

* ``suck``  -> dust, hair, paper, wrapper, wire strands: boost suction, add a
  spot-clean waypoint.
* ``avoid`` -> power cables, socks, cloth, liquids, toys: these are too low or
  soft for the ultrasonic / ToF sensors, so they are painted into the map
  as permanent keep-out zones.

``YoloSuckAvoidDetector`` runs on the Raspberry Pi 4 (CPU, ~4-6 FPS at
320 px) or on the RTX 3060 dev machine (CUDA) and projects bounding boxes to
floor coordinates with a calibrated pinhole model.  ``MockDetector`` is used
by the simulation and the unit tests, so no GPU/ultralytics is needed there.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple

from .kinematics import Pose2D

SUCK_CLASSES = {"dust", "hair", "paper", "wrapper", "wire_strand", "crumbs"}
AVOID_CLASSES = {"power_cable", "sock", "cloth", "liquid", "toy", "pet_waste", "charger"}
# Fallback when only the stock COCO yolov8n.pt is available
COCO_AVOID = {"chair", "couch", "bed", "dining table", "potted plant", "person",
              "dog", "cat", "backpack", "handbag", "suitcase", "bottle", "cup"}


def action_for(label: str) -> Optional[str]:
    if label in SUCK_CLASSES:
        return "suck"
    if label in AVOID_CLASSES or label in COCO_AVOID:
        return "avoid"
    return None


@dataclass
class Detection:
    label: str
    action: str          # suck | avoid
    confidence: float
    x: float             # world / odom frame (m)
    y: float
    radius: float = 0.05


@dataclass
class CameraModel:
    """Pinhole camera looking forward and tilted down at the floor."""
    width: int = 640
    height: int = 480
    hfov_deg: float = 62.0
    mount_height: float = 0.16     # m above floor
    tilt_deg: float = 28.0         # downward pitch
    forward_offset: float = 0.15   # m ahead of the wheel axle

    @property
    def fx(self) -> float:
        return (self.width / 2) / math.tan(math.radians(self.hfov_deg) / 2)

    def pixel_to_floor(self, u: float, v: float) -> Optional[Tuple[float, float]]:
        """Return (forward, left) metres in the robot frame, or None above horizon."""
        f = self.fx
        x_c = (u - self.width / 2) / f      # right
        y_c = (v - self.height / 2) / f     # down
        tilt = math.radians(self.tilt_deg)
        # ray in robot frame (forward, left, up)
        fwd = math.cos(tilt) - y_c * math.sin(tilt)
        up = -math.sin(tilt) - y_c * math.cos(tilt)
        left = -x_c
        if up >= -1e-6:
            return None
        s = self.mount_height / -up
        return self.forward_offset + s * fwd, s * left


def to_world(pose: Pose2D, forward: float, left: float) -> Tuple[float, float]:
    c, s = math.cos(pose.theta), math.sin(pose.theta)
    return pose.x + c * forward - s * left, pose.y + s * forward + c * left


class YoloSuckAvoidDetector:
    """Ultralytics YOLOv8n wrapper (imported lazily so the core stays light)."""

    def __init__(self, weights: str = "models/chotu_suck_avoid_yolov8n.pt",
                 conf: float = 0.35, imgsz: int = 320, device: Optional[str] = None,
                 camera: CameraModel = CameraModel()):
        from ultralytics import YOLO  # noqa: WPS433 (optional dependency)
        self.model = YOLO(weights)
        self.conf = conf
        self.imgsz = imgsz
        self.device = device
        self.camera = camera

    def detect(self, image, pose: Pose2D) -> List[Detection]:
        res = self.model.predict(image, conf=self.conf, imgsz=self.imgsz,
                                 device=self.device, verbose=False)[0]
        names = res.names
        out: List[Detection] = []
        for box, cls, conf in zip(res.boxes.xyxy.tolist(), res.boxes.cls.tolist(),
                                  res.boxes.conf.tolist()):
            label = names[int(cls)]
            action = action_for(label)
            if action is None:
                continue
            x1, y1, x2, y2 = box
            sx = self.camera.width / res.orig_shape[1]
            sy = self.camera.height / res.orig_shape[0]
            floor = self.camera.pixel_to_floor((x1 + x2) / 2 * sx, y2 * sy)
            if floor is None:
                continue
            wx, wy = to_world(pose, *floor)
            width_m = abs(floor[0]) * (x2 - x1) * sx / self.camera.fx
            out.append(Detection(label, action, float(conf), wx, wy,
                                 radius=max(0.04, min(0.4, width_m / 2))))
        return out


class MockDetector:
    """Ground-truth driven detector with range-dependent recall (sim/tests)."""

    def __init__(self, fov_deg: float = 62.0, max_range: float = 1.1,
                 recall_near: float = 0.95, recall_far: float = 0.6,
                 pos_noise: float = 0.02, rng=None):
        import random
        self.half_fov = math.radians(fov_deg) / 2
        self.max_range = max_range
        self.recall_near = recall_near
        self.recall_far = recall_far
        self.pos_noise = pos_noise
        self.rng = rng or random.Random(7)

    def detect(self, pose: Pose2D,
               objects: Iterable[Tuple[str, float, float, float]]) -> List[Detection]:
        """``objects``: (label, x, y, radius) ground truth items on the floor."""
        out: List[Detection] = []
        for label, x, y, r in objects:
            dx, dy = x - pose.x, y - pose.y
            d = math.hypot(dx, dy)
            if d > self.max_range or d < 0.08:
                continue
            bearing = math.atan2(dy, dx) - pose.theta
            bearing = math.atan2(math.sin(bearing), math.cos(bearing))
            if abs(bearing) > self.half_fov:
                continue
            recall = self.recall_near + (self.recall_far - self.recall_near) * d / self.max_range
            if self.rng.random() > recall:
                continue
            action = action_for(label)
            if action is None:
                continue
            out.append(Detection(label, action, round(0.5 + 0.5 * recall, 2),
                                 x + self.rng.gauss(0, self.pos_noise),
                                 y + self.rng.gauss(0, self.pos_noise), r))
        return out


def debris_ahead(dets: Sequence[Detection], pose: Pose2D, distance: float = 0.55) -> int:
    n = 0
    for d in dets:
        if d.action != "suck":
            continue
        dx, dy = d.x - pose.x, d.y - pose.y
        fwd = dx * math.cos(pose.theta) + dy * math.sin(pose.theta)
        lat = -dx * math.sin(pose.theta) + dy * math.cos(pose.theta)
        if 0 < fwd < distance and abs(lat) < 0.2:
            n += 1
    return n
