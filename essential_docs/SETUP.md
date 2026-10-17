# Setup Guide

There are three tracks. Pick the one you need: **A** needs only Python, **B** adds ROS 2, and **C** is the physical robot.

| Track | You get | Needs |
|---|---|---|
| A. Digital twin (Windows / Linux / macOS) | Simulator, HUD, fleet, tests, recordings | Python 3.10+ (3.12 tested), optional ffmpeg |
| B. ROS 2 workstation | ROS 2 Humble workspace, Gazebo world, RViz | Docker Desktop (WSL2) **or** WSL Ubuntu 22.04 |
| C. Robot | ESP32 firmware + ROS 2 on the Raspberry Pi 4 | Hardware in `HARDWARE_SOFTWARE_REQUIREMENTS.md` |

```bash
git clone https://github.com/Gurjas2112/CHOTU.git
cd CHOTU
```

---

## A. Digital twin (5 minutes)

### Windows 11 (PowerShell)
```powershell
# one-shot: venv + deps + pytest + firmware host tests + 10-room benchmark
powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1

# or step by step
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
python bot_simulation\run_simulation.py            # live HUD window, room seed 2025
scripts\run_sim.bat fleet                           # 4 robots / 4 rooms dashboard
```

### Linux / WSL / macOS
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && pip install -e .
python bot_simulation/run_simulation.py --seed 7
python bot_simulation/run_simulation.py --benchmark 20 --headless
```

### Regenerate the screenshots and videos
```bash
python bot_simulation/record_demo.py --seed 2025      # ~5-8 min on an i7-11800H
# -> bot_simulation/simulation_screenshot_screen_recording/
```
`ffmpeg` on the PATH gives H.264 MP4s. Without it, OpenCV writes `mp4v`.

---

## B. ROS 2 Humble workstation

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
Follow `HARDWARE_SOFTWARE_REQUIREMENTS.md` §2 and the pin table in `ARCHITECTURE.md` §6.
* Keep **one common ground**.
* Put level shifting on every 5 V output (HC-SR04 echo, encoders).
* Fit a flyback diode across the vacuum motor.

### C2. Flash the ESP32-S3
```bash
pip install platformio
bash scripts/flash_esp32.sh            # or: cd firmware/esp32s3_base_controller && pio run -t upload
```
At boot the robot must be **still on the dock** for about 1 s while the gyro calibrates. Two short beeps mean it is ready.

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
