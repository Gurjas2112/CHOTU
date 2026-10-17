"""/api/v1: rooms, mission history, fleet summary, alerts."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from .. import schemas
from ..deps import repo
from ..repositories import Repository

router = APIRouter(tags=["history"])


@router.get("/rooms", response_model=List[schemas.Room])
def list_rooms(r: Repository = Depends(repo)):
    return r.list_rooms()


@router.get("/missions", response_model=schemas.MissionPage)
def list_missions(robot_id: Optional[str] = None, limit: int = Query(20, ge=1, le=200),
                  offset: int = Query(0, ge=0), r: Repository = Depends(repo)):
    total, items = r.list_missions(robot_id, limit, offset)
    return {"total": total, "limit": limit, "offset": offset, "items": items}


@router.get("/missions/{mission_id}", response_model=schemas.Mission)
def get_mission(mission_id: str, r: Repository = Depends(repo)):
    m = r.get_mission(mission_id)
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"mission {mission_id!r} not found")
    return m


@router.get("/fleet/summary", response_model=schemas.FleetSummary)
def fleet_summary(r: Repository = Depends(repo)):
    return r.fleet_summary()


@router.get("/alerts", response_model=List[schemas.Alert])
def list_alerts(robot_id: Optional[str] = None, unresolved: bool = False, r: Repository = Depends(repo)):
    return r.list_alerts(robot_id, unresolved)


@router.post("/alerts/{alert_id}/resolve", response_model=schemas.Alert)
def resolve_alert(alert_id: str, r: Repository = Depends(repo)):
    a = r.resolve_alert(alert_id)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"alert {alert_id!r} not found")
    return a
