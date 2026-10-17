# CHOTU: Project Analysis and Autonomy Upgrade Plan

> **Scope.** This file reviews every document in `old_essential_docs/`, records what the December 2025 AtomQuest prototype actually was, and explains how the gaps were turned into the autonomous v2 stack and then the v3 design in this repository (§6).

---

## 1. Source documents reviewed

| Document | What it tells us | Used for |
|---|---|---|
| `Atomquest_2025_Problem_Statement.pdf` | Build a versatile, efficient, smart cleaning bot. Brooms, vacuum or liquid allowed. A challenge room with random obstacles and dry garbage (dust, paper, wire strands, wrappers, hair). Max 1.5 × 1.5 × 1 ft. | Garbage types, size envelope (`RobotConfig`) |
| `Atomquest 2025 Round 3.pdf` | Finale rules: start **at the dock**, clean for **5 min**, **return to the dock** or the attempt is incomplete. Restart penalties. Score weights: time 20, efficiency 25, autonomy and avoidance 20, battery 15, aesthetics 5, container 10, cost 5. | `MissionConfig.time_budget_s`, `scoring.py`, mission FSM |
| `Atomquest_Bot_SpecSheet.pdf` | Team, bot name, autonomous control, 2.4 kg, MDF + PLA, 2 drive wheels + caster, BO motors, XIAO ESP32-S3 Sense, 3× HC-SR04, SW-420, VL53L0X, 2× IR, tornado suction with dual brush, 470 mL container, ~0.25 m/s, ~85 % efficiency (1 m² test). | Geometry, speed, sensors, unique features |
| `Atomquest_Finale_Product_Pitch_Presentation (1).pdf` | Finale architecture: Raspberry Pi 4 (4 GB), YOLOv8n, VL53L0X, MPU6050, encoders, Pi camera, L298N, Bergmann motor, 3S4P 10.4 Ah pack. Battery maths (4.62 A → 130 min). Future scope: SLAM, LiDAR + camera fusion. | Compute split, battery model (`battery_model.py`), vision |
| `Atomquest_bot_cost_sheet.xlsx` | ₹4,134 BOM (ESP32-S3 cam, sensors, Bergmann 12 V 60 W, 8 × 1000 mAh cells, MDF). | Prototype BOM baseline |
| `…_Essential_component_bills/Bill-1..3.pdf`, `motor_prize_label.jpeg` | Invoices: BO motor + wheel + encoder combo, VL53L0X, MPU6050, Pi 5 MP camera, PLA. Bills 2 and 3 are scanned images (no text layer). | BOM line items |
| `Bot_circuit_diagram.jpg` | v1 wiring: ESP32 DevKit, 2× HC-SR04, L298N, BO motors, blower via MOSFET module, 9 V packs for brush motors, 3S LiPo. | Pin map and power domains |
| `bot_connection_schema.jpeg` | v2 wiring: Raspberry Pi 4 GPIO, L298N, wheel encoders, MPU6050, VL53L0X, SW-420, camera, brush motors, vacuum, common ground. | Hybrid architecture (Pi + MCU) |
| `…_Images/*` | Real bot photos (labelled: vacuum motor, sweep blade, container, wheels), parts, before/after cleaning, team photo. | Mechanical reference, README |
| `cleaning_bot_cad_design/*` | CAD renders and videos of the chassis and the dust container. | URDF dimensions |
| `…_Mentor_Review&Feedback_Form.pdf` | Dr. Tejas Pramod Naik (COEP Tech). Improve **motion control and path optimisation**, suction efficiency, **documentation and simulation validation**, and testing time management. | Drove the v2 priorities (see section 4) |
| `essential_research_paper_docs/` | (1) IR + ultrasonic floor robot (Arduino Mega, L298N, relays). (2) Instructables DIY vacuum robot (3D-printed, Sharp IR). (3) **VLM-Vac**: YOLOv8n distilled from a VLM into *suck / avoid* classes with continual learning. | Reactive safety, cliff IR, **suck/avoid perception** |
| `web_cam_object_detection.mp4`, `…_Video.mp4` | Webcam object-detection demo and the Round 3 bot-in-motion video. | Confirms the YOLO pipeline worked on webcam |

## 2. What the December 2025 prototype was

* **Mechanics:** a round MDF base with a box-shaped transparent dust container (two-level storage) and a sweep blade in front of a Bergmann "tornado" vacuum motor. Two yellow BO gear motors drive it, with a ball caster.
* **Control:** the spec sheet says "Autonomous", but the firmware was a **reactive bump-and-turn** loop. The ESP32 read the ultrasonics and turned away from obstacles. It had **no map, no coverage plan, no localisation and no return-to-dock**.
* **Vision:** YOLOv8 ran on a webcam / Pi as a **stand-alone demo**. Its detections did not change the robot's behaviour.
* **Result:** finalist (**Top 10**) and **People's Choice Award** at the Atomberg Innovation Center.

## 3. Gap analysis against the finale rules

