"""chotu_core - hardware-independent autonomy library for CHOTU.

Compact Home Operations & Tidying Unit - Team Hack O' Giants, AtomQuest 2025.
Used unchanged by the ROS 2 nodes (``ros2_ws``) and the simulator
(``bot_simulation``).
"""
from .autonomy import CleaningMission, Command, Observation
from .config import DEFAULT_CONFIG, ChotuConfig
from .kinematics import DiffDrive, FusedOdometry, Pose2D
from .mission_fsm import MissionState

__all__ = ["CleaningMission", "Command", "Observation", "ChotuConfig", "DEFAULT_CONFIG",
           "DiffDrive", "FusedOdometry", "Pose2D", "MissionState"]
__version__ = "2.0.0"
