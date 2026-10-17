"""Pydantic models: the JSON shapes of the REST API (OpenAPI at /docs)."""
from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

MissionState = Literal["IDLE", "UNDOCK", "SCAN", "COVER", "SPOT_CLEAN", "STUCK_RECOVERY",
                       "RETURN_TO_DOCK", "DOCKING", "DOCKED"]


class Pose(BaseModel):
    x: float
    y: float
    theta: float = 0.0


class Room(BaseModel):
    id: str
    name: str
    width_m: float
    height_m: float
    dock: Pose


class Robot(BaseModel):
    id: str
    name: str
    room_id: str
    firmware: str
    software: str
    endpoint: str = Field(description="rosbridge WebSocket of the robot's Raspberry Pi")


class Telemetry(BaseModel):
    t: float = Field(description="seconds since mission start")
    state: MissionState
    coverage: float = Field(ge=0, le=1)
    battery_pct: float = Field(ge=0, le=100)
    suction_pct: int = Field(ge=0, le=100)
    pose: Pose


class RobotStatus(BaseModel):
    robot: Robot
    online: bool
    link: Literal["demo", "rosbridge"]
    telemetry: Optional[Telemetry] = None


class MissionIn(BaseModel):
    """Report a robot (or the app) uploads when a mission ends."""
    room_id: str
    started_at: str
    ended_at: str
    trigger: Literal["app", "schedule"]
    source: Literal["digital_twin", "gazebo", "robot"]
    sim_seed: Optional[int] = None
    docked: bool
    duration_s: float
    coverage: float
    debris_g: float
    debris_spawned_g: Optional[float] = None
    energy_wh: float
    avg_power_w: float
    eco_energy_saving_pct: float
    collisions: int
    cable_incidents: int
    recoveries: int
    dock_error_m: float
    efficiency_by_type: Dict[str, float]
    rubric: Dict[str, float]
    score: float
    no_go_zones: int = 0


class Mission(MissionIn):
    id: str
    robot_id: str


class MissionPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: List[Mission]


class FleetSummary(BaseModel):
    robots: int
    missions: int
    dock_success_rate: float
    mean_coverage: float
    mean_score: float
    total_debris_g: float
    total_energy_wh: float
    open_alerts: int


class ScheduleIn(BaseModel):
    time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$", examples=["10:30"])
    days: List[int] = Field(min_length=1, description="1 = Monday ... 7 = Sunday")
    label: str = "Full room"
    enabled: bool = True

    @field_validator("days")
    @classmethod
    def _days(cls, v: List[int]) -> List[int]:
        if any(d < 1 or d > 7 for d in v):
            raise ValueError("days must be 1..7")
        return sorted(set(v))


class Schedule(ScheduleIn):
    id: str
    robot_id: str


class ZoneIn(BaseModel):
    label: str = ""
    x0: float
    y0: float
    x1: float
    y1: float

    @model_validator(mode="after")
    def _ordered(self) -> "ZoneIn":
        if self.x1 <= self.x0 or self.y1 <= self.y0:
            raise ValueError("zone needs x0 < x1 and y0 < y1 (metres, room frame)")
        return self


class Zone(ZoneIn):
    id: str
    robot_id: str


class Alert(BaseModel):
    id: str
    robot_id: str
    mission_id: Optional[str] = None
    level: Literal["info", "warning", "critical"]
    code: str
    title: str
    body: str
    created_at: str
    resolved: bool = False


class CommandIn(BaseModel):
    action: Literal["start_mission", "return_to_dock"]
    time_budget_s: float = Field(0.0, ge=0, le=3600, description="0 = robot default (300 s)")


class CommandResult(BaseModel):
    accepted: bool
    message: str
    rosbridge: dict = Field(description="the exact rosbridge v2 message sent (or that would be sent) to the robot")
