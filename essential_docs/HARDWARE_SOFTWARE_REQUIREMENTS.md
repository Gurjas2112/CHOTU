# Hardware and Software Requirements

> The v2 prototype reuses everything the team bought for AtomQuest 2025 (see `Atomquest_bot_cost_sheet.xlsx` and the bills folder). Items marked **NEW** are the additions needed for autonomy. Prices are INR from Indian hobby stores (Robu, Robocraze, Amazon) at the time of the build. Production-grade parts are out of scope for this prototype.

## 1. Bill of materials: hybrid Pi 4 + ESP32-S3 prototype

| # | Part | Qty | Unit ₹ | Total ₹ | Status | Role |
|---|---|---|---|---|---|---|
| 1 | BO motor + 65 mm wheel + 20-slot encoder disc + LM393 sensor (combo, Bill-1) | 2 | 260 | 520 | owned | Drive + odometry |
| 2 | Caster ball | 1 | 20 | 20 | owned | Third contact point |
| 3 | MDF board (chassis) | 1 | 250 | 250 | owned | Base plate Ø 34 cm |
| 4 | PLA PRO+ filament 1 kg (Bill-1) | 1 | 180 | 180 | owned | Brackets, container, sensor mounts |
| 5 | L298N dual H-bridge 2 A | 1 | 150 | 150 | owned | Drive motors |
| 6 | HC-SR04 ultrasonic | 3 | 50 | 150 | 1 owned + **2 NEW** | Left / centre / right obstacles |
| 7 | GY-53 VL53L0X ToF laser ranging | 1 | 180 | 180 | owned | Precise front distance |
| 8 | MPU6050 gyro/accel (Bill-1) | 1 | 140 | 140 | owned | Heading for odometry |
| 9 | SW-420 vibration sensor | 1 | 40 | 40 | owned | Bump detection |
| 10 | TCRT5000 IR reflective sensor | 2 | 40 | 80 | **NEW** | Cliff / stair detection |
| 11 | Raspberry Pi 5 MP camera + cable (Bill-1) | 1 | 720 | 720 | owned | YOLOv8n suck/avoid |
| 12 | **Raspberry Pi 4 Model B, 4 GB** | 1 | 5,199 | 5,199 | **NEW** (pitch) | ROS 2 brain |
| 13 | microSD 32 GB A1 | 1 | 350 | 350 | **NEW** | Ubuntu 22.04 Server arm64 |
| 14 | **ESP32-S3-DevKitC-1 (N8R8)** | 1 | 950 | 950 | **NEW** (replaces XIAO cam) | Real-time base controller |
| 15 | Bergmann "tornado" 12 V 60 W vacuum motor | 1 | 500 | 500 | owned | Suction |
| 16 | Side brush | 1 | 60 | 60 | owned | Debris sweep |
| 17 | IRLZ44N logic-level MOSFET module | 2 | 60 | 120 | **NEW** | Vacuum / brush PWM |
| 18 | 18650 Li-ion cells (3S configuration) | 8 | 100 | 800 | owned | 11.1 V pack |
| 19 | Battery holders | 4 | 25 | 100 | owned | |
| 20 | 3S 20 A BMS | 1 | 220 | 220 | **NEW** | Cell protection, balancing |
| 21 | 3S Li-ion charger | 2 | 18 | 36 | owned | |
| 22 | XL4015 5 V / 5 A buck converter | 1 | 250 | 250 | **NEW** | Clean 5 V for the Pi (separate from motors) |
| 23 | 4-ch bi-directional logic level shifter | 1 | 60 | 60 | **NEW** | 5 V echo/encoder → 3.3 V |
| 24 | Dock: IR LED + TSOP38238 + spring contacts | 1 | 180 | 180 | **NEW** | Docking target and charging contacts |
| 25 | Fuse holder + 10 A fuse + rocker switch + XT60 | 1 | 127 | 127 | **NEW** | Power safety |
| 26 | Jumper wires + perfboard | 1 | 98 | 98 | owned | |
| | **Total** | | | **₹11,480** | | (`PROTOTYPE_BOM_INR` in `chotu_core/config.py`) |

The v1 competition bot cost ₹4,134. The extra ₹7,346 buys autonomy, and the Raspberry Pi 4 alone is ₹5,199 of that. A **cost-down variant** for later would drop the Pi and run YOLO on an ESP32-S3 + OV2640 using ESP-DL, with coverage running on the MCU.

### Parts that are unique to this design and need care

