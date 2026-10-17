#!/usr/bin/env python3
"""CHOTU carrier PCB - single source of truth for the base-controller wiring.

Replaces the breadboard + jumper wiring of `essential_docs/Bot_circuit_diagram.jpg`
and `bot_connection_schema.jpeg` with one 2-layer board (90 x 65 mm) that the
ESP32-S3-DevKitC-1 plugs into. Pin assignment == firmware/.../include/pins.h
(checked by tests/test_pcb_netlist.py).

    python hardware/pcb/chotu_carrier.py        # -> chotu_carrier.net (KiCad) + ERC report

The data tables below (PARTS, GPIO) are also used by render_schematic.py, so the
drawings, the netlist and the firmware cannot drift apart.
"""
from __future__ import annotations

import os
import sys
from typing import Dict, List, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- DevKitC-1 headers
# ESP32-S3-DevKitC-1 v1.0/v1.1 header order (verify against your board's silkscreen).
J1 = ["3V3", "3V3", "RST", "GPIO4", "GPIO5", "GPIO6", "GPIO7", "GPIO15", "GPIO16", "GPIO17", "GPIO18",
      "GPIO8", "GPIO3", "GPIO46", "GPIO9", "GPIO10", "GPIO11", "GPIO12", "GPIO13", "GPIO14", "5V0", "GND"]
J3 = ["GND", "TX", "RX", "GPIO1", "GPIO2", "GPIO42", "GPIO41", "GPIO40", "GPIO39", "GPIO38", "GPIO37",
      "GPIO36", "GPIO35", "GPIO0", "GPIO45", "GPIO48", "GPIO47", "GPIO21", "GPIO20", "GPIO19", "GND", "GND"]

# ---------------------------------------------------------------- firmware signal -> GPIO
# Net names are the pins.h define names without the PIN_ prefix.
GPIO: Dict[str, int] = {
    "MOTOR_L_EN": 4, "MOTOR_L_IN1": 5, "MOTOR_L_IN2": 6,
    "MOTOR_R_EN": 7, "MOTOR_R_IN3": 15, "MOTOR_R_IN4": 16, "MOTOR_STBY": 2,
    "ENC_L": 17, "ENC_R": 18,
    "I2C_SDA": 8, "I2C_SCL": 9, "TOF_XSHUT": 47,
    "US_L_TRIG": 10, "US_L_ECHO": 13, "US_C_TRIG": 11, "US_C_ECHO": 14, "US_R_TRIG": 12, "US_R_ECHO": 21,
    "SW420": 38, "CLIFF_L": 39, "CLIFF_R": 40, "DOCK_IR": 3,
    "VACUUM_PWM": 41, "BRUSH_PWM": 42, "BATT_SENSE": 1,
}

# ---------------------------------------------------------------- parts
# ref: (value, footprint, [(pin_number, pin_name, net), ...])
Pins = List[Tuple[int, str, str]]


def conn(n: int, nets: List[str], names: List[str] = None) -> Pins:
    names = names or [str(i + 1) for i in range(n)]
    return [(i + 1, names[i], nets[i]) for i in range(n)]


def two(a: str, b: str) -> Pins:
    return [(1, "1", a), (2, "2", b)]


PARTS: Dict[str, Tuple[str, str, Pins]] = {}

# --- power entry: XT60 -> 10 A fuse -> rocker switch -> VBAT bus
PARTS["J1"] = ("XT60 battery 3S 11.1V", "Connector_AMASS:AMASS_XT60-M_1x02_P7.20mm_Vertical",
               conn(2, ["VBAT_RAW", "GND"], ["BAT+", "BAT-"]))
PARTS["F1"] = ("Fuse 10A ATO", "Fuse:Fuseholder_Blade_ATO_Littelfuse_FLR_178.6165", two("VBAT_RAW", "VBAT_SW"))
PARTS["J2"] = ("Rocker switch (panel)", "Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical", two("VBAT_SW", "VBAT"))
PARTS["C1"] = ("470uF 25V", "Capacitor_THT:CP_Radial_D10.0mm_P5.00mm", two("VBAT", "GND"))
PARTS["U2"] = ("XL4015 5V/5A buck module", "CHOTU:XL4015_module_pads",
               conn(4, ["VBAT", "GND", "+5V", "GND"], ["IN+", "IN-", "OUT+", "OUT-"]))
PARTS["C2"] = ("1000uF 10V", "Capacitor_THT:CP_Radial_D10.0mm_P5.00mm", two("+5V", "GND"))
PARTS["J3"] = ("Raspberry Pi 4 5V feed (GPIO pins 2/6)", "Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical",
               conn(2, ["+5V", "GND"], ["5V", "GND"]))

# --- MCU
mcu: Pins = []
for i, name in enumerate(J1):
    mcu.append((i + 1, name, ""))
for i, name in enumerate(J3):
    mcu.append((23 + i, name, ""))
by_gpio = {f"GPIO{g}": net for net, g in GPIO.items()}
mcu = [(n, nm, by_gpio.get(nm, "+3V3" if nm == "3V3" else "+5V" if nm == "5V0" else "GND" if nm == "GND" else ""))
       for n, nm, _ in mcu]
