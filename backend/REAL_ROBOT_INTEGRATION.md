# Real robot integration: communication, retrieval and storage

This is the step-by-step path from parts on a bench to a CHOTU robot whose data reaches the app and is stored by the fleet backend. Every layer of the repo is covered: mechanical, electronics, firmware, `chotu_core`, ROS 2, the YOLO model, Gazebo, Docker, the backend and the app.

> **Status.** No v3 hardware has been bought yet. Each step below is marked:
> - ✅ **verified**: the step is implemented, and it was run against the Gazebo robot. Gazebo runs the same ROS 2 stack, rosbridge and topics as the Pi.
> - 🔧 **on hardware**: the code exists; the step can only be run once the parts are on the bench.
> - ➕ **to add**: a designed extension that is not in the code yet. The design is given here so it can be built in one sitting.

## 0. The whole data path

```
 MECHANICAL            ELECTRONICS                 FIRMWARE                RASPBERRY PI 4 (Docker, ROS 2 Humble)                     OFF-ROBOT
┌──────────────┐  ┌──────────────────────┐   ┌──────────────────┐   ┌──────────────────────────────────────────────┐   ┌─────────────────────────┐
│ printed body │  │ carrier PCB J1..J18  │   │ ESP32-S3         │   │ serial_bridge_node ─► /odom /imu /range/*    │   │ Flutter app             │
│ sensor       │─►│ sensors, TB6612,     │──►│ 50 Hz PID,       │══►│   /chotu/bump /cliff /dock_ir /battery_state  │   │  (direct, LAN)          │
│ windows,     │  │ IRLZ44N, XL4015,     │   │ watchdog, safety │UART│ mission_manager (chotu_core) ─► /chotu/status │◄─►│ ws://chotu-01.local:9090│
│ deck, dock   │  │ star ground          │   │ COBS + CRC16     │   │   /map /chotu/plan /cmd_vel /chotu/actuators  │   ├─────────────────────────┤
└──────────────┘  └──────────────────────┘   └──────────────────┘   │ v4l2_camera ─► yolo_detector ─► /chotu/detections│   │ fleet backend (FastAPI) │
                                                                    │ rosbridge_websocket :9090  (JSON over WS)    │◄─►│  ─► PostgreSQL          │
                                                                    └──────────────────────────────────────────────┘   └─────────────────────────┘
```

| Hop | Transport | Rate | Content | Spec |
|---|---|---|---|---|
| ESP32 → Pi | UART 115200, COBS + CRC16 | 50 Hz | ticks, gyro z, 3 ultrasonic ranges, ToF, flags (bump, cliff, e-stop, watchdog, dock IR), battery mV | [PROTOCOL.md §1](PROTOCOL.md) |
| Pi → ESP32 | same | 10 Hz heartbeat + on change | `CMD_VEL`, `ACTUATORS`, `ESTOP` | same |
| ROS nodes on the Pi | DDS (CycloneDDS, host network) | 5–50 Hz | ROS 2 messages | `docs/ARCHITECTURE.md` §7 |
| Robot ↔ app | rosbridge v2 JSON over WebSocket :9090 | status 5 Hz, odom 10 Hz, plan 2 Hz, map 1 Hz (app throttles) | subscribe, call_service | [PROTOCOL.md §2](PROTOCOL.md) |
| Robot ↔ backend | same | status and odom 1 Hz | subscribe, call_service | same |
| Backend ↔ app and dashboard | REST `/api/v1` + WebSocket `/ws/v1/robots/{id}` | 1 Hz telemetry | versioned JSON envelope | [PROTOCOL.md §3–4](PROTOCOL.md) |
| Backend ↔ database | SQL (SQLAlchemy) | per event | robots, missions, schedules, zones, alerts | [PROTOCOL.md §5](PROTOCOL.md) |

---

## Phase 1. Mechanical: print and assemble the body 🔧

Files: [`bot_3d_printing/`](../bot_3d_printing/). Settings are in its README; the per-part checks are in `review_report.md`.

