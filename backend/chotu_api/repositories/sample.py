"""In-memory store seeded from sample_data/*.json. Writes live until the process
exits; nothing touches a database or the JSON files."""
from __future__ import annotations

import copy
import json
import os
import threading
from typing import List, Optional, Tuple

from .base import Repository, next_id


class SampleRepository(Repository):
    def __init__(self, sample_dir: str):
        def load(name: str):
            with open(os.path.join(sample_dir, name), encoding="utf-8") as f:
                return json.load(f)

        self._lock = threading.Lock()
        self.robots = load("robots.json")
        self.rooms = load("rooms.json")
        self.missions = load("missions.json")
        self.schedules = load("schedules.json")
        self.zones = load("zones.json")
        self.alerts = load("alerts.json")

    # robots and rooms
    def list_robots(self) -> List[dict]:
        return copy.deepcopy(self.robots)

    def get_robot(self, robot_id: str) -> Optional[dict]:
        return next((copy.deepcopy(r) for r in self.robots if r["id"] == robot_id), None)

    def list_rooms(self) -> List[dict]:
        return copy.deepcopy(self.rooms)

    # missions (newest first)
    def list_missions(self, robot_id, limit, offset) -> Tuple[int, List[dict]]:
        rows = [m for m in self.missions if robot_id is None or m["robot_id"] == robot_id]
        rows.sort(key=lambda m: m["started_at"], reverse=True)
        return len(rows), copy.deepcopy(rows[offset:offset + limit])

    def get_mission(self, mission_id):
        return next((copy.deepcopy(m) for m in self.missions if m["id"] == mission_id), None)

    def add_mission(self, mission):
        with self._lock:
            row = dict(mission, id=next_id("m", [m["id"] for m in self.missions]))
            self.missions.append(row)
            return copy.deepcopy(row)

    # schedules
    def list_schedules(self, robot_id):
        return [copy.deepcopy(s) for s in self.schedules if s["robot_id"] == robot_id]

    def add_schedule(self, robot_id, data):
        with self._lock:
            row = dict(data, id=next_id("s", [s["id"] for s in self.schedules]), robot_id=robot_id)
            self.schedules.append(row)
            return copy.deepcopy(row)

    def update_schedule(self, robot_id, schedule_id, data):
        with self._lock:
            for s in self.schedules:
                if s["id"] == schedule_id and s["robot_id"] == robot_id:
                    s.update(data)
                    return copy.deepcopy(s)
        return None

    def delete_schedule(self, robot_id, schedule_id):
        with self._lock:
            before = len(self.schedules)
            self.schedules = [s for s in self.schedules
                              if not (s["id"] == schedule_id and s["robot_id"] == robot_id)]
            return len(self.schedules) < before

    # zones
    def list_zones(self, robot_id):
        return [copy.deepcopy(z) for z in self.zones if z["robot_id"] == robot_id]

    def replace_zones(self, robot_id, zones):
        with self._lock:
            self.zones = [z for z in self.zones if z["robot_id"] != robot_id]
            out = []
            for z in zones:
                row = dict(z, id=next_id("z", [x["id"] for x in self.zones]), robot_id=robot_id)
                self.zones.append(row)
                out.append(copy.deepcopy(row))
            return out

    # alerts (newest first)
    def list_alerts(self, robot_id, unresolved_only):
        rows = [a for a in self.alerts
                if (robot_id is None or a["robot_id"] == robot_id) and not (unresolved_only and a["resolved"])]
        return copy.deepcopy(sorted(rows, key=lambda a: a["created_at"], reverse=True))

    def resolve_alert(self, alert_id):
        with self._lock:
            for a in self.alerts:
                if a["id"] == alert_id:
                    a["resolved"] = True
                    return copy.deepcopy(a)
        return None
