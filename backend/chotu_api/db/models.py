"""SQLAlchemy 2.x ORM tables. migrations/001_init.sql is the same schema as
hand-written PostgreSQL DDL; tests assert the two stay in sync."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# JSONB on PostgreSQL, plain JSON elsewhere (SQLite in tests)
Json = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


class RoomRow(Base):
    __tablename__ = "rooms"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    width_m: Mapped[float] = mapped_column(Float)
    height_m: Mapped[float] = mapped_column(Float)
    dock: Mapped[dict] = mapped_column(Json)


class RobotRow(Base):
    __tablename__ = "robots"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"))
    firmware: Mapped[str] = mapped_column(String(32))
    software: Mapped[str] = mapped_column(String(32))
    endpoint: Mapped[str] = mapped_column(String(256))


class MissionRow(Base):
    __tablename__ = "missions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    robot_id: Mapped[str] = mapped_column(ForeignKey("robots.id"), index=True)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"))
    started_at: Mapped[str] = mapped_column(String(32), index=True)   # ISO-8601 UTC
    ended_at: Mapped[str] = mapped_column(String(32))
    trigger: Mapped[str] = mapped_column(String(16))
    source: Mapped[str] = mapped_column(String(16))
    sim_seed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    docked: Mapped[bool] = mapped_column(Boolean)
    duration_s: Mapped[float] = mapped_column(Float)
    coverage: Mapped[float] = mapped_column(Float)
    debris_g: Mapped[float] = mapped_column(Float)
    debris_spawned_g: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    energy_wh: Mapped[float] = mapped_column(Float)
    avg_power_w: Mapped[float] = mapped_column(Float)
    eco_energy_saving_pct: Mapped[float] = mapped_column(Float)
    collisions: Mapped[int] = mapped_column(Integer)
    cable_incidents: Mapped[int] = mapped_column(Integer)
    recoveries: Mapped[int] = mapped_column(Integer)
    dock_error_m: Mapped[float] = mapped_column(Float)
    efficiency_by_type: Mapped[dict] = mapped_column(Json)
    rubric: Mapped[dict] = mapped_column(Json)
    score: Mapped[float] = mapped_column(Float)
    no_go_zones: Mapped[int] = mapped_column(Integer, default=0)


class ScheduleRow(Base):
    __tablename__ = "schedules"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    robot_id: Mapped[str] = mapped_column(ForeignKey("robots.id"), index=True)
    time: Mapped[str] = mapped_column(String(5))                       # HH:MM local
    days: Mapped[list] = mapped_column(Json)                           # [1..7]
    label: Mapped[str] = mapped_column(String(64))
    enabled: Mapped[bool] = mapped_column(Boolean)


class ZoneRow(Base):
    __tablename__ = "zones"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    robot_id: Mapped[str] = mapped_column(ForeignKey("robots.id"), index=True)
    label: Mapped[str] = mapped_column(String(64))
    x0: Mapped[float] = mapped_column(Float)
    y0: Mapped[float] = mapped_column(Float)
    x1: Mapped[float] = mapped_column(Float)
    y1: Mapped[float] = mapped_column(Float)


class AlertRow(Base):
    __tablename__ = "alerts"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    robot_id: Mapped[str] = mapped_column(ForeignKey("robots.id"), index=True)
    mission_id: Mapped[Optional[str]] = mapped_column(ForeignKey("missions.id"), nullable=True)
    level: Mapped[str] = mapped_column(String(16))
    code: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(128))
    body: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[str] = mapped_column(String(32), index=True)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)


# sample_data file -> table, in foreign-key order
TABLES = (("rooms.json", RoomRow), ("robots.json", RobotRow), ("missions.json", MissionRow),
          ("schedules.json", ScheduleRow), ("zones.json", ZoneRow), ("alerts.json", AlertRow))


def to_dict(row: Base) -> dict:
    return {c.key: getattr(row, c.key) for c in row.__table__.columns}
