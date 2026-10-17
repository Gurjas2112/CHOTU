# Hardware and Software Requirements (v3)

> **One design.** CHOTU v3 is a Raspberry Pi 4 + ESP32-S3 hybrid. It reuses every part the team bought for AtomQuest 2025 that is still fit for purpose; see `old_essential_docs/Atomquest_bot_cost_sheet.xlsx` and `old_essential_docs/AtomQuest2025_HackOGiants_PESMCOE_Essential_component_bills/`. The BOM has no alternatives or "optional" rows. The reasons for each choice, with sources, are in [ATOMBERG_ENGINEERING_REVIEW.md](ATOMBERG_ENGINEERING_REVIEW.md).
>
> **Status:** prototype on demo data. Nothing in the *to buy* column has been purchased yet. Prices are INR, taken from robu.in product pages and the team's own bills. Check them again when ordering.

## 1. Bill of materials

### 1a. Reused from the AtomQuest build (already owned)

| # | Part | Qty | ₹ (bill) | Role in v3 |
|---|---|---|---|---|
| 1 | BO motor + 65 mm wheel + 20-slot encoder disc + LM393 sensor (Bill-1 combo) | 2 | 520 | Drive + odometry |
| 2 | Caster ball | 1 | 20 | Third contact point (printed `caster_spacer`) |
| 3 | MDF board | 1 | 250 | Ø 300 mm base plate (`bot_3d_printing/dxf/mdf_base_template.dxf`) |
| 4 | PLA PRO+ filament 1 kg (Bill-1) | 1 | 180 | Non-structural prints: deck pillars, lid tiles, cliff mounts |
| 5 | HC-SR04 ultrasonic | 1 | 50 | Centre range sensor |
| 6 | GY-53 VL53L0X ToF | 1 | 180 | Precise front distance + docking |
| 7 | MPU6050 (Bill-1) | 1 | 140 | Gyro heading |
| 8 | SW-420 vibration sensor | 1 | 40 | Bump detection |
| 9 | Raspberry Pi 5 MP camera + cable (Bill-1) | 1 | 720 | YOLOv8n suck/avoid |
| 10 | **Bergmann MGA Tornado BAV-60** 12 V / 60 W motor (`motor_prize_label.jpeg`) | 1 | 500 | Suction, 6.5 kPa class |
| 11 | Side brush + motor | 1 | 60 | Debris sweep into the nozzle |
| 12 | 18650 Li-ion cells | 8 | 800 | 3S pack, 11.1 V |
| 13 | Battery holders | 4 | 100 | |
| 14 | 3S Li-ion charger | 2 | 36 | Bench charging and dock supply |
| 15 | Jumper wires | 1 | 98 | Sensor leads to the carrier PCB's JST sockets |
| | **Reused subtotal** | | **₹3,694** | |

Two parts the team owns are **retired**: the L298N (replaced by the TB6612FNG) and the IRF520 MOSFET module (replaced by the IRLZ44N). They stay as bench spares and are not counted.

### 1b. To buy

