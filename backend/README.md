# CHOTU fleet backend

FastAPI service for **mission history, schedules, no-go zones, alerts and live telemetry** across CHOTU robots. Out of the box it serves **sample data** and **demo robots**. Nothing is connected to a database or to hardware until you switch it on, as described below.

<p align="center"><img src="docs/fleet_dashboard.png" width="88%" alt="Fleet dashboard served by the backend"/></p>

| | |
|---|---|
| API | REST `/api/v1/*` + WebSocket `/ws/v1/robots/{id}`. OpenAPI docs at `/docs`. |
| Dashboard | `/`: one static page that renders the API, with live robot cards over the WebSocket |
| Protocol | [PROTOCOL.md](PROTOCOL.md): every link from app to backend to robot to MCU |
| Stores | `sample` (in-memory, from `sample_data/*.json`) or `sql` (SQLAlchemy: PostgreSQL in production, SQLite in tests) |
| Robot link | `demo` (replays the Gazebo mission) or `rosbridge` (connects to each robot's `ws://<pi>:9090`) |
| Tests | `python -m pytest backend/tests -q`: 23 tests covering both stores, the WebSocket, auth, the migration and a fake rosbridge |

## Where it sits

```
Flutter app ──REST/WS──► chotu_api (this) ──rosbridge JSON──► Raspberry Pi 4 (ROS 2) ──COBS/CRC16 UART──► ESP32-S3
     │                        │
     └──rosbridge JSON (LAN)──┼──────────────────────────────► same robot, direct (works with the backend down)
                              └──SQL──► PostgreSQL
```

The robot's autonomy never depends on this service. The backend adds what one robot cannot keep on its own: history across robots and re-flashes, schedules, stored no-go zones, and a single endpoint for phones that are off the robot's WiFi.

## Layout

```
backend/
├── chotu_api/
│   ├── main.py              app factory, lifespan (store + robot link), /healthz, dashboard
│   ├── config.py            Settings from environment variables (.env.example)
│   ├── protocol.py          WebSocket envelope + rosbridge translation (single source of the wire contract)
│   ├── schemas.py           pydantic request/response models (OpenAPI)
│   ├── deps.py              store / link / API-key dependencies
│   ├── routers/             robots.py (status, commands, schedules, zones, uploads) · history.py · live.py (WebSocket)
│   ├── repositories/        base.py (interface) · sample.py (JSON, in memory) · sql.py (SQLAlchemy)
│   ├── db/                  models.py (ORM) · session.py · seed.py (load sample_data into a database)
│   ├── services/robot_link.py   DemoRobotLink · RosbridgeRobotLink (reconnecting WebSocket client)
│   └── static/dashboard.html
├── sample_data/             robots, rooms, 40 missions, schedules, zones, alerts, telemetry replay
├── migrations/001_init.sql  PostgreSQL DDL (kept equal to the ORM by a test)
├── tests/                   pytest
├── Dockerfile · docker-compose.yml · requirements.txt · .env.example
```

**Where the sample data comes from.** Every mission is a real run from the 40-room v2 digital-twin benchmark (commit `9757b23`), spread over four demo robots and a calendar (`source: "digital_twin"`). The telemetry replay uses the Gazebo run's state timeline (`gazebo_mission_metrics.json`). The fleet summary therefore shows the benchmark's own figures: 40/40 docked, mean score 77.6.

## 1. Run it on sample data (no database)

```bash
cd backend
python -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn chotu_api.main:app --reload
# http://127.0.0.1:8000         dashboard
# http://127.0.0.1:8000/docs    interactive API
```

## 2. Connect a database (PostgreSQL), step by step

The code path is already written and tested. Connecting a database only takes configuration.

### Option A: Docker (recommended, about 2 minutes)
```bash
# from the repo root
CHOTU_STORE=sql docker compose -f backend/docker-compose.yml --profile db up --build
```
This starts three services:
1. `db`: PostgreSQL 16. `migrations/001_init.sql` runs automatically on first start (`docker-entrypoint-initdb.d`).
2. `seed`: runs `python -m chotu_api.db.seed`, which loads `sample_data/*.json`. Rows that already exist are skipped, so it is safe to re-run.
3. `api`: starts after the seed with `CHOTU_STORE=sql`, and reads and writes PostgreSQL.

If port 5432 or 8000 is taken, set `CHOTU_DB_PORT=15432` and/or `CHOTU_API_PORT=18000`.

Check it:
```bash
curl localhost:8000/healthz                       # {"store":"sql", ...}
curl localhost:8000/api/v1/fleet/summary          # 4 robots, 40 missions
docker compose -f backend/docker-compose.yml exec db psql -U chotu -c "select count(*) from missions;"
```

### Option B: your own PostgreSQL (local install, RDS, Supabase, Neon, …)
```bash
# 1. create the database and user
psql -U postgres -c "create user chotu with password 'change-me';" -c "create database chotu owner chotu;"
# 2. point the backend at it (the URL scheme selects the psycopg 3 driver)
export DATABASE_URL="postgresql+psycopg://chotu:change-me@localhost:5432/chotu"
# 3. create the schema: either the migration ...
psql "postgresql://chotu:change-me@localhost:5432/chotu" -f backend/migrations/001_init.sql
#    ... or let SQLAlchemy create it during the seed (step 4 does this as well)
# 4. load the sample data
cd backend && python -m chotu_api.db.seed            # --reset drops and recreates the tables first
# 5. run the API on the database
CHOTU_STORE=sql uvicorn chotu_api.main:app
```

### What changes in the code: nothing
Routers depend only on `repositories.base.Repository`. `CHOTU_STORE` selects `SampleRepository` or `SqlRepository` at start-up (`repositories/__init__.py`). Responses are identical. The test suite runs every API test against both stores to prove it.

## 3. Connect real robots

```bash
CHOTU_ROBOT_LINK=rosbridge uvicorn chotu_api.main:app
```
For every row in `robots`, the backend opens `endpoint` (for example `ws://chotu-01.local:9090`, the robot's `rosbridge_websocket` from `robot.launch.py`). It subscribes to `/chotu/status` and `/odom`, and sends commands as `call_service` to `/chotu/start_mission` and `/chotu/set_zones`. If a robot drops off, the link reconnects with exponential back-off (1 s up to 30 s). Edit `endpoint` in the database (or in `sample_data/robots.json`) to match your robot's hostname.

## 4. Render it in the app

The Flutter app uses the backend when it is built with `--dart-define=BACKEND_URL=...`:
```bash
cd mobile_app/chotu_app
flutter run -d chrome --dart-define=BACKEND_URL=http://127.0.0.1:8000 --dart-define=ROBOT_ID=chotu-01
```
After connecting, the app replaces its local *History* and *Schedule* with `GET /api/v1/missions?robot_id=…` and `GET /api/v1/robots/{id}/schedules`. *Apply zones* also sends `PUT /api/v1/robots/{id}/zones`. Live control still goes straight to the robot over rosbridge. The client is `lib/data/backend_api.dart`, unit-tested in `test/backend_api_test.dart`.

<p align="center">
  <img src="docs/app_history_from_backend.png" width="30%" alt="App history rendered from the backend"/>
  <img src="docs/app_settings_backend.png" width="30%" alt="App settings showing the backend URL"/>
</p>

*The app's History tab rendering chotu-01's missions from the backend. Mission m-0037 shows 49.5 % coverage, 21.6 g and 212 s, exactly as in `sample_data/missions.json`.*

## 5. Security checklist before leaving localhost
* Set `CHOTU_API_KEY` to a long random value. REST clients send `X-API-Key`; browsers' WebSockets send `?api_key=`.
* Restrict `CHOTU_CORS_ORIGINS` to your app's origin.
* Put TLS in front (Caddy, nginx or a cloud load balancer) so the app uses `https://` and `wss://`.
* Use a dedicated database user that owns only the `chotu` database.

## API summary

| Method | Path | Purpose |
|---|---|---|
| GET | `/healthz` | Liveness, version, store, link (no auth) |
| GET | `/api/v1/robots` | Fleet list |
| GET | `/api/v1/robots/{id}` | Online flag + latest telemetry |
| POST | `/api/v1/robots/{id}/commands` | `start_mission` / `return_to_dock`. Returns the exact rosbridge message sent. |
| GET/POST/PUT/DELETE | `/api/v1/robots/{id}/schedules[/{sid}]` | Cleaning schedules |
| GET/PUT | `/api/v1/robots/{id}/zones` | No-go zones (replace-all, forwarded to `/chotu/set_zones`) |
| POST | `/api/v1/robots/{id}/missions` | Upload a mission report |
| GET | `/api/v1/missions[/{mid}]` | History (newest first, `limit`/`offset`/`robot_id`) |
| GET | `/api/v1/fleet/summary` | Dock success, coverage, score, debris, energy, open alerts |
| GET | `/api/v1/rooms` | Room geometry + dock pose |
| GET | `/api/v1/alerts` · POST `/api/v1/alerts/{aid}/resolve` | Alerts |
| WS | `/ws/v1/robots/{id}` | Live telemetry, mission events, acks; send commands |

