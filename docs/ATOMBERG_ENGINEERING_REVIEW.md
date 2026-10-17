# Atomberg Engineering Review: What CHOTU v3 Needs, and What It Does Not

> **Question asked.** Review CHOTU the way an Atomberg engineer would: affordable, sustainable, high quality and scalable. Decide whether the hardware from the AtomQuest build is enough, whether the Bergmann motor should give way to a 7530 blower or a WPV40 pump, and whether a VLM, an agentic layer, an app and a backend are needed. Give **one** choice for each item, not a list of options, and cite sources.
>
> **Status.** Prototype on demo data. No v3 hardware has been bought. Every performance number comes from simulation: the Gazebo run in `bot_simulation/gazebo_recording/` or the v2 digital-twin benchmark (commit `9757b23`).

## 1. From the problem statement to each decision

The AtomQuest 2025 Round 3 rubric (`old_essential_docs/Atomquest 2025 Round 3.pdf`) awards points for **time 20, efficiency per garbage type 25, autonomy and avoidance 20, battery 15, container 10, aesthetics 5, cost 5**. A part or a feature earns its place only if it moves one of those numbers, or if it is needed to finish the run (start at the dock and return to it within 5 minutes).

| Rubric item | What moves it | v3 decision |
|---|---|---|
| Efficiency (25) | Suction pressure at the nozzle, brush feed, picking up debris the camera sees | Keep the Bergmann BAV-60 (6.5 kPa class). Adaptive ECO/BOOST suction. YOLOv8n *suck* classes. |
| Autonomy and avoidance (20) | Mapping, coverage, cable avoidance, returning to the dock | On-board ROS 2 autonomy. YOLOv8n *avoid* classes. A* return. IR dock beacon. |
| Time (20) | Coverage speed, no restarts | Time-aware return. Stuck recovery. Low-drop TB6612FNG drive. |
| Battery (15) | Energy per run | ECO suction saved 11–20 % in simulation. TB6612 wastes less than the L298N. |
| Container (10) | Easy, clean bin removal | 557 mL bin, magnetic quick-release hatch, anti-spill standpipe |
| Aesthetics (5) | Finished body | Parametric printed shell instead of open MDF |
| Cost (5) | BOM | Reuse every owned part that still fits; buy ₹9,999 of parts |

## 2. Suction: keep the Bergmann BAV-60

| Candidate | Static pressure | Verdict |
|---|---|---|
| **Bergmann MGA Tornado BAV-60** (owned, 12 V, 60 W; MRP ₹912 for the whole car vacuum) | ≈ **6.5 kPa** (retail spec) [1][2] | **Keep.** Run it with PWM at ECO 55 % / BOOST 100 %. |
| 7530 12 V centrifugal blower | ≈ **35–400 Pa** depending on model [3][4] | **Reject.** At best 16× weaker, at worst 180×. It is a cooling fan; it cannot lift sand-like dust or hair. |
| WPV40 | – | **Reject.** It is a small diaphragm *air pump*, built for pressure at very low flow. A vacuum nozzle needs flow at moderate pressure. |

**Benchmark.** Budget robot vacuums sold in India in the ₹7–15k band quote about **2–3 kPa** with gyro navigation [5][6]. At ECO duty the BAV-60 is still in that range, so the owned motor is good enough for a prototype that has to compete with commercial robots. It costs nothing new, and running it at reduced duty is what saves battery.

**Driving it correctly.** The v1 IRF520 module has a gate threshold of 2–4 V. From a 3.3 V GPIO it only partly turns on, and at the Bergmann's ~5 A it overheats [7][8]. v3 uses an **IRLZ44N** logic-level MOSFET with a 100 Ω gate resistor, a 10 k pull-down and a **1N5822** flyback diode, laid out on the carrier PCB (`hardware/pcb/`).

**Production path (not built).** Atomberg's own products are built on BLDC motors and simulation-led design. Atomberg reports, for example, a 65 % energy cut from Ansys-driven redesign [9][10][11]. A 12 V BLDC suction motor [12] is therefore the right production step. It is listed here so the roadmap is clear; the prototype keeps the owned brushed motor.