1. **Drill the reused MDF base.** Print `dxf/mdf_base_template.dxf` at 1:1, check it against the 100 mm scale, tape it to the MDF, and drill every hole listed in `dxf/mdf_base_holes.csv` (M3 = 3.4 mm).
2. **Print in this order:**
   - motor brackets, caster spacer and rear skid first: they set the ground clearance the cliff sensors depend on
   - then the bumper segments, cliff mounts, battery tray, deck pillars, electronics deck, nozzle, bin cradle, dust bin, bin lid and hatch
   - lid tiles and the dock last
   - all from `stl/`, in PETG where the README says so
3. **Fit the hardware:**
   - press the brass M3 heat-set inserts into the shell's top ledge and the deck pillars
   - glue the 12 magnets (hatch, bin and cradle) with the **polarity checked pairwise** before the glue sets
4. **Mount the sensors in their printed windows:**
   - 3× HC-SR04 in `bumper_front` at +35° / 0° / −35°, the same angles as `ultrasonic_angles_deg` in `chotu_core/config.py`
   - the VL53L0X in the front window
   - TCRT5000s in the cliff mounts, 3–5 mm above the floor
   - the TSOP38238 and the charging-contact slots as modelled in the bumper
   - the camera in `camera_pod`, which sets the 0.16 m height and 28° tilt that `perception.CameraModel` assumes
5. **Mount the drive and cleaning parts:** BO motors with encoder discs in the motor brackets, caster, Bergmann motor in the bin cradle duct, side-brush motor in `side_brush_mount`.
6. **Electronics deck:** the Raspberry Pi 4 and the 90 × 65 mm carrier PCB share the printed deck. The standoff holes match `hardware/pcb` (four M3, 4 mm from each corner).

**Check:** the robot sits level on the drive wheels and caster. The 200 mm nozzle clears the floor by 2–3 mm, and the bin lifts out through the hatch without tools.

## Phase 2. Electronics: wire everything through the carrier PCB 🔧

Files: [`hardware/pcb/`](../hardware/pcb/): schematic sheets, `chotu_carrier.net`, and the Protoflow hand-off for fabrication. Every connector is JST-XH or XT60, so there are no jumper wires.

| Connector | Plug in | Notes |
|---|---|---|
| J1 (XT60) | 3S Li-ion pack through the BMS | 11.1 V nominal, 12.6 V full. F1 is a 10 A blade fuse. |
| J2 | panel rocker switch | Cuts VBAT to everything |
| U2 pads | XL4015 buck, **set to 5.1 V before connecting the Pi** | +5 V rail with 1000 µF (C2) |
| J3 | Raspberry Pi 4 GPIO pins 2 (5 V) and 6 (GND) | The Pi is powered from the PCB, never from a power bank |
| U1 sockets | ESP32-S3-DevKitC-1 | The **UART** USB port goes to a Pi USB port: that is the data link |
| U3 sockets | TB6612FNG module | STBY has a 10 k pull-down, so the motors are off at boot |
| J4 / J5 | left / right BO motor | Swap the pair if a wheel spins backwards |
| J6 / J7 | left / right LM393 encoder | 5 V output, divided to 3.3 V on the PCB |
| J8 / J9 / J10 | HC-SR04 left / centre / right | Echo divided 1 k / 2 k |
| J11 / J12 | VL53L0X / MPU6050 | Shared I²C, 4.7 k pull-ups on the PCB |
| J13 | SW-420 bump | |
| J14 / J15 | TCRT5000 cliff left / right | |
| J16 | TSOP38238 dock receiver | Supply filter R14 (100 Ω) / C3 (4.7 µF) on the PCB, as the datasheet recommends |
| J17 | Bergmann BAV-60 | Q1 IRLZ44N with D1 1N5822 flyback |
| J18 | side-brush motor | Q2 IRLZ44N with D2 1N5822 |
| Pi CSI port | Pi camera ribbon | Becomes `/dev/video0` |

**Bring-up order, with the meter on the test points:**
1. Bench supply at 12 V, current-limited to 0.5 A, on J1. No modules fitted.
2. Check TP1 (VBAT) ≈ 12 V. Adjust the XL4015 until TP2 = 5.1 V.
3. Fit the ESP32 and check TP3 (+3V3) = 3.3 V.
4. Only now fit the TB6612, plug in the sensors, and finally the Pi.

