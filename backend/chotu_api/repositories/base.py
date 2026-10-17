"""Storage interface. Routers only talk to this, so swapping the sample store for
PostgreSQL is a configuration change (CHOTU_STORE=sql), not a code change."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple


class Repository(ABC):
    # robots and rooms
    @abstractmethod
    def list_robots(self) -> List[dict]: ...

    @abstractmethod
    def get_robot(self, robot_id: str) -> Optional[dict]: ...

    @abstractmethod
    def list_rooms(self) -> List[dict]: ...

    # missions
    @abstractmethod
    def list_missions(self, robot_id: Optional[str], limit: int, offset: int) -> Tuple[int, List[dict]]: ...

    @abstractmethod
    def get_mission(self, mission_id: str) -> Optional[dict]: ...

    @abstractmethod
    def add_mission(self, mission: dict) -> dict: ...

    # schedules
    @abstractmethod
    def list_schedules(self, robot_id: str) -> List[dict]: ...

    @abstractmethod
    def add_schedule(self, robot_id: str, data: dict) -> dict: ...

    @abstractmethod
    def update_schedule(self, robot_id: str, schedule_id: str, data: dict) -> Optional[dict]: ...

    @abstractmethod
    def delete_schedule(self, robot_id: str, schedule_id: str) -> bool: ...

    # no-go zones (replace-all, like the SetZones service on the robot)
    @abstractmethod
    def list_zones(self, robot_id: str) -> List[dict]: ...

    @abstractmethod
    def replace_zones(self, robot_id: str, zones: List[dict]) -> List[dict]: ...

    # alerts
    @abstractmethod
    def list_alerts(self, robot_id: Optional[str], unresolved_only: bool) -> List[dict]: ...

    @abstractmethod
    def resolve_alert(self, alert_id: str) -> Optional[dict]: ...

    # derived
    def fleet_summary(self) -> Dict[str, float]:
        _, ms = self.list_missions(None, limit=10 ** 9, offset=0)
        n = len(ms) or 1
        return {
            "robots": len(self.list_robots()),
            "missions": len(ms),
            "dock_success_rate": round(sum(m["docked"] for m in ms) / n, 4),
            "mean_coverage": round(sum(m["coverage"] for m in ms) / n, 4),
            "mean_score": round(sum(m["score"] for m in ms) / n, 2),
            "total_debris_g": round(sum(m["debris_g"] for m in ms), 1),
            "total_energy_wh": round(sum(m["energy_wh"] for m in ms), 2),
            "open_alerts": len(self.list_alerts(None, unresolved_only=True)),
        }


def next_id(prefix: str, existing: List[str]) -> str:
    """Sequential ids (m-0041, s-005 ...) matching the sample data format."""
    nums = [int(i.split("-")[-1]) for i in existing if i.startswith(prefix + "-") and i.split("-")[-1].isdigit()]
    width = max((len(i.split("-")[-1]) for i in existing if i.startswith(prefix + "-")), default=3)
    return f"{prefix}-{(max(nums) + 1) if nums else 1:0{width}d}"
