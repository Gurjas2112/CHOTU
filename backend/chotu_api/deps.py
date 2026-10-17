"""FastAPI dependencies: store, robot link, API-key guard."""
from __future__ import annotations

import hmac

from fastapi import Depends, Header, HTTPException, Request, WebSocket, status

from .repositories import Repository
from .services.robot_link import RobotLink


def repo(request: Request) -> Repository:
    return request.app.state.repo


def link(request: Request) -> RobotLink:
    return request.app.state.link


def key_ok(expected: str, given: str | None) -> bool:
    return not expected or (given is not None and hmac.compare_digest(expected, given))


def require_key(request: Request, x_api_key: str | None = Header(default=None)) -> None:
    if not key_ok(request.app.state.settings.api_key, x_api_key):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing or wrong X-API-Key")


def robot_or_404(robot_id: str, r: Repository = Depends(repo)) -> dict:
    robot = r.get_robot(robot_id)
    if robot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"robot {robot_id!r} not found")
    return robot


def ws_key_ok(ws: WebSocket) -> bool:
    # browsers cannot set headers on a WebSocket, so the key may also come as ?api_key=
    given = ws.headers.get("x-api-key") or ws.query_params.get("api_key")
    return key_ok(ws.app.state.settings.api_key, given)
