import json
import os
import re

from chotu_api import protocol
from chotu_api.db.models import Base

MIGRATION = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "migrations", "001_init.sql")


def test_health_and_dashboard(client):
    h = client.get("/healthz").json()
    assert h["status"] == "ok" and h["protocol"] == protocol.PROTOCOL_VERSION
    assert "CHOTU" in client.get("/").text


def test_robots_and_live_status(client):
    robots = client.get("/api/v1/robots").json()
    assert [r["id"] for r in robots] == ["chotu-01", "chotu-02", "chotu-03", "chotu-04"]
    st = client.get("/api/v1/robots/chotu-02").json()
    assert st["online"] is True and st["link"] == "demo"
    assert st["telemetry"]["state"] in ("IDLE", "UNDOCK", "SCAN", "COVER", "SPOT_CLEAN", "STUCK_RECOVERY",
                                        "RETURN_TO_DOCK", "DOCKING", "DOCKED")
    assert client.get("/api/v1/robots/nope").status_code == 404


def test_missions_paging_and_summary(client):
    page = client.get("/api/v1/missions", params={"limit": 5}).json()
    assert page["total"] == 40 and len(page["items"]) == 5
    dates = [m["started_at"] for m in page["items"]]
    assert dates == sorted(dates, reverse=True)                      # newest first
    mine = client.get("/api/v1/missions", params={"robot_id": "chotu-03", "limit": 200}).json()
    assert mine["total"] == 10 and {m["robot_id"] for m in mine["items"]} == {"chotu-03"}
    s = client.get("/api/v1/fleet/summary").json()
    assert s["missions"] == 40 and s["dock_success_rate"] == 1.0
    assert abs(s["mean_score"] - 77.6) < 0.1                          # matches benchmark_40_rooms.json
    assert client.get("/api/v1/missions/m-0001").json()["sim_seed"] == 10


def test_mission_upload(client):
    m = client.get("/api/v1/missions/m-0002").json()
    body = {k: v for k, v in m.items() if k not in ("id", "robot_id")}
    body.update(source="robot", sim_seed=None, started_at="2026-12-01T09:00:00Z")
    new = client.post("/api/v1/robots/chotu-01/missions", json=body)
    assert new.status_code == 201 and new.json()["id"] == "m-0041" and new.json()["robot_id"] == "chotu-01"
    assert client.get("/api/v1/missions", params={"limit": 1}).json()["items"][0]["id"] == "m-0041"


def test_schedule_crud(client):
    base = "/api/v1/robots/chotu-01/schedules"
    assert len(client.get(base).json()) == 1
    s = client.post(base, json={"time": "07:45", "days": [7, 1, 1], "label": "Morning"}).json()
    assert s["days"] == [1, 7] and s["robot_id"] == "chotu-01"
    assert client.post(base, json={"time": "25:00", "days": [1]}).status_code == 422
    u = client.put(f"{base}/{s['id']}", json={"time": "08:00", "days": [2], "enabled": False}).json()
    assert u["time"] == "08:00" and u["enabled"] is False
    assert client.delete(f"{base}/{s['id']}").status_code == 204
    assert client.delete(f"{base}/{s['id']}").status_code == 404


def test_zones_replace_and_validation(client):
    base = "/api/v1/robots/chotu-02/zones"
    assert len(client.get(base).json()) == 1
    zs = [{"label": "Cables", "x0": 0.1, "y0": 0.1, "x1": 0.6, "y1": 0.5},
          {"label": "Desk", "x0": 2.0, "y0": 2.0, "x1": 2.9, "y1": 2.9}]
    out = client.put(base, json=zs).json()
    assert [z["label"] for z in out] == ["Cables", "Desk"]
    assert len(client.get(base).json()) == 2
    bad = [{"x0": 1.0, "y0": 1.0, "x1": 0.5, "y1": 2.0}]
    assert client.put(base, json=bad).status_code == 422


def test_alerts_resolve(client):
    open_ = client.get("/api/v1/alerts", params={"unresolved": True}).json()
    assert [a["code"] for a in open_] == ["BIN_FULL"]
    client.post(f"/api/v1/alerts/{open_[0]['id']}/resolve")
    assert client.get("/api/v1/alerts", params={"unresolved": True}).json() == []
    assert client.get("/api/v1/fleet/summary").json()["open_alerts"] == 0


def test_rest_command_returns_rosbridge_message(client):
    r = client.post("/api/v1/robots/chotu-01/commands", json={"action": "return_to_dock"}).json()
    assert r["accepted"] is True
    assert r["rosbridge"] == {"op": "call_service", "id": r["rosbridge"]["id"], "service": "/chotu/start_mission",
                              "type": "chotu_interfaces/srv/StartMission",
                              "args": {"abort": True, "time_budget_s": 0.0}}
    assert client.get("/api/v1/robots/chotu-01").json()["telemetry"]["state"] == "RETURN_TO_DOCK"