## 3. Electronics: what stays and what changes

| Part | Decision | Why |
|---|---|---|
| Raspberry Pi 4 (4 GB) + ESP32-S3 | **Keep the hybrid** (finale pitch, `bot_connection_schema.jpeg`) | The Pi runs ROS 2 and YOLO. The ESP32 runs the 50 Hz PID and a hardware watchdog that stops the motors if Linux stalls. |
| XIAO ESP32-S3 Sense | **Retire** | It has 11 GPIO. The v3 pin map uses 26 (`pins.h`). |
| L298N | **Replace with TB6612FNG** (₹149) [13] | About 0.5 V drop instead of about 2 V, so more wheel torque and less heat from the same pack. It has a STBY pin, which v3 uses as a hardware safety cut on GPIO2. It costs the same and is smaller. |
| IRF520 module | **Replace with IRLZ44N** | It cannot switch 5 A from 3.3 V logic (§2). |
| 3× HC-SR04, VL53L0X, MPU6050, SW-420, encoders | **Keep** | Owned, and modelled in Gazebo. Their 5 V outputs are divided down on the PCB. |
| TCRT5000 ×2 (cliff) [14], TSOP38238 (dock) [15] | **Add** | Cliff safety, and finding the dock for the "return to dock" rule |
| 3S 20 A BMS [16], XL4015 buck [17] | **Add** | Cell protection, and a clean 5 V rail so the Pi does not brown out |
| Breadboard + jumpers | **Replace with the carrier PCB** | Removes loose wires, the most common failure in the v1 demo. Generated from code and tested against `pins.h`. |

The full BOM is in [HARDWARE_SOFTWARE_REQUIREMENTS.md](HARDWARE_SOFTWARE_REQUIREMENTS.md): **₹13,693 total, ₹3,694 reused, ₹9,999 to buy.**

## 4. Mechanical: printed, repairable, recyclable

* **28 parametric parts** (CadQuery). Every one fits a 220 mm bed and passes the automatic FDM review: watertight, flat bottom, overhangs and bridges (`bot_3d_printing/review_report.md`). That is about 1 kg of PETG and about 92 h of printing.
* **The MDF base is reused.** Its holes come from the same model (`dxf/mdf_base_template.dxf`).
* **Serviceability.** Four bumper segments and four lid tiles mean a crack costs one small reprint, not a whole shell. The bin lifts out through a magnetic hatch, with no tools.
* **Material.** Structural parts are PETG for its toughness and heat tolerance next to the motor. Non-structural parts use the PLA the team already owns.

## 5. Software: what is in and what is out

| Layer | Decision | Reason |
|---|---|---|
| Autonomy (`chotu_core` on ROS 2 Humble) | **In** | It is the score: coverage, avoidance and returning to the dock. The same code runs in Gazebo and on the robot. |
| YOLOv8n suck/avoid (from the VLM-Vac paper) [18] | **In** | Cable incidents fell from 38 to 1 over 10 rooms in the v2 digital-twin benchmark (commit `9757b23`), and pick-up by mass rises for every garbage type. |
| **VLM on the robot or in the cloud** | **Out** | It is too slow for 5 FPS control on a Pi 4. It needs internet at the venue. The VLM-Vac approach already distils the VLM's knowledge into YOLOv8n offline, which is what v3 uses. |
| **Agentic / LLM orchestration layer** | **Out** | The task is fixed (one room, 5 minutes, return to dock), so a deterministic FSM is safer, testable and free to run. An agent would add latency, API cost and failure modes that score nothing. |
| **Flutter app** over rosbridge | **In** | Start, dock, no-go zones, live map, schedules and history: the same pattern as Atomberg's own app-connected products [19]. It talks to the robot on the local network, with no cloud required. |
| **Fleet backend** (FastAPI + PostgreSQL) | **In, off the robot** | It keeps history, schedules and zones across robots and re-flashes. The robot never waits on it, and a mission completes with the backend down (`backend/PROTOCOL.md`). |

