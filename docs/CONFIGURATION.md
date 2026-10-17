# Configuration Guide

Configuration lives in six places. Change values in **one** place and keep the mirrors in sync, as marked below.

| File | Scope | Mirrors |
|---|---|---|
| `chotu_core/config.py` | Robot geometry, sensors, room, mission tuning, power model, BOM cost | Source of truth for the sim and the ROS nodes |
| `ros2_ws/src/chotu_bringup/config/chotu_params.yaml` | ROS 2 runtime parameters (overrides) | Room, dock, lane spacing, speed, serial port, YOLO |
| `firmware/esp32s3_base_controller/include/config.h` | Firmware rates, PID, geometry, PWM | Wheel base and radius, ticks/rev, stop distance |
| `firmware/esp32s3_base_controller/include/pins.h` | GPIO map | `ARCHITECTURE.md` §6 and `hardware/pcb/chotu_carrier.py` (checked by `tests/test_pcb_netlist.py`) |
| `backend/.env` (see `.env.example`) | Fleet backend: store, database URL, robot link, API key | – |
| Flutter `--dart-define` | App build: `BACKEND_URL`, `BACKEND_KEY`, `ROBOT_ID`, `TOUR` | – |

## 1. Room and docking station (`RoomConfig`, `chotu_params.yaml`)

The organisers publish the room shape before the run.

| Key | Default | Meaning |
|---|---|---|
| `room.width`, `room.height` / `room_width_m`, `room_height_m` | 3.048 m (10 ft) | Inner wall-to-wall size. The walls form an analytic no-go band. |
| `room.dock_x`, `dock_y`, `dock_theta` | 1.524, 0.19, π/2 | Robot centre when docked. The origin is the south-west corner and the robot leaves facing +y. |

Measure the dock position with a tape on the day and edit `chotu_params.yaml`. Nothing needs rebuilding.

## 2. Mission tuning (`MissionConfig`)

| Key | Default | Effect / tuning hint |
|---|---|---|
| `time_budget_s` | 300 | AtomQuest session length |
| `return_margin_s` | 14 | Safety margin before leaving for the dock. Raise it if docking is slow on the real floor. |
| `lane_spacing` | 0.22 | Smaller means more overlap and slower runs. Must be less than the 0.24 m cleaning width. |
| `wall_margin` | 0.24 | Distance of the first lane from the walls |
| `grid_resolution` | 0.05 | Map cell size. 0.025 m is finer but A* gets about 4× slower on the Pi. |
| `inflation_margin` | 0.02 | Extra clearance beyond the 0.17 m radius |
| `stop_distance` / `slow_distance` | 0.05 / 0.12 | Reactive layer distances, measured from the chassis rim along the travel corridor |
| `stuck_timeout_s` | 1.5 | Time blocked before stuck recovery starts |
| `scan_turn_rate` | 1.4 rad/s | Initial 360° mapping spin |
| `waypoint_step` | 0.30 | Waypoint spacing along a lane |

## 3. Robot and sensors (`RobotConfig`, `SensorConfig`)

| Key | Default | Notes |
|---|---|---|
| `radius` | 0.17 m | Chassis radius. The planner keeps the centre ≥ radius + margin from obstacles. |
| `wheel_base`, `wheel_radius` | 0.26 m, 0.0325 m | Measure them. Odometry depends directly on these. |
| `encoder_ticks_per_rev` | 20 | Slots on the encoder disc. Use 40 if the firmware counts CHANGE edges. |
| `max_linear`, `max_angular` | 0.25 m/s, 1.8 rad/s | Spec-sheet coverage speed |
| `cleaning_width` | 0.24 m | Brush + nozzle swept width |
| `ultrasonic_angles_deg` | (35, 0, -35) | Mounting yaw of the three HC-SR04 |
| `ultrasonic_max` / `tof_max` | 1.5 / 1.2 m | Ranges beyond these count as "no echo" |
| `camera_fov_deg`, `camera_range` | 62°, 1.1 m | Pi camera v1.3 horizontal FOV |

Camera floor projection (`perception.CameraModel`) uses a mount height of 0.16 m, a 28° down tilt and a 0.15 m forward offset. Re-measure these after mounting the camera. A wrong tilt shifts every detection forward or backward.

## 4. Firmware (`config.h`)