def test_websocket_protocol(client):
    with client.websocket_connect("/ws/v1/robots/chotu-01") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello" and hello["v"] == 1 and hello["data"]["online"] is True
        frames = [ws.receive_json() for _ in range(3)]
        assert all(f["robot_id"] == "chotu-01" for f in frames)
        tel = next(f for f in frames if f["type"] == "telemetry")["data"]
        assert set(tel) == {"t", "state", "coverage", "battery_pct", "suction_pct", "pose"}

        ws.send_text("not json")
        assert _next(ws, "error")["data"]["reason"] == "invalid JSON"
        ws.send_json({"v": 2, "type": "ping"})
        assert "version" in _next(ws, "error")["data"]["reason"]
        ws.send_json({"v": 1, "type": "ping", "seq": 7})
        assert _next(ws, "pong")["data"]["echo"] == 7
        ws.send_json({"v": 1, "type": "command", "seq": 8, "data": {"action": "start_mission"}})
        ack = _next(ws, "ack")["data"]
        assert ack == {"action": "start_mission", "accepted": True, "message": "demo: mission restarted from the dock"}


def _next(ws, type_, limit=50):
    for _ in range(limit):
        m = ws.receive_json()
        if m["type"] == type_:
            return m
    raise AssertionError(f"no {type_} message")


def test_api_key_guard(secured_client):
    c = secured_client
    assert c.get("/healthz").status_code == 200                      # liveness stays open
    assert c.get("/api/v1/robots").status_code == 401
    assert c.get("/api/v1/robots", headers={"X-API-Key": "wrong"}).status_code == 401
    assert c.get("/api/v1/robots", headers={"X-API-Key": "s3cret"}).status_code == 200
    with c.websocket_connect("/ws/v1/robots/chotu-01?api_key=s3cret") as ws:
        assert ws.receive_json()["type"] == "hello"


def test_protocol_translation_matches_ros_interfaces():
    z = protocol.to_rosbridge("set_zones", {"zones": [{"x0": 0, "y0": 1, "x1": 2, "y1": 3}]}, "c1")
    assert z["args"] == {"no_go": [{"x_min": 0, "y_min": 1, "x_max": 2, "y_max": 3}]}
    srv = open(os.path.join(os.path.dirname(MIGRATION), "..", "..", "ros2_ws", "src", "chotu_interfaces",
                            "msg", "Zone.msg"), encoding="utf-8").read()
    for f in ("x_min", "y_min", "x_max", "y_max"):
        assert f"float32 {f}" in srv
    t = protocol.merge_rosbridge({}, {"op": "publish", "topic": "/chotu/status",
                                      "msg": {"state": "COVER", "coverage_estimate": 0.5, "battery_soc": 0.9,
                                              "suction_duty": 0.55, "elapsed_s": 12.0}})
    t = protocol.merge_rosbridge(t, {"op": "publish", "topic": "/odom",
                                     "msg": {"pose": {"pose": {"position": {"x": 1.0, "y": 2.0},
                                                               "orientation": {"z": 0.7071068, "w": 0.7071068}}}}})
    assert t == {"state": "COVER", "coverage": 0.5, "battery_pct": 90.0, "suction_pct": 55, "t": 12.0,
                 "pose": {"x": 1.0, "y": 2.0, "theta": 1.571}}


def test_sql_migration_matches_orm():
    ddl = open(MIGRATION, encoding="utf-8").read()
    for table in Base.metadata.sorted_tables:
        m = re.search(rf"CREATE TABLE IF NOT EXISTS {table.name} \((.*?)\n\);", ddl, re.S)
        assert m, f"{table.name} missing from 001_init.sql"
        cols = {line.split()[0] for line in m.group(1).strip().splitlines()
                if line.strip() and not line.strip().startswith(("PRIMARY", "FOREIGN", "--", "CONSTRAINT"))}
        assert cols == {c.name for c in table.columns}, table.name


def test_sample_data_is_consistent():
    sd = os.path.join(os.path.dirname(MIGRATION), "..", "sample_data")
    load = lambda n: json.load(open(os.path.join(sd, n), encoding="utf-8"))  # noqa: E731
    robots = {r["id"] for r in load("robots.json")}
    rooms = {r["id"] for r in load("rooms.json")}
    missions = load("missions.json")
    assert {m["robot_id"] for m in missions} <= robots and {m["room_id"] for m in missions} <= rooms
    assert {s["robot_id"] for s in load("schedules.json")} <= robots
    assert {a["mission_id"] for a in load("alerts.json")} <= {m["id"] for m in missions}
    states = [f["state"] for f in load("telemetry_replay.json")["frames"]]
    assert states[0] == "IDLE" and states[-1] == "DOCKED" and "COVER" in states