| Part | Why it is special | Notes |
|---|---|---|
| Bergmann tornado vacuum motor | High-current brushed motor (rated 60 W, about 5 A at 12 V) | Use a **logic-level** MOSFET (IRLZ44N) with a flyback diode (1N5822). Do not drive it from the L298N. PWM at 20 kHz to avoid audible whine. |
| HC-SR04 on a 3.3 V MCU | ECHO outputs 5 V | Use a 1 kΩ / 2 kΩ divider or the level shifter on GPIO 13/14/21. |
| VL53L0X + MPU6050 on one I2C bus | Different addresses (0x29 / 0x68) | XSHUT on GPIO 47 lets you add a second ToF later (re-addressing). |
| Single-channel encoders | No direction information | Firmware takes the direction from the commanded wheel speed, as in `main.cpp`. |
| Raspberry Pi 4 power | 5.1 V / 3 A, brown-outs reset Linux | Use a dedicated 5 A buck from the battery, not a USB power bank. Add a 1000 µF capacitor at the buck output. |
| Docking station | Needed for the finale rule "start and end at the dock" | A 30 cm wide block with an IR beacon (38 kHz) and two spring contacts at 12.6 V CV / 2 A. |

## 2. Wiring and power domains

```
11.1 V pack ─ BMS ─ 10 A fuse ─ switch ─┬─ L298N 12 V in ──► BO motors
                                        ├─ IRLZ44N #1 ──► Bergmann vacuum (+ flyback diode)
                                        ├─ IRLZ44N #2 ──► brush motors
                                        ├─ XL4015 buck 5.1 V ──► Raspberry Pi 4 (USB-C / GPIO 5V)
                                        └─ 100k/22k divider ──► ESP32 GPIO1 (battery sense)
Raspberry Pi USB ──► ESP32-S3 DevKitC-1 "UART" port (power + serial link, /dev/ttyUSB0)
ESP32 3V3 ──► VL53L0X, MPU6050, TCRT5000;  5 V (from Pi USB) ──► HC-SR04, encoders, SW-420
COMMON GROUND for all modules (shown in bot_connection_schema.jpeg)
```

The full GPIO table is in `ARCHITECTURE.md` §6 and in `firmware/esp32s3_base_controller/include/pins.h`.

## 3. Software requirements

| Component | Version | Where | Purpose |
|---|---|---|---|
| Windows 11 Home 26H2 (build 26300) | – | Dev workstation | Host OS |
| Python | 3.12.0 (3.10+ supported) | Workstation, CI | chotu_core, simulator, tests |
| numpy / opencv-python / matplotlib | ≥1.21 / ≥4.6 / ≥3.5 | Workstation | Planning, HUD rendering, charts |
| pytest | ≥7 | Workstation, CI | 32 unit + end-to-end tests |
| ffmpeg (libx264) | any recent | Workstation | MP4 recordings (OpenCV fallback if missing) |
| MSYS2 g++ / gdb | 16.2.0 / 18.1 | Workstation | Firmware logic host tests |
| WSL2 Ubuntu | 22.04.2 LTS (jammy) | Workstation | Native ROS 2 alternative |
| Docker Desktop (WSL2 backend) | 29.x | Workstation | ROS 2 dev / sim containers |
| ROS 2 | **Humble Hawksbill** (LTS to 2027) | Docker / Pi 4 | Robot middleware (`ROS_DISTRO` build arg, `kilted` also works) |
| Gazebo | Fortress via `ros-humble-ros-gz` | Docker dev image | Physics simulation |
| CycloneDDS | `rmw_cyclonedds_cpp` | Docker / Pi 4 | DDS middleware |
| PlatformIO Core | ≥6.1, `espressif32@6.9.0` (Arduino-ESP32 2.0.17; core 3.x also supported) | Workstation / CI | Firmware build and flash |
| Pololu VL53L0X library | ^1.3.1 | Firmware | ToF driver |
| Ultralytics | 8.3.40 | RTX 3060 (CUDA 13.2 driver) / Pi 4 (CPU, NCNN) | YOLOv8n training and inference |
| Ubuntu Server 22.04 arm64 | – | Raspberry Pi 4 | Robot OS (Docker Engine + compose plugin) |

## 4. Optional and next-step hardware

| Part | Why |
|---|---|
| 360° 2D LiDAR (RPLIDAR C1 / LD19, about ₹6–8k) | Replaces the ultrasonic arc for SLAM (`slam_toolbox`). This is the "LiDAR + camera fusion" future scope in the pitch. |
| Quadrature (hall) encoders, N20 metal-gear motors | Better odometry (direction plus higher resolution). |
| Second VL53L0X angled down | Carpet edge and step detection. |
| Raspberry Pi 5 + Hailo-8L AI HAT | 30+ FPS YOLO and segmentation for dirt maps. |
