# Setup Guide

Pick the track you need. **A** needs only Python. **B** adds ROS 2 and Gazebo, the project's simulator. **C** is the physical robot. **D–F** cover the app, the fleet backend, and the CAD and PCB tools. Everything except C runs on demo data.

| Track | You get | Needs |
|---|---|---|
| A. Core library + tests (Windows / Linux / macOS) | `chotu_core` autonomy, protocol and PCB checks | Python 3.10+ (3.12 tested) |
| B. ROS 2 + Gazebo simulation | ROS 2 Humble workspace, Gazebo world, RViz, recorded mission | Docker Desktop (WSL2) **or** WSL Ubuntu 22.04 |
| C. Robot | ESP32 firmware + ROS 2 on the Raspberry Pi 4 | Hardware in `HARDWARE_SOFTWARE_REQUIREMENTS.md` (not bought yet) |
| D. Mobile app | Flutter app with demo robot, or connected to rosbridge | Flutter 3.16+ |
| E. Fleet backend | REST + WebSocket API, sample data, PostgreSQL | Python 3.10+, Docker for PostgreSQL |
| F. CAD + PCB | Printable STL/STEP, schematic sheets, KiCad netlist | Python 3.12 + CadQuery, SKiDL, schemdraw |

```bash
git clone https://github.com/Gurjas2112/CHOTU.git
cd CHOTU
```

---

## A. Core library and tests (2 minutes)

### Windows 11 (PowerShell)
```powershell
# one-shot: venv + deps + pytest + firmware host tests + backend tests
powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1

# or step by step
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
python -m pytest tests -q
```

### Linux / WSL / macOS
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && pip install -e .
python -m pytest tests -q
```

---

## B. ROS 2 Humble workstation

Gazebo Fortress is the simulator for CHOTU. To record a complete mission headless, see [`bot_simulation/gazebo_recording/README.md`](../bot_simulation/gazebo_recording/README.md).

### B1. Docker (recommended, nothing installed on the host)
Prerequisites: Docker Desktop with the WSL2 backend. For GPU work you also need the NVIDIA driver; the GPU is visible in Docker on WSL2.

```bash
# build the versioned dev image (osrf/ros:humble-desktop + Gazebo Fortress + tools)
docker compose -f docker/docker-compose.yml --profile dev build

# interactive dev shell, repo mounted at /workspace
docker compose -f docker/docker-compose.yml --profile dev run --rm dev
#   inside:
cd /workspace/ros2_ws
rosdep update && rosdep install --from-paths src --ignore-src -y
colcon build --symlink-install
source install/setup.bash
ros2 launch chotu_bringup sim.launch.py rviz:=true vision:=false
```

* **GUI (RViz / Gazebo) on Windows 11.** WSLg provides the display, and the compose file mounts `/tmp/.X11-unix` and `/mnt/wslg`. On native Linux, run `xhost +local:` first.
* **VS Code.** Open the folder, then choose *Dev Containers: Reopen in Container*. `.devcontainer/devcontainer.json` uses the same `dev` stage.
* **Shortcut.** `bash scripts/build_ros_docker.sh` builds and tests the workspace in the container.

### B2. Native WSL Ubuntu 22.04
```bash
wsl -d Ubuntu
cd /mnt/c/Users/<you>/OneDrive/Desktop/CHOTU
bash scripts/setup_wsl_ros2_humble.sh      # apt installs ros-humble-desktop + ros-gz, colcon build
source ros2_ws/install/setup.bash
ros2 launch chotu_bringup sim.launch.py
```

---

## C. Physical robot

### C1. Assemble and wire
Follow `HARDWARE_SOFTWARE_REQUIREMENTS.md` §2 and the pin table in `ARCHITECTURE.md` §6. Every module plugs into the **CHOTU carrier PCB** (`hardware/pcb/`), which already has the star ground, the 5 V → 3.3 V dividers, the MOSFET drivers with flyback diodes, and the STBY pull-down. Print the body from `bot_3d_printing/` (see its README).

### C2. Flash the ESP32-S3
```bash
pip install platformio
bash scripts/flash_esp32.sh            # or: cd firmware/esp32s3_base_controller && pio run -t upload
```
At boot the robot must be **still on the dock** for about 1 s while the gyro calibrates. When calibration is done, the status reaches the Pi and the app shows *Docked · ready*.

### C3. Prepare the Raspberry Pi 4
1. Flash **Ubuntu Server 22.04 LTS (64-bit)** with Raspberry Pi Imager. Set the hostname to `chotu`, enable SSH and add Wi-Fi.
2. On the Pi:
   ```bash
   sudo apt update && sudo apt install -y docker.io docker-compose-v2
   sudo usermod -aG docker,dialout,video $USER && newgrp docker
   ls /dev/ttyUSB* /dev/video*          # ESP32 link + camera must be present
   ```
3. Enable the camera. With the Pi camera v1.3 or v2 on Ubuntu, add `start_x=1` to `/boot/firmware/config.txt` (legacy stack) or use a USB webcam. Either way it shows up as `/dev/video0`.
4. Deploy the containers as described in `DEPLOYMENT.md`.

### C4. First run
```bash
docker compose -f docker/docker-compose.yml --profile robot up -d
docker exec -it chotu-robot-1 bash -lc \
  "ros2 service call /chotu/start_mission chotu_interfaces/srv/StartMission '{abort: false}'"
docker exec -it chotu-robot-1 bash -lc "ros2 topic echo /chotu/status"
```

---

## D. Mobile app (Flutter)

```powershell
cd mobile_app\chotu_app
flutter pub get
flutter run -d chrome                         # demo robot: tap "Connect" on CHOTU-01
flutter run -d <android-device>               # real robot: enter ws://chotu.local:9090
flutter run -d chrome --dart-define=BACKEND_URL=http://127.0.0.1:8000   # history + schedules from the backend
```
Re-record the demo tour with `python mobile_app/tools/record_app_demo.py` (see `mobile_app/app_screenshot_screen_recording/README.md`).

## E. Fleet backend (FastAPI)

```bash
cd backend
pip install -r requirements.txt
uvicorn chotu_api.main:app --reload             # http://127.0.0.1:8000 (dashboard), /docs (OpenAPI)
python -m pytest tests -q                       # sample store + SQL store + WebSocket + rosbridge link
CHOTU_STORE=sql docker compose --profile db up --build   # PostgreSQL 16, schema + seed, API on :8000
```
The step-by-step guide to connecting a database is [`backend/README.md`](../backend/README.md). The wire protocol is [`backend/PROTOCOL.md`](../backend/PROTOCOL.md).

## F. CAD and PCB tools

```bash
pip install -r requirements-dev.txt              # cadquery, trimesh, skidl, schemdraw, playwright
python bot_3d_printing/tools/cad_pipeline.py      # STL/STEP/DXF + review + flow PNGs + walkthrough MP4 (~2 min)
python hardware/pcb/chotu_carrier.py              # KiCad netlist + design-rule report
python hardware/pcb/render_schematic.py           # schematic sheets (PNG + SVG)
python hardware/pcb/protoflow/make_protoflow_package.py   # Protoflow brief + JLCPCB BOM
```
