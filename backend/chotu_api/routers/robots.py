"""/api/v1/robots: fleet, live status, commands, schedules, no-go zones."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Response, status

from .. import schemas
from ..deps import link, repo, robot_or_404
from ..repositories import Repository
from ..services.robot_link import RobotLink

router = APIRouter(prefix="/robots", tags=["robots"])


@router.get("", response_model=List[schemas.Robot])
def list_robots(r: Repository = Depends(repo)):
    return r.list_robots()


@router.get("/{robot_id}", response_model=schemas.RobotStatus)
def robot_status(robot: dict = Depends(robot_or_404), lk: RobotLink = Depends(link)):
    return {"robot": robot, "online": lk.online(robot["id"]), "link": lk.kind,
            "telemetry": lk.latest(robot["id"])}


@router.post("/{robot_id}/commands", response_model=schemas.CommandResult)
async def command(body: schemas.CommandIn, robot: dict = Depends(robot_or_404), lk: RobotLink = Depends(link)):
    ok, message, ros = await lk.send_command(robot["id"], body.action, body.model_dump())
    if not ok and "offline" in message:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, message)
    return {"accepted": ok, "message": message, "rosbridge": ros}


# ---- schedules
@router.get("/{robot_id}/schedules", response_model=List[schemas.Schedule])
def list_schedules(robot: dict = Depends(robot_or_404), r: Repository = Depends(repo)):
    return r.list_schedules(robot["id"])


@router.post("/{robot_id}/schedules", response_model=schemas.Schedule, status_code=status.HTTP_201_CREATED)
def add_schedule(body: schemas.ScheduleIn, robot: dict = Depends(robot_or_404), r: Repository = Depends(repo)):
    return r.add_schedule(robot["id"], body.model_dump())


@router.put("/{robot_id}/schedules/{schedule_id}", response_model=schemas.Schedule)
def update_schedule(schedule_id: str, body: schemas.ScheduleIn, robot: dict = Depends(robot_or_404),
                    r: Repository = Depends(repo)):
    row = r.update_schedule(robot["id"], schedule_id, body.model_dump())
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"schedule {schedule_id!r} not found")
    return row


@router.delete("/{robot_id}/schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule(schedule_id: str, robot: dict = Depends(robot_or_404), r: Repository = Depends(repo)):
    if not r.delete_schedule(robot["id"], schedule_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"schedule {schedule_id!r} not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---- no-go zones (replace-all, then pushed to the robot's /chotu/set_zones)
@router.get("/{robot_id}/zones", response_model=List[schemas.Zone])
def list_zones(robot: dict = Depends(robot_or_404), r: Repository = Depends(repo)):
    return r.list_zones(robot["id"])


@router.put("/{robot_id}/zones", response_model=List[schemas.Zone])
async def replace_zones(body: List[schemas.ZoneIn], robot: dict = Depends(robot_or_404),
                        r: Repository = Depends(repo), lk: RobotLink = Depends(link)):
    zones = [z.model_dump() for z in body]
    saved = r.replace_zones(robot["id"], zones)
    await lk.send_command(robot["id"], "set_zones", {"zones": zones})   # robot offline -> applied on next mission
    return saved


# ---- mission upload (robot or app posts its report when DOCKED)
@router.post("/{robot_id}/missions", response_model=schemas.Mission, status_code=status.HTTP_201_CREATED)
def upload_mission(body: schemas.MissionIn, robot: dict = Depends(robot_or_404), r: Repository = Depends(repo)):
    data = body.model_dump()
    data["robot_id"] = robot["id"]
    return r.add_mission(data)