| Finale requirement | v1 prototype | Gap | v2 solution (this repo) |
|---|---|---|---|
| Start at dock, **return to dock** | No dock concept | Attempt counted incomplete | Mission FSM `UNDOCK → … → RETURN_TO_DOCK → DOCKING → DOCKED`, A* home path, IR-beacon final approach |
| Finish inside **5 min** | Ran until stopped | Time score lost | Time-budget-aware return: replans the home ETA every second and leaves with a margin |
| **Unknown obstacle layout** | Random bouncing | Missed areas, repeated passes | Online occupancy grid + boustrophedon coverage + A* detours + frontier fill |
| **Obstacle avoidance effectiveness** (20 %) | Front ultrasonic only | Side hits, chair legs, cables | Corridor-projected safety layer (3× US + ToF), cone-aware mapping, bump/cliff, **YOLO keep-out zones for cables** |
| **Efficiency per garbage type** (25 %) | Constant suction | Light debris left, battery wasted | Adaptive suction (ECO / BOOST from vision), spot-clean of detected debris |
| **Battery life** (15 %) | Mixed 9 V packs + 3S | Unclear runtime | Single 3S4P 111 Wh pack, energy model, eco suction (11–20 % energy saved in sim) |
| Mentor: motion control | Open-loop PWM | Drift, uneven speed | Encoder PID per wheel on the ESP32 at 50 Hz, gyro-fused odometry |
| Mentor: simulation validation | None | No evidence before the finale | v2: a digital twin ran **the same `chotu_core` code** as ROS 2 (benchmarks, ablation). v3: the full ROS 2 stack recorded in Gazebo. |
| Mentor: documentation | Slides only | Hard to reproduce | This doc set: setup, configuration, testing, deployment, hardware, specs |

## 4. Decisions for v2 (autonomous)

1. **Hybrid compute.** The **Raspberry Pi 4** runs ROS 2 Humble (mapping, planning, YOLO). The **ESP32-S3** is the real-time base controller (PWM, encoders, sensors, safety watchdog). This uses both boards the team already bought. It also keeps the robot safe if Linux stalls: the ESP32 stops the motors after 300 ms without a command.
2. **One autonomy library (`chotu_core`).** It is pure Python plus numpy. The ROS node drives `CleaningMission.step()` both on the robot and in Gazebo, so every simulated run tests the robot code.
3. **Known room, unknown layout.** The Round 3 rules publish the room shape in advance. The walls are therefore an analytic band, and only obstacles are mapped from noisy echoes. This removes most false walls caused by ultrasonic multipath.
4. **Suck / avoid vision (VLM-Vac).** The camera handles what range sensors cannot see: power cables, socks and liquids become keep-out zones, and debris triggers suction BOOST.
5. **Containerised deployment.** We follow the 2026 Docker-for-ROS-2 guide: versioned multi-stage images, a dev container, explicit `--device` mapping and compose profiles. Production hardening (enclosure, certification, OTA) is **deliberately postponed**. This release is a prototype.

## 5. Measured results of the v2 stack (digital twin, commit `9757b23`)

These numbers come from the v2 Python digital twin (since removed from the repo; it remains in git history at `9757b23`), using randomised AtomQuest rooms of 10 ft × 10 ft. Each room has 2 boxes, 1 chair, 1 bin, 1 power cable and 85 garbage items of five types. The simulation includes sensor noise and odometry drift. The raw data is in git history (`bot_simulation/simulation_screenshot_screen_recording/` at `9757b23`), and the 40 runs also seed `backend/sample_data/missions.json`.

| Metric (10 random rooms) | Vision ON | Vision OFF (ablation) |
|---|---|---|
| Returned to dock within 5 min | **10 / 10** | 10 / 10 |
| Mean area coverage | 73.5 % | 79.2 % |
| Mean debris pick-up by mass (dust / hair / paper / wrapper / wire) | **80 / 73 / 74 / 68 / 75 %** | 65 / 58 / 55 / 45 / 50 % |
| Power-cable incidents (brush tangles) | **1** | 38 |
| Mean projected AtomQuest score | **78.8 / 100** | 63.9 / 100 |

A 40-room robustness run (seeds 10–49) gave these results: 40/40 docked, 39/40 within 300 s (worst 308.9 s), mean coverage 70.0 %, minimum coverage 48.7 % (a cluttered room), and a mean score of 77.6.

Limits are stated honestly. These figures come from a simulator, not from the physical robot, which was not available for this iteration. Coverage is bounded by the 0.25 m/s top speed, because 5 minutes is not enough to sweep 9.3 m² twice. Avoiding cables and detouring to detected debris costs about 6 points of area, but it raises pick-up by mass. The known weak spot is a tightly cluttered room, where map-induced pockets cost time. The worst of 50 rooms docked 8.9 s late. The hardware test plan in `TESTING.md` will calibrate the simulator against the real robot.

## 6. v3: one Atomberg-standard design (prototype, demo data)

v3 keeps the v2 autonomy and turns the prototype into a buildable, single-path design. The reasoning and sources are in [ATOMBERG_ENGINEERING_REVIEW.md](ATOMBERG_ENGINEERING_REVIEW.md).

| Area | v3 decision | Evidence in this repo |
|---|---|---|
| Hardware | Reuse the AtomQuest parts. Retire the L298N for the **TB6612FNG** and the IRF520 for the **IRLZ44N**. Keep the **Bergmann BAV-60**. | `docs/HARDWARE_SOFTWARE_REQUIREMENTS.md` (₹13,693, of which ₹9,999 to buy) |
| Firmware | STBY safety cut on GPIO2, dock IR on GPIO3, buzzer removed, `FLAG_DOCK_IR` | `firmware/…/pins.h`, host tests |
| Wiring | Carrier PCB generated from code. A test checks it against `pins.h`. | `hardware/pcb/`, `tests/test_pcb_netlist.py` |
| Body | 28 parametric printed parts with an automatic FDM review | `bot_3d_printing/` |
| ROS 2 | rosbridge app API, `SetZones` no-go zones, operator dock, overhead Gazebo recording | `ros2_ws/`, `bot_simulation/gazebo_recording/` |
| App | Flutter app with a demo robot, rosbridge client, backend client | `mobile_app/` (recordings in `mobile_app/app_screenshot_screen_recording/`) |
| Backend | FastAPI fleet API on sample data; PostgreSQL path tested | `backend/` |
| Excluded | A VLM, an agentic layer and a cloud dependency score nothing in the rubric and add latency and running cost | Review §5 |
