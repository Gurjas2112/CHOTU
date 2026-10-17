# Gazebo Fortress recording: full ROS 2 mission

This is the **real ROS 2 stack** (`chotu_bringup/sim.launch.py`: the mission manager, the `chotu_core` autonomy, the Gazebo sensor adapter and rosbridge) driving CHOTU in `chotu_gazebo/worlds/atomquest_room.sdf`. It runs headless in Docker under Xvfb with Mesa software rendering. An overhead observer camera in the world provides the video.

<p align="center"><img src="03_cover.png" width="80%" alt="Gazebo coverage phase"/></p>

**Full recording:** [`chotu_gazebo_full_mission.mp4`](chotu_gazebo_full_mission.mp4): 229.7 s at 1:1 sim time, 1280 × 720, H.264.

| Flow screenshot | State | Sim time (s) |
|---|---|---|
| `01_undock.png` | UNDOCK | 0.4 |
| `02_scan.png` | SCAN (360°) | 3.5 |
| `03_cover.png` | COVER (boustrophedon) | 7.5 |
| `04_spot_clean.png` | SPOT_CLEAN (frontier fill) | 165.5 |
| `05_return_to_dock.png` | RETURN_TO_DOCK (A*) | 216.7 |
| `06_docking.png` | DOCKING (IR beacon) | 220.7 |
| `07_docked.png` | DOCKED | 226.5 |

From `gazebo_mission_metrics.json`:
* docked at **226.5 s**, inside the 300 s budget
* coverage estimate **97.9 %**
* 111 of 130 waypoints
* **0** stuck recoveries

## Reproduce

```bash
# from the repo root (Git Bash on Windows, or Linux)
docker build -f docker/Dockerfile --target dev -t chotu/dev:3.0.0 .
MSYS_NO_PATHCONV=1 docker run --rm -v "$(pwd -W 2>/dev/null || pwd)":/workspace \
    chotu/dev:3.0.0 bash /workspace/bot_simulation/gazebo_recording/run_gazebo_recording.sh
```

`run_gazebo_recording.sh` does the following:
1. Runs `colcon build` on the workspace.
2. Launches the simulation under `xvfb-run`.
3. Starts `record_gazebo.py`, which subscribes to the overhead camera (RELIABLE QoS), `/odom`, `/chotu/plan` and `/chotu/status`. It composes the HUD, streams frames to ffmpeg, saves one screenshot per new state, and stops when the robot reports `DOCKED`.

**Odometry.** Distance comes from the wheel odometry and heading from the IMU yaw. The caster is frictionless and the tyres use μ = 1.5, so the robot's own pose estimate stays on the true path. The trail in the video is the robot's estimate.
