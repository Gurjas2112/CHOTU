# CHOTU communication protocol (v1)

This spec covers every link, from the phone down to the motor controller. It describes what is implemented in `backend/chotu_api/protocol.py`, `mobile_app/chotu_app/lib/data/`, `ros2_ws/` and `firmware/`, and the tests named in each section pin it down.

```
 Phone / dashboard                Fleet backend                  Raspberry Pi 4                 ESP32-S3
┌───────────────┐  §3 REST   ┌──────────────────┐  §2 rosbridge ┌────────────────┐  §1 UART    ┌───────────┐
│ Flutter app   │──────────► │ chotu_api        │ ────────────► │ rosbridge :9090│ ──────────► │ base      │
│ dashboard.html│ ◄────────► │ (FastAPI)        │ ◄──────────── │ ROS 2 Humble   │ ◄────────── │ controller│
└───────────────┘  §4 WS     └────────┬─────────┘               └────────────────┘  50 Hz      └───────────┘
        │                             │ §5 SQL                         ▲
        └────────── §2 rosbridge (LAN, direct; works without the backend) ┘
```

## 1. ESP32-S3 ↔ Raspberry Pi: binary frames over UART

* 115200 baud over the DevKitC USB-UART (`/dev/ttyUSB0`).
* Frame: `COBS(payload ‖ CRC16-CCITT(payload)) ‖ 0x00`. The payload is `msg_id:u8, seq:u8, body…`, little-endian.
* Messages: `0x01 CMD_VEL`, `0x02 ACTUATORS`, `0x03 HEARTBEAT`, `0x04 ESTOP` (Pi → ESP), and `0x81 TELEMETRY` (25 B, ESP → Pi).
* Flags byte: bump 0, cliff L 1, cliff R 2, e-stop 3, watchdog 4, **dock IR 5**.
* **Safety:** if no valid frame arrives within 300 ms, the firmware's safety supervisor zeroes the wheel and vacuum outputs. `ESTOP` also pulls the TB6612 STBY pin low, a hardware cut.
* **Tested by:** `tests/test_protocol.py` (Python) and `firmware/.../test_host` (C++). Both use the same byte vectors.

## 2. App or backend ↔ robot: rosbridge v2 JSON over WebSocket

The robot runs `rosbridge_websocket` on **port 9090** (`chotu_bringup/launch/robot.launch.py`). Both clients speak the standard rosbridge v2 operations:

| Purpose | Client sends | Robot replies |
|---|---|---|
| Live status | `{"op":"subscribe","topic":"/chotu/status","type":"chotu_interfaces/msg/CleaningStatus","throttle_rate":1000}` | `{"op":"publish","topic":"/chotu/status","msg":{state, elapsed_s, coverage_estimate, suction_duty, battery_soc, …}}` |
| Pose | `subscribe` `/odom` (`nav_msgs/msg/Odometry`) | `publish` with `pose.pose.position` and `orientation` (yaw from the quaternion) |
| Start | `{"op":"call_service","id":"…","service":"/chotu/start_mission","type":"chotu_interfaces/srv/StartMission","args":{"abort":false,"time_budget_s":0}}` | `{"op":"service_response","id":"…","result":true,"values":{"accepted":true,"message":"…"}}` |
| Return to dock | same service, `"args":{"abort":true,"time_budget_s":0}` (the robot calls `CleaningMission.request_dock`) | same |
| No-go zones | `call_service` `/chotu/set_zones` `{"no_go":[{"x_min","y_min","x_max","y_max"}]}` (metres, room frame, replace-all) | same |

**Rules:**
* `id` is unique per call, and the response echoes it.
* The backend times out after 5 s and reports the robot as not answering.
* Clients reconnect with back-off from 1 s to 30 s.

**Tested by:**
* `backend/tests/test_api.py::test_protocol_translation_matches_ros_interfaces`, which reads the real `.msg` file
* `backend/tests/test_rosbridge_link.py`, which runs against a fake rosbridge server
* `mobile_app/chotu_app/test/rosbridge_protocol_test.dart`

## 3. App ↔ backend: REST `/api/v1`

* JSON over HTTP(S). The complete schema is served live at `/docs` and `/openapi.json`.
* **Auth:** the header `X-API-Key: <key>` is required when `CHOTU_API_KEY` is set. `/healthz` stays open.
* **Errors:** FastAPI's standard `{"detail": …}` with the matching HTTP status: 401 bad key, 404 unknown id, 422 validation (for example `x1 <= x0`, or `time` outside `HH:MM`), 503 robot offline.
* **Versioning:** the path prefix `/api/v1`. A breaking change becomes `/api/v2`, served side by side.
* **Units:** metres and radians in the room frame (origin at the south-west corner; the dock is on the south wall). Times are ISO-8601 UTC strings. Coverage is 0..1. Battery and suction are percentages.

## 4. App or dashboard ↔ backend: live WebSocket `/ws/v1/robots/{robot_id}`

Every message in both directions is one JSON envelope:

```json
{"v": 1, "type": "telemetry", "robot_id": "chotu-01", "seq": 42, "ts": "2026-10-17T10:30:00.000Z", "data": {}}
```

| Direction | `type` | `data` |
|---|---|---|
| server → client | `hello` | `{protocol, link, online, telemetry, commands}`, sent once on connect |
| server → client | `telemetry` | `{t, state, coverage, battery_pct, suction_pct, pose:{x,y,theta}}` at 1 Hz |
| server → client | `mission_event` | `{from, to, t}` on every state change (for example `COVER → RETURN_TO_DOCK`) |
| server → client | `ack` | `{action, accepted, message}`, broadcast to every subscriber of that robot |
| server → client | `error` | `{reason}` (or `{action, reason}`), sent only to the client that caused it |
| server → client | `pong` | `{echo: <client seq>}` |
| client → server | `command` | `{action: "start_mission" \| "return_to_dock", time_budget_s?}` |
| client → server | `ping` | – |

**Rules:**
* The server rejects a wrong `v`, an unknown `type` or an unknown `action` with `error` and keeps the socket open.
* A browser passes the API key as `?api_key=`, because browsers cannot set WebSocket headers.
* Slow clients lose their oldest frames; the queue holds 64. They never stall the robot link.
* `seq` increases per robot on broadcasts, and separately per connection on `hello`, `error` and `pong`.

**Tested by:** `backend/tests/test_api.py::test_websocket_protocol` and `test_api_key_guard`.

## 5. Backend ↔ database

* SQLAlchemy 2.x, with the URL taken from `DATABASE_URL`. PostgreSQL uses `postgresql+psycopg://`.
* The schema is `migrations/001_init.sql`: tables `rooms`, `robots`, `missions`, `schedules`, `zones` and `alerts`, with JSONB for rubric, efficiency, days and dock pose.
* The ORM in `chotu_api/db/models.py` must match the migration column for column; `test_sql_migration_matches_orm` enforces it.
* Seeding is idempotent: `python -m chotu_api.db.seed`.
* **Change process:** add `migrations/002_*.sql` and update `models.py` in the same commit. The test fails until they match.