## 6. Sustainability, quality and scalability

| Theme | What v3 does |
|---|---|
| Reuse | 15 owned part lines (₹3,694) carry over. Retired parts stay as bench spares. |
| Energy | Adaptive suction saved 11–20 % in the v2 digital-twin benchmark (commit `9757b23`). The TB6612 avoids the L298N's ~2 V loss. One 111 Wh pack covers ≥ 26 AtomQuest runs per charge (pitch calculation). |
| Repair | Segmented printed body, tool-free bin, JST-XH connectors on the PCB, plus published STEP and STL files |
| Quality | 3 test suites in CI (Python, C++ firmware logic, Flutter), plus backend tests. The Gazebo run uses the robot's own code. The PCB is checked against the firmware pin map. |
| Scalability | Versioned Docker images. One app and one backend for N robots, with a fleet API and a `robots` table. The parametric CAD rebuilds from one parameter table. |

## References

1. Croma: Bergmann Tornado car vacuum cleaner BAV-60. https://www.croma.com/bergmann-tornado-car-vacuum-cleaner-bav-60-blue-/p/223284
2. Flipkart: Bergmann Tornado BAV-60 car vacuum cleaner. https://flipkart.com/bergmann-tornado-bav-60-car-vacuum-cleaner/p/itm4cd7ca7c790aa
3. Same Sky: CBM-7530BF centrifugal blower. https://www.sameskydevices.com/product/thermal-management/dc-fans/centrifugal-blowers/cbm-7530bf-160-540
4. Zenode: ODB7530 blower specifications. https://zenode.ai/parts/4ubp81h1mb
5. StudioMatrx: Robot vacuum guide India. https://www.studiomatrx.org/guides/robot-vacuum-guide-india
6. Houme India: Best robot vacuum in India 2025. https://houmeindia.com/best-robot-vacuum-in-india-2025/
7. ShillehTek: IRF520 MOSFET driver module manual. https://shillehtek.com/blogs/shillehtek-product-manuals/irf520-mosfet-driver-module-arduino-raspberry-pi-esp32-manual
8. Arduino forum: Confused about logic-level MOSFETs. https://forum.arduino.cc/t/confused-about-logic-level-mosfets/1244674
9. Atomberg: Technology. https://atomberg.com/technology
10. Ansys: Atomberg case study. https://ansys.com/resource-center/case-study/ansys-atomberg
11. Ansys press release: simulation helps Atomberg cut home-appliance energy consumption by 65 %. https://www.ansys.com/news-center/press-releases/1-5-23-ansys-simulation-empowers-atomberg-to-reduce-home-appliance-energy-consumption-by-65-percent
12. Probots: 85 W 12 V high-speed vacuum brushless motor. https://probots.co.in/85w-12v-high-speed-vacuum-brushless-motor.html
13. robu.in: TB6612FNG motor driver module. https://robu.in/product/motor-driver-tb6612fng-module-performance-ultra-small-volume-3-pi-matching-performance-ultra-l298n/
14. robu.in: TCRT5000. https://robu.in/product/tcrt-5000/
15. robu.in: TSOP38238 IR receiver. https://robu.in/product/ir-receiver-diode-tsop38238/
16. robu.in: 3S 20 A 18650 BMS. https://robu.in/product/3-series-20a-18650-lithium-battery-protection-board-11-1v-12v-12-6v/
17. robu.in: XL4015 5 A buck module. https://robu.in/product/xl4015-5a-dc-dc-step-down-adjustable-buck-module/
18. Mirjalili et al., *VLM-Vac: Enhancing Smart Vacuums through VLM Knowledge Distillation and Language-Guided Experience Replay*, arXiv:2409.14096. https://arxiv.org/abs/2409.14096
19. Atomberg Home app (App Store). https://apps.apple.com/app/id1608682336
