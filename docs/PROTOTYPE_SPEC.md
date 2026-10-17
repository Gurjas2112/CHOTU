# CHOTU v3: Prototype Specification Sheet

> This updates `Atomquest_Bot_SpecSheet.pdf` (Round 3, October 2025) for the autonomous v3 prototype. This is a prototype on demo data: no v3 hardware has been bought or built yet, and every performance number below comes from simulation (Gazebo, or the v2 digital-twin benchmark where marked).

## 1. General

| Parameter | Specification |
|---|---|
| Team | Hack O' Giants, PES Modern College of Engineering, Pune |
| Members | Gurjas Singh Gandhi, Joy Johnson Kujur, Sumedh Khedekar, Prathamesh Lohar, Dipali Gode (SY MCA); Swapnil Kulkarni (Mechanical) |
| Faculty / industry mentor | Dr. Tejas Pramod Naik, Assistant Professor, Mechanical Engineering, COEP Technological University |
| Bot name | **CHOTU**, "Compact Home Operations & Tidying Unit" |
| Version | 3.0.0 (autonomous prototype), up from 1.0 (AtomQuest 2025 finale) |
| Control type | **Fully autonomous** (dock → map → coverage → dock). Supervision is through the Flutter app (start, dock, no-go zones) and an e-stop. |

## 2. Physical

| Parameter | v1 (finale) | v3 prototype |
|---|---|---|
| Footprint / height | ≤ 1.5 × 1.5 ft, ≤ 1 ft | Ø 306 mm round, 230 mm tall (within limits) |
| Weight | 2.4–2.8 kg | ≈ 2.9 kg (adds Pi 4 and BMS) |
| Chassis | MDF + PLA | Reused MDF base + 28 parametric PETG/PLA printed parts (CadQuery, every part fits a 220 mm bed) |
| Drive | 2 × BO 200 RPM + caster | Same, plus 20-slot encoders and closed-loop PID |
| Max / coverage speed | ~0.25 m/s | 0.25 m/s cruise, 1.8 rad/s turn |

## 3. Power

| Parameter | Value |
|---|---|
| Battery | 3S Li-ion, 11.1 V nominal (12.6 V full), 10 Ah, 111 Wh, with 3S BMS |
| Average power, cleaning (simulated) | ≈ 43 W (Pi 4 6.4 W, drive ≤ 6 W, vacuum 36 W × duty^1.5, brush 3 W) |
| Runtime per charge | ≈ 2.2 h at average load (model) and 2.17 h per the pitch calculation (4.62 A). That is **≥ 26 AtomQuest runs** per charge. |
| Charge time | 2–3 h (2 A CV/CC through dock contacts) |
| Energy per 5-min mission | ≈ 3.4 Wh (simulated) |
| Adaptive suction saving | 11–20 % vs. constant full suction (simulated) |

## 4. Compute and electronics

| Parameter | Value |
|---|---|
| High-level computer | Raspberry Pi 4 Model B 4 GB, Ubuntu 22.04 arm64, ROS 2 Humble in Docker |
| Real-time controller | ESP32-S3-DevKitC-1 (dual-core 240 MHz), Arduino framework / PlatformIO |
| Link | UART 115200 baud, COBS + CRC16 frames, 50 Hz telemetry, 300 ms watchdog |
| Motor driver | TB6612FNG (drive, STBY safety cut); 2 × IRLZ44N MOSFET (vacuum, brush), 20 kHz PWM |
| Wiring | CHOTU carrier PCB (2-layer, 54 parts, 45 nets) instead of breadboard and jumpers |
| App / fleet | Flutter app over rosbridge (`ws://<pi>:9090`); FastAPI fleet backend with PostgreSQL |

## 5. Sensors

| Sensor | Qty | Range / rate | Use |
|---|---|---|---|
| HC-SR04 ultrasonic | 3 (±35°, 0°) | 2–150 cm, ~17 Hz each | Obstacle mapping and avoidance |
| VL53L0X ToF | 1 (front) | 3–120 cm, 50 Hz | Precise front stop and docking |
| MPU6050 | 1 | ±500 °/s, 50 Hz | Heading (gyro-fused odometry) |
| Wheel encoders (LM393) | 2 | 20 ticks/rev (10.2 mm/tick) | Odometry, wheel PID |
| SW-420 | 1 | interrupt | Bump detection |
| TCRT5000 | 2 | digital | Cliff detection |
| TSOP38238 | 1 | 38 kHz | Dock IR beacon |
| Pi camera 5 MP | 1 | 640×480, YOLO at 5 FPS | Suck/avoid detection |

## 6. Cleaning

| Parameter | Value |
|---|---|
| Mechanism | Side brush feeding a 200 mm printed nozzle on the Bergmann BAV-60 (6.5 kPa class), swept width 24 cm |
| Container | ≈ 557 mL clear PETG bin with an anti-spill standpipe and a magnetic quick-release hatch |
| Garbage handled | Dust, hair, paper scraps, wrappers, wire strands (AtomQuest list) |
| Suction modes | OFF / ECO 55 % / BOOST 100 % (camera-triggered) |
| Pick-up efficiency (sim, per type, 10 rooms) | dust 0.80, hair 0.73, paper 0.74, wrapper 0.68, wire strand 0.75 |

## 7. Autonomy and performance (Gazebo run; randomised rooms from the v2 digital-twin benchmark (commit `9757b23`))

| Metric | Value |
|---|---|
| Docking success | 10 / 10 rooms (and 40 / 40 in the robustness run, 39 of them inside 300 s) |
| Mean coverage of reachable floor | 73.5 % (10 rooms), 70.0 % (40 rooms) |
| Mean dock-to-dock time | 284 s (time-budget aware) |
| Dock alignment error | ≈ 3 cm (IR-beacon approach) |
| Collisions per run | 0–2 (light contacts) |
| Power-cable incidents | 1 in 10 rooms with AI vision vs. 38 without |
| Projected AtomQuest score | 78.8 / 100 (10 rooms), 77.6 (40 rooms) |
| Gazebo Fortress run (ROS 2 stack, same code) | Docked at 226.5 s, coverage estimate 97.9 %, 0 recoveries |

## 8. Development workstation used for this prototype

| Item | Value |
|---|---|
| Device | HSGPC laptop, Windows 11 Home 26H2 (OS build 26300.9550 / 26300.9711) |
| CPU / RAM | Intel Core i7-11800H @ 2.30 GHz (8C/16T) / 16 GB (15.7 GB usable) |
| GPU | NVIDIA GeForce RTX 3060 Laptop 6 GB (+ Intel UHD), CUDA toolkit 13.2 (V13.2.78) |
| Storage | 954 GB SSD (598 GB used) |
| Python | 3.12.0 (Windows), 3.10.12 (WSL) |
| C/C++ | MSYS2 g++ 16.2.0, GNU gdb 18.1 |
| Linux | WSL2 Ubuntu 22.04.2 LTS (jammy) |
| Containers | Docker 29.5.2 (Docker Desktop, WSL2 backend) |

**What runs where during prototyping:**
* Tests, the CAD and PCB pipelines, the backend and the app recordings run natively on Windows (Python 3.12, Flutter 3.16).
* YOLOv8n training runs on the RTX 3060 (batch 16 fits in 6 GB).
* ROS 2 Humble and Gazebo (including the recorded mission) run in the Docker dev image `chotu/dev:3.0.0`, or natively in WSL with `scripts/setup_wsl_ros2_humble.sh`.
* Firmware host tests use MSYS2 g++. Run them from PowerShell or cmd, because Git Bash's MSYS environment conflicts with the UCRT64 toolchain.