**Check:** `tests/test_pcb_netlist.py` already proves the PCB nets equal the firmware pins. On the bench, nothing should get warm with the motors idle.

## Phase 3. Firmware: flash the ESP32-S3 and bench-test it 🔧

Files: [`firmware/esp32s3_base_controller/`](../firmware/esp32s3_base_controller/). The pins are in `include/pins.h` and the tuning in `include/config.h`.

1. Run the host tests on the workstation: `make -C firmware/esp32s3_base_controller/test_host` (Linux), or the g++ command in `docs/TESTING.md` (Windows). Expect **322 passed**. These tests use the same COBS/CRC byte vectors as `chotu_core/protocol.py`.
2. Flash from the workstation or from the Pi:
   ```bash
   bash scripts/flash_esp32.sh /dev/ttyUSB0      # COM5 on Windows
   ```
3. At power-on, keep the robot **still on the dock** for about 1 s while the gyro bias is calibrated.
4. **Safety check before any ROS.** With the wheels off the ground and no link to the Pi, the motors must stay off. The watchdog only enables motion while valid frames arrive (300 ms timeout).

**Check:** the PID tuning procedure in `docs/CONFIGURATION.md` §4. Done when the wheel speed tracks 0.2 m/s ± 10 %.

## Phase 4. Raspberry Pi 4: OS, devices and network 🔧

1. Flash **Ubuntu Server 22.04 LTS (64-bit)** with Raspberry Pi Imager. In the imager settings:
   - hostname `chotu-01`
   - enable SSH
   - add the home or venue WiFi
2. On the Pi:
   ```bash
   sudo apt update && sudo apt install -y docker.io docker-compose-v2 avahi-daemon
   sudo usermod -aG docker,dialout,video $USER && newgrp docker
   ```
   `avahi-daemon` makes the robot reachable as **`chotu-01.local`**, which the app and backend use. Also add a DHCP reservation on the router so the IP never changes.
3. **Give the ESP32 a stable device name.** The USB-UART chip on the DevKitC-1 is a CP210x or a CH343, depending on the board revision.
   ```bash
   udevadm info -a -n /dev/ttyUSB0 | grep -E 'idVendor|idProduct' | head -2      # or /dev/ttyACM0
   echo 'SUBSYSTEM=="tty", ATTRS{idVendor}=="10c4", ATTRS{idProduct}=="ea60", SYMLINK+="chotu_esp32"' \
     | sudo tee /etc/udev/rules.d/99-chotu.rules     # put your vendor/product IDs here
   sudo udevadm control --reload && sudo udevadm trigger && ls -l /dev/chotu_esp32
   ```
4. **Camera.** For the Pi camera on Ubuntu 22.04, add `start_x=1` to `/boot/firmware/config.txt` and reboot. Check that `ls /dev/video0` exists.

**Check:** `ping chotu-01.local` works from the phone's network, and both `/dev/chotu_esp32` and `/dev/video0` exist.

## Phase 5. Docker: deploy the ROS 2 stack to the Pi 🔧 (images ✅)

Files: [`docker/`](../docker/) and `scripts/deploy_pi.sh`. These images run the same `chotu_core` and ROS packages that were verified in Gazebo.

| Container (`docker/docker-compose.yml`, profile `robot`) | Runs | Hardware it maps |
|---|---|---|
| `robot` | `robot.launch.py vision:=false camera:=true`: rosbridge :9090, serial bridge, mission manager (`chotu_core`), robot description, camera driver | `${CHOTU_ESP32_PORT}` → `/dev/ttyUSB0` in the container, `/dev/video0` |
| `perception` | `yolo_detector_node` with `weights:=${CHOTU_YOLO_WEIGHTS}` (NCNN on the Pi) | `models/` mounted read-only |

Both containers use `network_mode: host` with `ROS_DOMAIN_ID=42` and CycloneDDS, so they see each other's topics, and port 9090 is the Pi's own port.

