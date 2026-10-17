"""SQLAlchemy-backed store (PostgreSQL in production, SQLite in tests)."""
from __future__ import annotations

from typing import List, Optional, Tuple

from sqlalchemy import func, select

from ..db.models import AlertRow, MissionRow, RobotRow, RoomRow, ScheduleRow, ZoneRow, to_dict
from .base import Repository, next_id


class SqlRepository(Repository):
    def __init__(self, session_factory):
        self.sf = session_factory

    # robots and rooms
    def list_robots(self) -> List[dict]:
        with self.sf() as s:
            return [to_dict(r) for r in s.scalars(select(RobotRow).order_by(RobotRow.id))]

    def get_robot(self, robot_id: str) -> Optional[dict]:
        with self.sf() as s:
            r = s.get(RobotRow, robot_id)
            return to_dict(r) if r else None

    def list_rooms(self) -> List[dict]:
        with self.sf() as s:
            return [to_dict(r) for r in s.scalars(select(RoomRow).order_by(RoomRow.id))]

    # missions
    def list_missions(self, robot_id, limit, offset) -> Tuple[int, List[dict]]:
        with self.sf() as s:
            q = select(MissionRow)
            c = select(func.count()).select_from(MissionRow)
            if robot_id is not None:
                q = q.where(MissionRow.robot_id == robot_id)
                c = c.where(MissionRow.robot_id == robot_id)
            q = q.order_by(MissionRow.started_at.desc()).limit(limit).offset(offset)
            return s.scalar(c), [to_dict(r) for r in s.scalars(q)]

    def get_mission(self, mission_id):
        with self.sf() as s:
            r = s.get(MissionRow, mission_id)
            return to_dict(r) if r else None

    def add_mission(self, mission):
        with self.sf.begin() as s:
            ids = list(s.scalars(select(MissionRow.id)))
            row = MissionRow(**dict(mission, id=next_id("m", ids)))
            s.add(row)
            s.flush()
            return to_dict(row)

    # schedules
    def list_schedules(self, robot_id):
        with self.sf() as s:
            q = select(ScheduleRow).where(ScheduleRow.robot_id == robot_id).order_by(ScheduleRow.id)
            return [to_dict(r) for r in s.scalars(q)]

    def add_schedule(self, robot_id, data):
        with self.sf.begin() as s:
            ids = list(s.scalars(select(ScheduleRow.id)))
            row = ScheduleRow(**dict(data, id=next_id("s", ids), robot_id=robot_id))
            s.add(row)
            s.flush()
            return to_dict(row)

    def update_schedule(self, robot_id, schedule_id, data):
        with self.sf.begin() as s:
            row = s.get(ScheduleRow, schedule_id)
            if row is None or row.robot_id != robot_id:
                return None
            for k, v in data.items():
                setattr(row, k, v)
            s.flush()
            return to_dict(row)

    def delete_schedule(self, robot_id, schedule_id):
        with self.sf.begin() as s:
            row = s.get(ScheduleRow, schedule_id)
            if row is None or row.robot_id != robot_id:
                return False
            s.delete(row)
            return True

    # zones
    def list_zones(self, robot_id):
        with self.sf() as s:
            q = select(ZoneRow).where(ZoneRow.robot_id == robot_id).order_by(ZoneRow.id)
            return [to_dict(r) for r in s.scalars(q)]

    def replace_zones(self, robot_id, zones):
        with self.sf.begin() as s:
            for old in s.scalars(select(ZoneRow).where(ZoneRow.robot_id == robot_id)):
                s.delete(old)
            s.flush()
            ids = list(s.scalars(select(ZoneRow.id)))
            out = []
            for z in zones:
                zid = next_id("z", ids)
                ids.append(zid)
                row = ZoneRow(**dict(z, id=zid, robot_id=robot_id))
                s.add(row)
                out.append(row)
            s.flush()
            return [to_dict(r) for r in out]

    # alerts
    def list_alerts(self, robot_id, unresolved_only):
        with self.sf() as s:
            q = select(AlertRow)
            if robot_id is not None:
                q = q.where(AlertRow.robot_id == robot_id)
            if unresolved_only:
                q = q.where(AlertRow.resolved.is_(False))
            return [to_dict(r) for r in s.scalars(q.order_by(AlertRow.created_at.desc()))]

    def resolve_alert(self, alert_id):
        with self.sf.begin() as s:
            row = s.get(AlertRow, alert_id)
            if row is None:
                return None
            row.resolved = True
            s.flush()
            return to_dict(row)
