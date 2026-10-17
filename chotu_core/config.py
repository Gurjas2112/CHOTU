"""Central configuration for CHOTU.

Every number here is traceable to the AtomQuest 2025 documents in
``essential_docs`` (spec sheet, finale pitch, Round 3 rules, cost sheet) or
to the datasheets of the parts listed in the BOM.  ROS 2 nodes load the same
dataclasses and override fields from ``chotu_bringup/config/chotu_params.yaml``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Tuple

FT = 0.3048  # metres per foot


@dataclass(frozen=True)
class RobotConfig:
    # Geometry - round MDF chassis, must fit 1.5 ft x 1.5 ft x 1 ft (Round 3 rules)
    radius: float = 0.17                 # m  (Ø 34 cm  < 45.7 cm limit)
    height: float = 0.22                 # m  (< 30.5 cm limit)
    wheel_base: float = 0.26             # m  centre-to-centre of the two BO wheels
    wheel_radius: float = 0.0325         # m  65 mm BO wheel
    encoder_ticks_per_rev: int = 20      # 20-slot encoder disc (Bill-1 combo)
    # Motion limits (spec sheet: ~0.25 m/s max coverage speed)
    max_linear: float = 0.25             # m/s
    max_angular: float = 1.8             # rad/s
    max_linear_accel: float = 0.6        # m/s^2
    # Cleaning head - side brush + Bergmann tornado nozzle
    cleaning_width: float = 0.24         # m  swept width
    dust_capacity_ml: float = 470.0      # spec sheet


@dataclass(frozen=True)
class SensorConfig:
    # 3 x HC-SR04 (left / centre / right), mounted on the chassis rim
    ultrasonic_angles_deg: Tuple[float, ...] = (35.0, 0.0, -35.0)
    ultrasonic_min: float = 0.02
    ultrasonic_max: float = 1.50         # spec sheet: effective 2-150 cm
    ultrasonic_cone_deg: float = 15.0
    ultrasonic_noise: float = 0.01
    # VL53L0X time-of-flight "LiDAR", forward-facing
    tof_angle_deg: float = 0.0
    tof_max: float = 1.20
    tof_noise: float = 0.005
    # Camera (Pi camera 5MP / ESP32-S3 OV2640) for YOLOv8n suck/avoid
    camera_fov_deg: float = 62.0
    camera_range: float = 1.10
    # Range sensors cannot see objects lower than this (cables, flat wrappers)
    range_sensor_mount_height: float = 0.06


@dataclass(frozen=True)
class RoomConfig:
    # Finale pitch: "designed for 10-12 ft rooms". Default 10 ft x 10 ft.
    width: float = 10 * FT
    height: float = 10 * FT
    # Docking station centred on the bottom wall; robot leaves facing +y
    dock_x: float = 5 * FT
    dock_y: float = 0.19
    dock_theta: float = math.pi / 2


@dataclass(frozen=True)
class MissionConfig:
    time_budget_s: float = 300.0         # Round 3 rules: 5 minute session
    return_margin_s: float = 14.0        # safety margin before the deadline
    control_rate_hz: float = 20.0
    grid_resolution: float = 0.05        # m per occupancy cell
    lane_spacing: float = 0.22           # < cleaning width -> 2 cm overlap
    waypoint_step: float = 0.30          # granularity of lane waypoints
    wall_margin: float = 0.24            # first/last lane offset from walls
    inflation_margin: float = 0.02       # extra clearance on top of robot radius
    undock_distance: float = 0.45
    scan_turn_rate: float = 1.4          # rad/s for the 360° mapping scan
    waypoint_tolerance: float = 0.10
    stop_distance: float = 0.05          # reactive stop (from chassis edge)
    slow_distance: float = 0.12
    stuck_timeout_s: float = 1.5
    max_recoveries_per_target: int = 2
    min_frontier_cells: int = 5
    spot_clean_radius: float = 0.12


@dataclass(frozen=True)
class GarbageType:
    name: str
    mass_g: float          # mass of one item / pile
    pickup_eff: float      # probability of pick-up at 100 % suction
    colour_bgr: Tuple[int, int, int]


# Garbage types listed in the AtomQuest problem statement
GARBAGE_TYPES: Dict[str, GarbageType] = {
    "dust":        GarbageType("dust", 0.5, 0.97, (90, 200, 255)),
    "hair":        GarbageType("hair", 0.2, 0.88, (200, 120, 255)),
    "paper":       GarbageType("paper", 1.0, 0.93, (255, 255, 255)),
    "wrapper":     GarbageType("wrapper", 2.0, 0.85, (60, 220, 120)),
    "wire_strand": GarbageType("wire_strand", 0.8, 0.78, (40, 160, 255)),
}


@dataclass(frozen=True)
class PowerConfig:
    """Finale pitch battery: 3S4P Li-ion, 11.1 V, ~10 Ah (111 Wh)."""
    nominal_voltage: float = 11.1
    capacity_ah: float = 10.0
    usable_fraction: float = 0.85        # pitch: 80-85 % efficiency
    pi4_w: float = 6.4                   # Raspberry Pi 4 under YOLO load
    esp32_w: float = 0.8
    sensors_w: float = 0.6
    drive_w_at_full: float = 6.0         # 2 x BO motor at 0.25 m/s
    vacuum_w_at_full: float = 36.0       # Bergmann 12 V tornado motor (rated 60 W)
    brush_w: float = 3.0


@dataclass(frozen=True)
class ChotuConfig:
    robot: RobotConfig = field(default_factory=RobotConfig)
    sensors: SensorConfig = field(default_factory=SensorConfig)
    room: RoomConfig = field(default_factory=RoomConfig)
    mission: MissionConfig = field(default_factory=MissionConfig)
    power: PowerConfig = field(default_factory=PowerConfig)


DEFAULT_CONFIG = ChotuConfig()

# Prototype bill of materials for the hybrid Pi 4 + ESP32-S3 build
# (itemised in essential_docs/HARDWARE_SOFTWARE_REQUIREMENTS.md).
PROTOTYPE_BOM_INR = 11480