| # | Part | Qty | Unit ₹ | Total ₹ | Source | Role |
|---|---|---|---|---|---|---|
| 16 | Raspberry Pi 4 Model B, 4 GB | 1 | 5,199 | 5,199 | finale pitch price; [robu.in search](https://robu.in/?s=raspberry+pi+4+model+b+4gb&post_type=product) | ROS 2 brain |
| 17 | microSD 32 GB A1 | 1 | 350 | 350 | local | Ubuntu 22.04 Server arm64 |
| 18 | ESP32-S3-DevKitC-1 (N16R8) | 1 | 950 | 950 | [robu.in](https://robu.in/product/esp32-s3-devkit-esp32-s3-wroom-1-n16r8/) | Real-time base controller |
| 19 | HC-SR04 ultrasonic | 2 | 50 | 100 | robu.in | Left / right range sensors |
| 20 | TCRT5000 IR reflective sensor | 2 | 39 | 78 | [robu.in](https://robu.in/product/tcrt-5000/) | Cliff detection |
| 21 | **TB6612FNG** dual motor driver | 1 | 149 | 149 | [robu.in](https://robu.in/product/motor-driver-tb6612fng-module-performance-ultra-small-volume-3-pi-matching-performance-ultra-l298n/) | Drive motors, replaces the L298N |
| 22 | **IRLZ44N** logic-level MOSFET | 2 | 60 | 120 | robu.in | Vacuum + brush PWM, replaces the IRF520 |
| 23 | 3S 20 A 18650 BMS | 1 | 266 | 266 | [robu.in](https://robu.in/product/3-series-20a-18650-lithium-battery-protection-board-11-1v-12v-12-6v/) | Cell protection and balancing |
| 24 | XL4015 5 V / 5 A buck | 1 | 250 | 250 | [robu.in](https://robu.in/product/xl4015-5a-dc-dc-step-down-adjustable-buck-module/) | Clean 5.1 V for the Pi and ESP32 |
| 25 | Dock kit: TSOP38238 + 940 nm IR LED + 2 spring contacts | 1 | 180 | 180 | [robu.in TSOP38238](https://robu.in/product/ir-receiver-diode-tsop38238/) | IR beacon + charging contacts |
| 26 | XT60 pair + ATO fuse holder + 10 A fuse + rocker switch | 1 | 127 | 127 | robu.in | Power entry and safety |
| 27 | CHOTU carrier PCB, 2-layer, 5 pcs + SMD passives + JST-XH sockets | 1 | 900 | 900 | JLCPCB estimate incl. shipping (`hardware/pcb/protoflow/bom_jlcpcb.csv`) | Replaces breadboard and jumper wiring |
| 28 | PETG filament 1 kg (natural / clear) | 1 | 1,000 | 1,000 | robu.in / local | Structural prints: bumper shell, nozzle, bin, cradle, dock |
| 29 | 10 × 3 mm N52 disc magnets | 12 | 15 | 180 | local | Quick-release hatch, bin and cradle |
| 30 | M3 screw + brass heat-set insert kit | 1 | 150 | 150 | local | Shell, lid tiles, brackets |
| | **To-buy subtotal** | | | **₹9,999** | | |

### 1c. Total

| | ₹ |
|---|---|
| Reused | 3,694 |
| To buy | 9,999 |
| **Prototype total** | **₹13,693** (`PROTOTYPE_BOM_INR` in `chotu_core/config.py`) |

**Where the money goes.** The Raspberry Pi 4 accounts for 38 % of the total. The cost of the parts the team actually needs to buy is ₹9,999.

**Note on recorded runs.** The v2 digital-twin benchmark (commit `9757b23`) ran while the BOM was ₹11,480. The AtomQuest cost criterion is worth 5 points and scales linearly from ₹5k (full marks) to ₹15k (zero). At ₹13,693 a run therefore scores 0.65 points on cost instead of 1.76, which lowers the total by about 1.1 points. The v2 figures are quoted as recorded.

### Parts that need care

| Part | Why | What to do |
|---|---|---|
| Bergmann BAV-60 | About 5 A at 12 V, brushed, inductive | Drive it from an IRLZ44N low-side switch with a 1N5822 flyback diode on the carrier PCB. Use 20 kHz PWM so there is no audible whine. Never drive it from a motor-driver channel. |
| TB6612FNG | VM limit is 13.5 V; a full 3S pack is 12.6 V | Within the limit. Do not connect it to a 4S pack. STBY (GPIO2) has a 10 k pull-down, so the motors are off at boot. |
| HC-SR04 and LM393 outputs | 5 V logic into a 3.3 V MCU | The carrier PCB divides each signal with 1 k / 2 k resistors (tested in `tests/test_pcb_netlist.py`). |
| VL53L0X + MPU6050 | One I²C bus at addresses 0x29 / 0x68 | Use the 4.7 k pull-ups on the PCB. XSHUT (GPIO47) is wired for re-addressing. |
| Single-channel encoders | They carry no direction information | The firmware takes the direction from the commanded wheel speed (`main.cpp`). |
| Raspberry Pi 4 power | 5.1 V / 3 A; a brown-out resets Linux | Power it from the dedicated XL4015 rail, which has a 1000 µF capacitor at the output. Never use a USB power bank. |
| Dock | Finale rule: start and end at the dock | Use the 3D-printed `dock_station`, with a 38 kHz IR beacon and spring contacts carrying 12.6 V CV / 2 A. |

## 2. Wiring and power domains

```
11.1 V pack ─ BMS ─ XT60 ─ 10 A fuse ─ rocker ─┬─ TB6612FNG VM ─────────► 2 × BO motor (+ encoders)
                                               ├─ IRLZ44N Q1 + 1N5822 ───► Bergmann BAV-60 vacuum
                                               ├─ IRLZ44N Q2 + 1N5822 ───► side-brush motor
                                               ├─ XL4015 → +5V (1000 µF) ┬► Raspberry Pi 4 (GPIO pins 2/6)
                                               │                         ├► ESP32-S3 DevKitC 5V0
                                               │                         └► HC-SR04 ×3, encoders
                                               └─ 100 k / 22 k divider ──► ESP32 GPIO1 (battery sense)
ESP32 3V3 ─► TB6612 VCC, VL53L0X, MPU6050, SW-420, TCRT5000 ×2, TSOP38238
Raspberry Pi USB ◄──► ESP32-S3 UART port (COBS + CRC16 link, /dev/ttyUSB0)
Star ground: motor and vacuum returns meet logic ground at one point on the PCB
```

The board itself is described in [`hardware/pcb/README.md`](../hardware/pcb/README.md): schematic sheets, KiCad netlist and the Protoflow hand-off. The GPIO table is in [ARCHITECTURE.md §6](ARCHITECTURE.md#6-esp32-s3-devkitc-1-pin-map) and in `firmware/esp32s3_base_controller/include/pins.h`. A test keeps those two in sync.

## 3. Software requirements

| Component | Version | Where | Purpose |
|---|---|---|---|
| Python | 3.12.0 (3.10+ supported) | Workstation, CI | `chotu_core`, backend, tools |
| numpy / opencv-python / matplotlib | ≥1.21 / ≥4.6 / ≥3.5 | Workstation | Planning, HUD rendering, charts |
| pytest | ≥7 | Workstation, CI | Python test suites |
| FastAPI / SQLAlchemy / pydantic / uvicorn | 0.137 / 2.1 / 2.13 / 0.44 (tested) | Workstation, Docker | Fleet backend (`backend/`) |
| PostgreSQL | 16 (Docker `postgres:16-alpine`) | Docker / server | Backend persistence (`CHOTU_STORE=sql`) |
| Flutter / Dart | 3.16.9 / 3.2.6 | Workstation | Mobile app (`mobile_app/chotu_app`) |
| CadQuery / trimesh | 2.8 / 4.x | Workstation | Parametric printed body (`bot_3d_printing/`) |
| SKiDL / schemdraw | 3.0 / 0.23 | Workstation | PCB netlist + schematic sheets (`hardware/pcb/`) |
| Protoflow | desktop app (KiCad-based) | Workstation | PCB layout, Gerbers and STEP from the netlist |
| ffmpeg (libx264) | any recent | Workstation, Docker | MP4 recordings |
| Playwright (Chromium) | 1.5x | Workstation | App recording and dashboard screenshots |
| MSYS2 g++ | 16.2.0 | Workstation | Firmware logic host tests |
| Docker Desktop (WSL2 backend) | 29.5.2 | Workstation | ROS 2 dev / Gazebo, backend + PostgreSQL |
| ROS 2 | **Humble Hawksbill** (LTS to 2027) | Docker / Pi 4 | Robot middleware |
| Gazebo | Fortress via `ros-humble-ros-gz` | Docker image `chotu/dev:3.0.0` | Physics simulation and recording |
| rosbridge_suite | `ros-humble-rosbridge-server` | Docker / Pi 4 | App and backend API on `ws://<pi>:9090` |
| CycloneDDS | `rmw_cyclonedds_cpp` | Docker / Pi 4 | DDS middleware |
| PlatformIO Core | ≥6.1, `espressif32@6.9.0` (Arduino-ESP32 2.0.17; core 3.x also supported) | Workstation / CI | Firmware build and flash |
| Pololu VL53L0X library | ^1.3.1 | Firmware | ToF driver |
| Ultralytics | 8.3.40 (CPU torch 2.4.1 in Docker) | RTX 3060 (CUDA) / Pi 4 (CPU, NCNN) | YOLOv8n training and inference |
| Ubuntu Server 22.04 arm64 | – | Raspberry Pi 4 | Robot OS (Docker Engine + compose plugin) |
