"""Wire contract shared by REST, WebSocket and the robot link (spec: backend/PROTOCOL.md).

Every WebSocket message, in both directions, is one JSON object:

    {"v": 1, "type": "<type>", "robot_id": "chotu-01", "seq": 42,
     "ts": "2026-10-17T10:30:00.000Z", "data": {...}}

Server -> client types: hello, telemetry, mission_event, alert, ack, error, pong
Client -> server types: command, ping
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict

PROTOCOL_VERSION = 1

SERVER_TYPES = ("hello", "telemetry", "mission_event", "alert", "ack", "error", "pong")
CLIENT_TYPES = ("command", "ping")

# command.data.action values and the rosbridge call each one becomes on the robot
COMMANDS = {
    "start_mission": {"op": "call_service", "service": "/chotu/start_mission",
                      "type": "chotu_interfaces/srv/StartMission"},
    "return_to_dock": {"op": "call_service", "service": "/chotu/start_mission",
                       "type": "chotu_interfaces/srv/StartMission"},       # abort=true -> request_dock
    "set_zones": {"op": "call_service", "service": "/chotu/set_zones",
                  "type": "chotu_interfaces/srv/SetZones"},
}

# ROS topics the backend subscribes to on each robot (rosbridge "subscribe", throttled)
SUBSCRIPTIONS = (
    {"topic": "/chotu/status", "type": "chotu_interfaces/msg/CleaningStatus", "throttle_rate": 1000},
    {"topic": "/odom", "type": "nav_msgs/msg/Odometry", "throttle_rate": 1000},
)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def envelope(type_: str, robot_id: str, seq: int, data: Dict[str, Any]) -> Dict[str, Any]:
    if type_ not in SERVER_TYPES:
        raise ValueError(f"unknown server message type {type_!r}")
    return {"v": PROTOCOL_VERSION, "type": type_, "robot_id": robot_id, "seq": seq,
            "ts": now_iso(), "data": data}


def validate_client(msg: Any) -> str:
    """Return '' if msg is a valid client envelope, else a human-readable reason."""
    if not isinstance(msg, dict):
        return "message must be a JSON object"
    if msg.get("v") != PROTOCOL_VERSION:
        return f"unsupported protocol version {msg.get('v')!r} (server speaks {PROTOCOL_VERSION})"
    if msg.get("type") not in CLIENT_TYPES:
        return f"unknown type {msg.get('type')!r}"
    if msg["type"] == "command":
        action = (msg.get("data") or {}).get("action")
        if action not in COMMANDS:
            return f"unknown command {action!r}; expected one of {sorted(COMMANDS)}"
    return ""


def to_rosbridge(action: str, data: Dict[str, Any], call_id: str) -> Dict[str, Any]:
    """Translate an app/backend command into a rosbridge v2 JSON message
    (field names are those of chotu_interfaces/srv/StartMission and SetZones)."""
    spec = COMMANDS[action]
    if action == "start_mission":
        args = {"abort": False, "time_budget_s": float(data.get("time_budget_s", 0.0))}
    elif action == "return_to_dock":
        args = {"abort": True, "time_budget_s": 0.0}
    else:  # set_zones
        args = {"no_go": [{"x_min": z["x0"], "y_min": z["y0"], "x_max": z["x1"], "y_max": z["y1"]}
                          for z in data.get("zones", [])]}
    return {"op": spec["op"], "id": call_id, "service": spec["service"], "type": spec["type"], "args": args}


def yaw_from_quaternion(q: Dict[str, Any]) -> float:
    x, y, z, w = (float(q.get(k, 0.0)) for k in ("x", "y", "z", "w"))
    return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))


def merge_rosbridge(prev: Dict[str, Any], msg: Dict[str, Any]) -> Dict[str, Any]:
    """Fold one rosbridge 'publish' (/chotu/status or /odom) into telemetry.data."""
    out = dict(prev) if prev else {"state": "IDLE", "coverage": 0.0, "battery_pct": 0.0,
                                   "suction_pct": 0, "pose": {"x": 0.0, "y": 0.0, "theta": 0.0}, "t": 0.0}
    m = msg.get("msg", {})
    if msg.get("topic") == "/chotu/status":
        out.update(state=m.get("state", "IDLE"),
                   coverage=round(float(m.get("coverage_estimate", 0.0)), 4),
                   battery_pct=round(100.0 * float(m.get("battery_soc", 0.0)), 2),
                   suction_pct=int(round(100.0 * float(m.get("suction_duty", 0.0)))),
                   t=float(m.get("elapsed_s", 0.0)))
    elif msg.get("topic") == "/odom":
        pose = m.get("pose", {}).get("pose", {})
        p = pose.get("position", {})
        out["pose"] = {"x": round(float(p.get("x", 0.0)), 3), "y": round(float(p.get("y", 0.0)), 3),
                       "theta": round(yaw_from_quaternion(pose.get("orientation", {})), 3)}
    return out