PARTS["U1"] = ("ESP32-S3-DevKitC-1 (N8R8)", "CHOTU:ESP32-S3-DevKitC-1_2x22_socket", mcu)

# --- TB6612FNG module (drive)
PARTS["U3"] = ("TB6612FNG module", "CHOTU:TB6612FNG_module_2x8",
               conn(16, ["VBAT", "+3V3", "GND", "MOT_L_A", "MOT_L_B", "MOT_R_B", "MOT_R_A", "GND",
                         "MOTOR_L_EN", "MOTOR_L_IN2", "MOTOR_L_IN1", "MOTOR_STBY", "MOTOR_R_IN3", "MOTOR_R_IN4",
                         "MOTOR_R_EN", "GND"],
                    ["VM", "VCC", "GND", "AO1", "AO2", "BO2", "BO1", "GND", "PWMA", "AIN2", "AIN1", "STBY",
                     "BIN1", "BIN2", "PWMB", "GND"]))
PARTS["R1"] = ("10k", "Resistor_SMD:R_0805_2012Metric", two("MOTOR_STBY", "GND"))     # motors off at boot
PARTS["J4"] = ("Left BO motor", "Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical", two("MOT_L_A", "MOT_L_B"))
PARTS["J5"] = ("Right BO motor", "Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical", two("MOT_R_A", "MOT_R_B"))

# --- wheel encoders (LM393, 5 V output -> 1k/2k divider -> 3.3 V)
for side, ref, rr in (("L", "J6", 2), ("R", "J7", 4)):
    PARTS[ref] = (f"Encoder {side} (LM393)", "Connector_JST:JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical",
                  conn(3, ["+5V", "GND", f"ENC_{side}_5V"], ["VCC", "GND", "OUT"]))
    PARTS[f"R{rr}"] = ("1k", "Resistor_SMD:R_0805_2012Metric", two(f"ENC_{side}_5V", f"ENC_{side}"))
    PARTS[f"R{rr + 1}"] = ("2k", "Resistor_SMD:R_0805_2012Metric", two(f"ENC_{side}", "GND"))

# --- 3 x HC-SR04 (5 V, echo divided 1k/2k)
rn = 6
for k, s in enumerate(("L", "C", "R")):
    PARTS[f"J{8 + k}"] = (f"HC-SR04 {s}", "Connector_JST:JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical",
                          conn(4, ["+5V", f"US_{s}_TRIG", f"US_{s}_ECHO_5V", "GND"], ["VCC", "TRIG", "ECHO", "GND"]))
    PARTS[f"R{rn}"] = ("1k", "Resistor_SMD:R_0805_2012Metric", two(f"US_{s}_ECHO_5V", f"US_{s}_ECHO"))
    PARTS[f"R{rn + 1}"] = ("2k", "Resistor_SMD:R_0805_2012Metric", two(f"US_{s}_ECHO", "GND"))
    rn += 2

# --- I2C: VL53L0X (GY-53) + MPU6050 (GY-521), 4.7k pull-ups
PARTS["J11"] = ("VL53L0X ToF", "Connector_JST:JST_XH_B5B-XH-A_1x05_P2.50mm_Vertical",
                conn(5, ["+3V3", "GND", "I2C_SCL", "I2C_SDA", "TOF_XSHUT"], ["VIN", "GND", "SCL", "SDA", "XSHUT"]))
PARTS["J12"] = ("MPU6050 IMU", "Connector_JST:JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical",
                conn(4, ["+3V3", "GND", "I2C_SCL", "I2C_SDA"], ["VCC", "GND", "SCL", "SDA"]))
PARTS["R12"] = ("4.7k", "Resistor_SMD:R_0805_2012Metric", two("+3V3", "I2C_SCL"))
PARTS["R13"] = ("4.7k", "Resistor_SMD:R_0805_2012Metric", two("+3V3", "I2C_SDA"))

# --- safety + dock inputs (3.3 V modules)
PARTS["J13"] = ("SW-420 bump", "Connector_JST:JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical",
                conn(3, ["+3V3", "GND", "SW420"], ["VCC", "GND", "DO"]))
PARTS["J14"] = ("TCRT5000 cliff L", "Connector_JST:JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical",
                conn(3, ["+3V3", "GND", "CLIFF_L"], ["VCC", "GND", "DO"]))
PARTS["J15"] = ("TCRT5000 cliff R", "Connector_JST:JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical",
                conn(3, ["+3V3", "GND", "CLIFF_R"], ["VCC", "GND", "DO"]))
PARTS["J16"] = ("TSOP38238 dock IR", "Connector_JST:JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical",
                conn(3, ["DOCK_IR", "GND", "TSOP_VS"], ["OUT", "GND", "VS"]))
PARTS["R14"] = ("100R", "Resistor_SMD:R_0805_2012Metric", two("+3V3", "TSOP_VS"))      # Vishay RC filter
PARTS["C3"] = ("4.7uF", "Capacitor_SMD:C_0805_2012Metric", two("TSOP_VS", "GND"))