```bash
# workstation: build arm64 images, push, start them on the Pi (versioned, never :latest)
export REGISTRY=ghcr.io/<github-user> PI_HOST=ubuntu@chotu-01.local
bash scripts/deploy_pi.sh 3.0.0
# on the Pi: point the robot container at the udev name
echo "CHOTU_ESP32_PORT=/dev/chotu_esp32" >> ~/chotu/docker/.env
cd ~/chotu/docker && docker compose --profile robot up -d && docker compose --profile robot ps
```

**Check:**
```bash
docker exec -it chotu-robot-1 bash -lc "ros2 topic hz /odom"            # ~50 Hz, no CRC warnings
docker exec -it chotu-robot-1 bash -lc "ros2 topic echo /chotu/status --once"   # state: IDLE
docker compose --profile robot logs robot | grep "Rosbridge WebSocket server started on port 9090"
```

## Phase 6. YOLO model: train, export and deploy 🔧

Files: [`ros2_ws/src/chotu_perception/training/`](../ros2_ws/src/chotu_perception/training/) and [`models/README.md`](../models/README.md).

1. **Collect data.** Record frames from the robot's own camera, so they come from the mounted height and tilt:
   ```bash
   docker exec -it chotu-robot-1 bash -lc "ros2 bag record -o /tmp/frames /camera/image_raw"
   ```
   Extract frames and label them with the classes in `chotu_suck_avoid.yaml` (Label Studio, CVAT or Roboflow).
2. **Train** on the RTX 3060 workstation: `python train_suck_avoid.py --data chotu_suck_avoid.yaml --epochs 80 --device 0`.
3. **Export for the Pi:** `python train_suck_avoid.py --export-only runs/detect/chotu/weights/best.pt`. This produces an NCNN model at imgsz 320.
4. **Deploy:** `scp -r models/chotu_suck_avoid_yolov8n_ncnn_model ubuntu@chotu-01.local:~/chotu/models/`, then `docker compose --profile robot restart perception`.

**Check:** `ros2 topic hz /chotu/detections` reads about 5 Hz. With a cable in view, `ros2 topic echo /chotu/detections` shows `action: avoid`, and the cable appears as a keep-out on `/map`.

## Phase 7. Gazebo: rehearse every connection before the floor ✅

The Gazebo launch (`sim.launch.py`) starts **the same rosbridge, mission manager and topics** as the robot. `gz_sensor_adapter_node` replaces the serial bridge, so the backend and the app cannot tell the difference. Connect to it first, so that any failure on the real robot is a hardware problem, not a software one.