| Macro | Default | Notes |
|---|---|---|
| `LINK_BAUD` | 115200 | Must match the `baud` parameter of `serial_bridge_node` |
| `CONTROL_HZ` | 50 | PID and telemetry rate |
| `WATCHDOG_MS` | 300 | Motors and vacuum stop if no frame arrives within this time |
| `PID_KP / KI / KD` | 1.6 / 6.0 / 0 | Wheel speed PID, output in PWM counts |
| `FEEDFORWARD_PWM_PER_MM_S` | 2.6 | Open-loop term. Tune it so the wheel nearly reaches speed with KI=0. |
| `MIN_MOVE_PWM` | 330 | Stiction of the BO motors at 11.1 V |
| `STOP_DISTANCE_MM` | 50 | Hardware front stop (centre US / ToF) |
| `BATT_DIVIDER_RATIO` | 122/22 | Matches the 100 k / 22 k resistor divider |

**PID tuning procedure.**
1. Lift the robot. Set `PID_KI=0` and `KP=0`.
2. Command `cmd_vel 0.2 m/s` and raise `FEEDFORWARD` until the wheel speed reported in `/odom` is about 0.18 m/s.
3. Add `KP` until the steps are crisp.
4. Add `KI` until there is no steady-state error.

## 5. Perception (`chotu_yolo_detector`)

| Param | Pi 4 | RTX 3060 |
|---|---|---|
| `weights` | `/opt/chotu/models/chotu_suck_avoid_yolov8n_ncnn_model` | `models/chotu_suck_avoid_yolov8n.pt` |
| `device` | `cpu` | `0` |
| `imgsz` | 320 | 640 |
| `max_fps` | 5 | 15 |
| `conf` | 0.35 | 0.35 |

Classes and their actions are defined in `chotu_core/perception.py` (`SUCK_CLASSES`, `AVOID_CLASSES`). To add a class, add it to the dataset YAML, retrain, and list it in the right set.

## 6. DDS and network

* `ROS_DOMAIN_ID=42` is set in compose. Change it if several robots share a network.
* `RMW_IMPLEMENTATION=rmw_cyclonedds_cpp`, with the profile in `docker/cyclonedds.xml`.
* Containers use `network_mode: host`, which gives the simplest DDS discovery. The 2026 Docker-for-ROS-2 guide recommends the same.

## 7. Gazebo simulation

| Setting | Where | Meaning |
|---|---|---|
| `rviz:=true` / `vision:=false` | `ros2 launch chotu_bringup sim.launch.py …` | Open RViz. Run without the YOLO node (no camera model needed). |
| Room, obstacles, dock, overhead camera | `ros2_ws/src/chotu_gazebo/worlds/atomquest_room.sdf` | The AtomQuest 10 × 10 ft layout |
| Wheel/caster friction | `ros2_ws/src/chotu_description/urdf/chotu.urdf.xacro` | Caster μ = 0, tyres μ = 1.5 |
| Bridged topics | `ros2_ws/src/chotu_bringup/config/gz_bridge.yaml` | Gazebo ↔ ROS topics, including `/overhead/image` |

## 8. Fleet backend (`backend/.env`)

| Variable | Default | Meaning |
|---|---|---|
| `CHOTU_STORE` | `sample` | `sample` serves `backend/sample_data/*.json` from memory, with no database. `sql` uses `DATABASE_URL`. |
| `DATABASE_URL` | – | For example `postgresql+psycopg://chotu:chotu@localhost:5432/chotu` |
| `CHOTU_ROBOT_LINK` | `demo` | `demo` replays the Gazebo mission. `rosbridge` connects to each robot's `endpoint`. |
| `CHOTU_REPLAY_SPEED` | `1.0` | Demo replay speed factor |
| `CHOTU_API_KEY` | empty | Required `X-API-Key` header (or `?api_key=` on the WebSocket). Leave it empty only on a local machine. |
| `CHOTU_CORS_ORIGINS` | `*` | Comma-separated origins allowed to call the API from a browser |

## 9. Mobile app build flags

| Flag | Default | Meaning |
|---|---|---|
| `--dart-define=BACKEND_URL=http://host:8000` | off | Loads mission history and schedules from the backend, and stores no-go zones there too |
| `--dart-define=BACKEND_KEY=...` | empty | Sent as `X-API-Key` |
| `--dart-define=ROBOT_ID=chotu-01` | `chotu-01` | Which fleet robot this phone controls |
| `--dart-define=TOUR=true` | off | Scripted demo tour used for the recording |