# --- cleaning actuators: IRLZ44N low-side switches + 1N5822 flyback
for name, q, rg, rp, d, j in (("VACUUM", "Q1", "R15", "R16", "D1", "J17"), ("BRUSH", "Q2", "R17", "R18", "D2", "J18")):
    PARTS[q] = ("IRLZ44N", "Package_TO_SOT_THT:TO-220-3_Vertical",
                [(1, "G", f"{name}_G"), (2, "D", f"{name}_D"), (3, "S", "GND")])
    PARTS[rg] = ("100R", "Resistor_SMD:R_0805_2012Metric", two(f"{name}_PWM", f"{name}_G"))
    PARTS[rp] = ("10k", "Resistor_SMD:R_0805_2012Metric", two(f"{name}_G", "GND"))
    PARTS[d] = ("1N5822", "Diode_THT:D_DO-201AD_P15.24mm_Horizontal", [(1, "K", "VBAT"), (2, "A", f"{name}_D")])
    PARTS[j] = (("Bergmann BAV-60 vacuum 12V/60W" if name == "VACUUM" else "Side-brush motor 12V"),
                "Connector_AMASS:AMASS_XT30PW-M_1x02_P2.50mm_Horizontal" if name == "VACUUM"
                else "Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical",
                [(1, "+", "VBAT"), (2, "-", f"{name}_D")])

# --- battery sense 100k / 22k (12.6 V -> 2.27 V) + filter
PARTS["R19"] = ("100k", "Resistor_SMD:R_0805_2012Metric", two("VBAT", "BATT_SENSE"))
PARTS["R20"] = ("22k", "Resistor_SMD:R_0805_2012Metric", two("BATT_SENSE", "GND"))
PARTS["C4"] = ("100nF", "Capacitor_SMD:C_0805_2012Metric", two("BATT_SENSE", "GND"))

# --- test points
for i, net in enumerate(("VBAT", "+5V", "+3V3", "GND")):
    PARTS[f"TP{i + 1}"] = (f"TP {net}", "TestPoint:TestPoint_Pad_D2.0mm", [(1, "1", net)])

POWER_NETS = {"VBAT_RAW", "VBAT_SW", "VBAT", "+5V", "+3V3", "GND", "MOT_L_A", "MOT_L_B", "MOT_R_A", "MOT_R_B",
              "VACUUM_D", "BRUSH_D"}
TRACE_MM = {n: (2.0 if n in POWER_NETS else 0.3) for n in {p[2] for v in PARTS.values() for p in v[2] if p[2]}}


def nets() -> Dict[str, List[Tuple[str, str]]]:
    out: Dict[str, List[Tuple[str, str]]] = {}
    for ref, (_, _, pins) in PARTS.items():
        for num, name, net in pins:
            if net:
                out.setdefault(net, []).append((ref, name))
    return out


def own_erc() -> List[str]:
    """Design-rule checks SKiDL's generic ERC cannot know about."""
    errs = []
    for net, members in nets().items():
        if len(members) < 2:
            errs.append(f"net {net} has a single connection {members}")
    for net, g in GPIO.items():
        if not any(ref == "U1" and nm == f"GPIO{g}" for ref, nm in nets().get(net, [])):
            errs.append(f"{net} not wired to GPIO{g}")
    strapping = {0, 45, 46}
    for net, g in GPIO.items():
        if g in strapping:
            errs.append(f"{net} on strapping pin GPIO{g}")
        if 26 <= g <= 37 or g in (19, 20, 43, 44):
            errs.append(f"{net} on reserved GPIO{g} (flash/PSRAM/USB/UART0)")
    return errs


def build_netlist(path: str) -> None:
    import builtins

    from skidl import ERC, KICAD8, SKIDL, TEMPLATE, Net, Part, Pin, generate_netlist, set_default_tool
    set_default_tool(KICAD8)
    netobj: Dict[str, Net] = {}
    for ref, (value, fp, pins) in PARTS.items():
        tmpl = Part(tool=SKIDL, name=value.split(" ")[0], ref_prefix="".join(c for c in ref if c.isalpha()),
                    dest=TEMPLATE, footprint=fp,
                    pins=[Pin(num=n, name=nm, func=Pin.types.PASSIVE) for n, nm, _ in pins])
        part = tmpl(value=value, tag=ref)
        part.ref = ref
        for n, nm, net in pins:
            if net:
                if net not in netobj:
                    netobj[net] = Net(net)
                netobj[net] += part[n]
            else:
                part[n] += builtins.NC
    ERC()
    generate_netlist(file_=path)


def main() -> int:
    errs = own_erc()
    report = os.path.join(HERE, "erc_report.txt")
    with open(report, "w") as f:
        f.write("CHOTU carrier - design-rule check\n")
        f.write(f"parts: {len(PARTS)}  nets: {len(nets())}\n")
        f.write("\n".join(errs) if errs else "0 errors: every net has >= 2 pins, every firmware signal reaches its "
                                             "GPIO, no strapping/flash/USB pins used.\n")
    print(open(report).read())
    build_netlist(os.path.join(HERE, "chotu_carrier.net"))
    print("netlist ->", os.path.join(HERE, "chotu_carrier.net"))
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