```bash
# Git Bash on Windows: prefix with MSYS_NO_PATHCONV=1 and use "$(pwd -W)"
docker run -d --name chotu_sim -p 9090:9090 -v "$(pwd)":/workspace chotu/dev:3.0.0 bash -c \
 "source /opt/ros/humble/setup.bash && cd /workspace/ros2_ws && colcon build --build-base /tmp/b --install-base /tmp/i \
  && source /tmp/i/setup.bash && (xvfb-run -a ros2 launch chotu_bringup sim.launch.py vision:=false; sleep infinity)"
```
(Keep `xvfb-run` as a child process; it hangs when it runs as the container's PID 1.)

**Verified on 2026-10-18** with the backend in rosbridge mode and `endpoint = ws://127.0.0.1:9090`:

| Step | Observed |
|---|---|
| Backend connects, subscribes to `/chotu/status` and `/odom` | rosbridge log: `Client connected` … `Subscribed to /chotu/status`, `/odom` |
| Live telemetry through `GET /api/v1/robots/chotu-01` | `SCAN → COVER`, pose `(1.236, 0.688, −3.10)`, coverage rising, battery 90 %, suction 55 % |
| `PUT /api/v1/robots/chotu-01/zones` | stored, and the mission manager logged `1 no-go zone(s) set` |
| `POST …/commands {"action":"return_to_dock"}` | `accepted: true, "returning to dock"` → `RETURN_TO_DOCK → DOCKING → DOCKED` at (1.521, 0.218), 2.8 cm from the dock pose |
| Flutter app, *Connect by address* `ws://127.0.0.1:9090` | it subscribed to `/chotu/status`, `/odom`, `/chotu/plan` and `/map`, and showed the robot's live map and state (screenshots in [`mobile_app/REAL_ROBOT_CONNECTION.md`](../mobile_app/REAL_ROBOT_CONNECTION.md)) |

## Phase 8. Connection establishment on the real robot

Do these in order. Each step only depends on the ones before it.

| # | Step | Command / action | Expected |
|---|---|---|---|
| 8.1 | Robot on the network | `ping chotu-01.local` | replies |
| 8.2 | Robot API up | `docker compose --profile robot logs robot \| grep 9090` | `Rosbridge WebSocket server started on port 9090` |
| 8.3 | ESP32 link alive | `ros2 topic hz /odom` | ~50 Hz |
| 8.4 | App, direct | App → *Connect by address* → `ws://chotu-01.local:9090` | header shows **ONLINE**, ring shows **IDLE** or **DOCKED**, map draws |
| 8.5 | App commands | *Clean room* | robot undocks (`StartMission{abort:false}`); *Dock* → `abort:true` |
| 8.6 | No-go zones | App → Live map → draw → *Apply* | mission manager log: `n no-go zone(s) set` |
| 8.7 | Backend link | On the server: `endpoint = ws://chotu-01.local:9090` in `robots` and `CHOTU_ROBOT_LINK=rosbridge` | `GET /api/v1/robots/chotu-01` → `"online": true` with live telemetry |
| 8.8 | App + backend | build the app with `--dart-define=BACKEND_URL=https://fleet.example:8000` | the History and Schedule tabs load from the backend |

The backend must run on a machine that can reach `chotu-01.local`, which means the same LAN or a VPN such as Tailscale. **Never port-forward 9090.** rosbridge has no authentication. The backend is the only service exposed beyond the LAN, behind an API key and TLS (`backend/README.md` §5).

## Phase 9. Data retrieval and storage

### 9.1 What exists where

| Data | Produced by | Retrieved by | Stored |
|---|---|---|---|
| Live state, coverage, battery, suction, pose | `/chotu/status` (5 Hz) + `/odom` | the app (rosbridge, direct) ✅; backend `GET /robots/{id}` + WS `/ws/v1/robots/{id}` ✅ | in memory (the latest value) ✅ |
| Map and planned path | `/map` (1 Hz), `/chotu/plan` | the app ✅ | on the robot only, for the current mission |
| No-go zones | app or backend | the app ✅, `GET /robots/{id}/zones` ✅ | **database** `zones` ✅ + pushed to the robot through `/chotu/set_zones` ✅ |
| Schedules | app or backend | `GET /robots/{id}/schedules` ✅ | **database** `schedules` ✅ |
| Mission reports | `POST /robots/{id}/missions` ✅ | `GET /missions`, `/fleet/summary` ✅, the app's History ✅ | **database** `missions` ✅ |
| Alerts | backend | `GET /alerts` ✅ | **database** `alerts` ✅ |
| Raw sensor logs | ROS topics | engineers (Foxglove, `ros2 bag play`) | ➕ rosbag2 on the robot (§9.3) |
| Telemetry history | `/chotu/status` | ➕ `GET /robots/{id}/telemetry` | ➕ `telemetry` table (§9.4) |

### 9.2 Storing mission reports from a real robot ➕

The API and table exist and are tested. What is missing is something that **creates the report automatically when a real robot docks**. That needs one module, `chotu_api/services/mission_recorder.py`:

1. Subscribe to the link's `mission_event` envelopes (the same fan-out the WebSocket uses).
2. On `IDLE/DOCKED → UNDOCK`, open a run: record `started_at`, the start battery and the zone count.
3. On `* → DOCKED`, close it:
   - `duration_s` = telemetry `t`
   - `coverage` = the last `coverage_estimate`
   - `energy_wh` = (battery % at start − at end) × 111 Wh / 100
   - `dock_error_m` = distance from the pose to the room's dock (`rooms.dock_*`)
   - `docked = true`
4. Mass is not measured on board. Leave `debris_g` empty, then have the operator **weigh the bin** and send `PATCH /missions/{id} {"debris_g": …}`. The backend then computes `rubric` and `score` with `chotu_core.scoring.score(...)`, the same function the robot uses.
5. Schema change in `migrations/002_mission_measurements.sql`: make `debris_g`, `debris_spawned_g`, `rubric`, `score` and `efficiency_by_type` nullable, and add `PATCH /missions/{id}`. Update `db/models.py` in the same commit; `test_sql_migration_matches_orm` enforces the match.
6. Test it against the Gazebo rehearsal (Phase 7): one full run must produce exactly one mission row.

### 9.3 Raw logs on the robot ➕

```bash
# inside the robot container, one bag per mission (MCAP, zstd), on a USB SSD rather than the SD card.
# MCAP needs ros-humble-rosbag2-storage-mcap added to the runtime stage of docker/Dockerfile.
ros2 bag record -s mcap --compression-mode file --compression-format zstd -o /data/bags/$(date +%F_%H%M) \
  /chotu/status /odom /imu /range/left /range/center /range/right /range/tof /chotu/detections /chotu/plan /map
```
* Mount a USB drive at `/data` and add `- /data:/data` to the `robot` service.
* Delete bags older than 14 days with a cron job.
* Leave out `/camera/image_raw` except while collecting training data, because it is about 100× larger.
* Open bags in Foxglove Studio, or replay them into Gazebo and RViz with `ros2 bag play`.

### 9.4 Telemetry history in the database ➕

* Table: `telemetry(robot_id, ts, state, coverage, battery_pct, suction_pct, x, y, theta)` with an index on `(robot_id, ts)`.
* Write rate: 1 Hz, from the same link callback. That is about 300 rows per 5-minute mission.
* Retention: 30 days, using a nightly `DELETE … WHERE ts < now() - interval '30 days'`, or the TimescaleDB extension once there are many robots.
* Read: `GET /api/v1/robots/{id}/telemetry?from=&to=` for replays and charts.

### 9.5 Retrieval examples (available today ✅)

```bash
curl -H "X-API-Key: $KEY" https://fleet.example/api/v1/robots/chotu-01            # live status
curl -H "X-API-Key: $KEY" "https://fleet.example/api/v1/missions?robot_id=chotu-01&limit=20"
curl -H "X-API-Key: $KEY" https://fleet.example/api/v1/fleet/summary
psql "$DATABASE_URL" -c "select robot_id, count(*), avg(score) from missions group by robot_id;"
```

## Phase 10. Troubleshooting by layer

| Symptom | Layer | Check |
|---|---|---|
| App says *Connection closed* at once | network | Same WiFi? `ping chotu-01.local`. Is 9090 open on the Pi? (`ss -ltn \| grep 9090`) |
| App connects, but the ring stays IDLE and there is no map | ROS | `ros2 topic hz /chotu/status`. Did the mission manager start? (`docker compose logs robot`) |
| `/odom` silent | firmware / USB | `ls -l /dev/chotu_esp32`, the `CHOTU_ESP32_PORT` in `.env`, the baud rate (115200) in `chotu_params.yaml` |
| CRC warnings in the bridge log | wiring | USB cable or ground. Is the ESP32 powered from the PCB 5 V rail? |
| Wheels don't move, but `/cmd_vel` is published | electronics | Is TB6612 STBY high (e-stop released)? Does the `safety` field of `/chotu/status` say `blocked`, `bump` or `cliff`? Any watchdog warnings in the bridge log? |
| Pi reboots when the vacuum starts | power | XL4015 at 5.1 V, C2 fitted, the Pi fed through J3, not USB |
| Backend `"online": false` | backend | The `endpoint` in the `robots` row, `CHOTU_ROBOT_LINK=rosbridge`, and the backend log `link down (...)`; it retries with 1–30 s back-off |
| No detections | perception | `/dev/video0` exists, and `ros2 topic hz /camera/image_raw` > 0 in the robot container; `CHOTU_YOLO_WEIGHTS` points to an existing model |
