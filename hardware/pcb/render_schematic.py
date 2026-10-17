#!/usr/bin/env python3
"""Render the CHOTU carrier-board connection schematics (PNG + SVG) with schemdraw.

Every pin/net label comes from chotu_carrier.PARTS / GPIO - the same tables that
generate the KiCad netlist - so the drawings cannot drift from the PCB.

    python hardware/pcb/render_schematic.py      # -> hardware/pcb/schematic/*.png|svg
"""
from __future__ import annotations

import os

import matplotlib

matplotlib.use("Agg")
import schemdraw  # noqa: E402
import schemdraw.elements as elm  # noqa: E402

import chotu_carrier as pcb  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "schematic")
INK = "#14202e"
POWER = "#c2410c"      # power / ground nets
SIG = "#0e7490"        # 3.3 V logic signals
HV = "#a21caf"         # 5 V signals before the divider
GPIO_OF = {f"GPIO{g}": n for n, g in pcb.GPIO.items()}


def colour(net: str) -> str:
    if net in pcb.POWER_NETS:
        return POWER
    if net.endswith("_5V"):
        return HV
    return SIG


def new(title: str) -> schemdraw.Drawing:
    d = schemdraw.Drawing(show=False)
    d.config(fontsize=10, color=INK, lw=1.2, bgcolor="white")
    d += elm.Label().at((0, 2.8)).label(title, fontsize=15, color=SIG, halign="left")
    return d


def save(d: schemdraw.Drawing, name: str) -> None:
    os.makedirs(OUT, exist_ok=True)
    d.save(os.path.join(OUT, f"{name}.svg"))
    d.save(os.path.join(OUT, f"{name}.png"), dpi=130)
    print("saved", name)


def ic_with_nets(d, ref: str, x: float, y: float, left_names, right_names, w=3.6, label=None, stub=1.3):
    """Draw part `ref` as an IC; pins on the left/right in the given order, each with its net label."""
    value, _, pins = pcb.PARTS[ref]
    by_name = {}
    for num, nm, net in pins:
        by_name.setdefault(nm, []).append((num, net))
    ic_pins, links = [], []
    for side, names in (("left", left_names), ("right", right_names)):
        for nm in names:
            num, net = by_name[nm].pop(0)
            a = f"p{num}"
            ic_pins.append(elm.IcPin(name=nm, pin=str(num), side=side, anchorname=a))
            links.append((a, side, net))
    ic = d.add(elm.Ic(pins=ic_pins, pinspacing=0.62, edgepadH=0.5, w=w).at((x, y))
               .label(f"{ref}  {label or value}", loc="top", fontsize=11, color=INK))
    for a, side, net in links:
        if not net:
            d.add(elm.Line().at(getattr(ic, a)).length(0.5).left() if side == "left"
                  else elm.Line().at(getattr(ic, a)).length(0.5).right())
            d.add(elm.Label().at(getattr(ic, a)).label("NC", loc="left" if side == "left" else "right",
                                                       fontsize=8, color="#94a3b8"))
            continue
        ln = elm.Line(color=colour(net)).at(getattr(ic, a))
        ln = ln.left(stub) if side == "left" else ln.right(stub)
        d.add(ln.label(net, loc="left" if side == "left" else "right", color=colour(net), fontsize=9,
                       halign="right" if side == "left" else "left"))
    return ic


# ------------------------------------------------------------------ sheets
def sheet_mcu():
    d = new("Sheet 1 - ESP32-S3-DevKitC-1 pin map (matches firmware include/pins.h)")
    ic_with_nets(d, "U1", 0, -14.5, pcb.J1, pcb.J3, w=5.2, label="ESP32-S3-DevKitC-1 socket (J1 left, J3 right)", stub=1.6)
    save(d, "01_mcu_pinmap")


def sheet_power():
    d = new("Sheet 2 - Power entry, 5 V rail, battery sense")
    # main power path (y = 0)
    d += elm.Battery().up().at((0, -3)).label("J1 XT60\n3S Li-ion 11.1 V\n(12.6 V max)", loc="left")
    d += elm.Line().up(1.0)
    d += elm.Fuse().right().label("F1 10 A")
    d += elm.Switch().right().label("J2 rocker")
    d += elm.Line().right(1.0)
    d += (vbat := elm.Dot().label("VBAT", loc="top", color=POWER))
    d += elm.Line().right(3.0)
    d += (tap := elm.Dot())
    d += elm.Line().right(4.0)
    d += elm.Label().label("-> U3 TB6612 VM, J17 vacuum +, J18 brush +", loc="right", color=POWER, fontsize=9,
                           halign="left")
    d += elm.Line().at((0, -3)).down(0.6)
    d += elm.Ground()
    d += elm.Capacitor(polar=True).at(vbat.center).down().label("C1 470 µF\n25 V", loc="bottom")
    d += elm.Ground()
    # buck converter: drawn as a box with explicit wires (no crossings)
    from schemdraw import flow
    d += (buck := flow.Box(w=3.0, h=2.0).at((tap.center[0] - 1.5, -2.0)).anchor("NW")
          .label("U2 XL4015\n5 V / 5 A", fontsize=10))
    d += elm.Line().at(tap.center).to(buck.N)
    d += elm.Line().at(buck.S).down(0.6)
    d += elm.Ground()
    d += elm.Line().at(buck.E).right(1.8)
    d += (v5 := elm.Dot().label("+5V", loc="top", color=POWER))
    d += elm.Capacitor(polar=True).at(v5.center).down().label("C2 1000 µF", loc="bottom")
    d += elm.Ground()
    d += elm.Line().at(v5.center).right(2.2)
    d += elm.Label().label("-> J3 Raspberry Pi 4 (pins 2/6), U1 5V0,\n   HC-SR04 x3, encoders", loc="right",
                           color=POWER, fontsize=9, halign="left")
    d += elm.Label().at((tap.center[0] + 4.6, -6.0)).label(
        "+3V3 = DevKitC-1 on-board LDO (3V3 pins)\n-> TB6612 VCC, ToF, IMU, cliff, bump, TSOP", fontsize=9,
        color=POWER, halign="left")
    # battery sense branch (separate, taken from a VBAT net label - no crossing wires)
    y = -8.5
    d += elm.Label().at((0, y + 0.45)).label("VBAT", color=POWER, fontsize=10, halign="left")
    d += elm.Line(color=POWER).at((0, y)).right(0.6)
    d += elm.Resistor().right().label("R19 100k", loc="bottom")
    d += (bs := elm.Dot().label("BATT_SENSE -> GPIO1", loc="top", color=SIG))
    d += elm.Resistor().down().label("R20 22k", loc="bottom")
    d += elm.Ground()
    d += elm.Line().at(bs.center).right(2.0)
    d += elm.Capacitor().down().label("C4 100 nF", loc="bottom")
    d += elm.Ground()
    d += elm.Label().at((7.5, y - 1.2)).label("12.6 V x 22k / 122k = 2.27 V max at the ADC (< 3.1 V)",
                                              fontsize=9, color=SIG, halign="left")
    save(d, "02_power")


def sheet_motor():
    d = new("Sheet 3 - Drive: TB6612FNG + BO motors + encoders")
    ic_with_nets(d, "U3", 0, -9, ["PWMA", "AIN2", "AIN1", "STBY", "BIN1", "BIN2", "PWMB", "VCC", "GND"],
                 ["VM", "AO1", "AO2", "BO2", "BO1", "GND", "GND"], w=3.6, stub=1.8)
    d += elm.Label().at((-6.5, -10.6)).label("MOTOR_STBY", color=SIG, fontsize=9)
    d += elm.Resistor().at((-6.5, -11.0)).down().label("R1 10k  STBY pull-down\n(motors off at boot)", loc="bottom")
    d += elm.Ground()
    for x, side, ref in ((9.5, "L", "J4 left"), (13.5, "R", "J5 right")):
        d += elm.Label().at((x, -3.6)).label(f"MOT_{side}_A", color=POWER, fontsize=9)
        d += elm.Motor().at((x, -4.0)).down().label(f"{ref}\nBO motor", loc="bottom")
        d += elm.Label().label(f"MOT_{side}_B", color=POWER, fontsize=9, loc="bottom")
    # encoder divider
    d += elm.Label().at((0, -14.6)).label("Encoder (x2): LM393 OUT 5 V -> 1k / 2k divider -> 3.3 V GPIO", fontsize=10,
                                         color=HV, halign="left")
    d += elm.Line(color=HV).at((0.5, -16)).right(1.0).label("ENC_L_5V", loc="left", color=HV)
    d += elm.Resistor().right().label("R2 1k")
    d += (e := elm.Dot().label("ENC_L -> GPIO17", loc="top", color=SIG))
    d += elm.Resistor().down().label("R3 2k", loc="bottom")
    d += elm.Ground()
    d += elm.Label().at((7.5, -16)).label("ENC_R: R4 / R5 -> GPIO18 (same)", fontsize=9, color=SIG, halign="left")
    save(d, "03_motor_drive")


def mosfet_stage(d, x, y, name, q, rg, rp, dio, j, gpio, load):
    NL = chr(10)
    d += elm.Label().at((x, y + 0.5)).label(f"{name}_PWM <- GPIO{gpio}", color=SIG, fontsize=10, halign="left")
    d += elm.Line(color=SIG).at((x, y)).right(0.6)
    d += elm.Resistor().right().label(f"{rg} 100R")
    d += (g := elm.Dot())
    d += (fet := elm.NFet(anchor="gate").right().reverse().label(q + NL + "IRLZ44N", loc="right"))
    d += elm.Resistor().at(g.center).down().label(f"{rp} 10k", loc="bottom")
    d += elm.Ground()
    d += elm.Line().at(fet.source).down(0.8)
    d += elm.Ground()
    d += elm.Line().at(fet.drain).up(0.8)
    d += (drain := elm.Dot().label(f"{name}_D", loc="right", color=POWER, fontsize=8))
    d += elm.Motor().up()
    d += (vb := elm.Dot().label("VBAT", loc="top", color=POWER))
    d += elm.Label().at((drain.center[0] + 1.0, drain.center[1] + 1.6)).label(j + NL + load, fontsize=9,
                                                                              halign="left")
    # flyback: anode on the drain, cathode (bar) on VBAT
    d += elm.Line().at(drain.center).left(1.8)
    d += elm.Diode().up().label(f"{dio} 1N5822", loc="left")
    d += elm.Line().to(vb.center)


def sheet_actuators():
    NL = chr(10)
    d = new("Sheet 4 - Cleaning actuators: logic-level low-side switches (replaces the v1 IRF520)")
    mosfet_stage(d, 0, -6.5, "VACUUM", "Q1", "R15", "R16", "D1", "J17 XT30", 41,
                 "Bergmann BAV-60" + NL + "12 V / 60 W / ~5 A")
    mosfet_stage(d, 12, -6.5, "BRUSH", "Q2", "R17", "R18", "D2", "J18", 42, "Side-brush motor" + NL + "12 V")
    d += elm.Label().at((0, -12.2)).label("IRLZ44N: logic-level gate, 22 mOhm Rds(on) at Vgs 5 V - fully on from the "
                                          "3.3 V GPIO at these currents (the IRF520 is not).", fontsize=9,
                                          color=INK, halign="left")
    d += elm.Label().at((0, -12.8)).label("20 kHz PWM (no audible whine); 1N5822 Schottky clamps the motor's "
                                          "inductive kick; 10k pull-down keeps the motor off while the ESP32 boots.",
                                          fontsize=9, color=INK, halign="left")
    save(d, "04_vacuum_brush_drivers")


def sheet_sensors():
    d = new("Sheet 5 - Sensors: ultrasonic, I2C, cliff, bump, dock IR")
    y = -1.0
    for k, s in enumerate(("L", "C", "R")):
        x = k * 7.0
        trig, echo = pcb.GPIO[f"US_{s}_TRIG"], pcb.GPIO[f"US_{s}_ECHO"]
        d += elm.Label().at((x, y)).label(f"J{8 + k} HC-SR04 {s} (5 V)", fontsize=10, color=INK, halign="left")
        d += elm.Label().at((x, y - 0.6)).label(f"TRIG <- GPIO{trig}", fontsize=9, color=SIG, halign="left")
        d += elm.Line(color=HV).at((x, y - 1.6)).right(0.4).label(f"US_{s}_ECHO_5V", loc="left", color=HV, fontsize=8)
        d += elm.Resistor().right(2.2).label("1k")
        d += (e := elm.Dot().label(f"GPIO{echo}", loc="top", color=SIG))
        d += elm.Resistor().down(2.0).label("2k", loc="bottom")
        d += elm.Ground()
    # I2C
    y = -7.0
    d += elm.Label().at((0, y)).label("I2C @ 400 kHz: J11 VL53L0X (0x29, XSHUT=GPIO47) + J12 MPU6050 (0x68)", fontsize=10,
                                      color=INK, halign="left")
    for i, (net, g, r) in enumerate((("I2C_SCL", 9, "R12"), ("I2C_SDA", 8, "R13"))):
        x = 1 + i * 5
        d += elm.Label().at((x, y - 0.7)).label("+3V3", color=POWER, fontsize=9)
        d += elm.Resistor().at((x, y - 1.0)).down().label(f"{r} 4.7k", loc="bottom")
        d += elm.Dot().label(f"{net} -> GPIO{g}", loc="right", color=SIG)
    # digital inputs
    y = -11.5
    d += elm.Label().at((0, y)).label("3.3 V digital inputs (modules powered from +3V3, no level shifting needed)",
                                      fontsize=10, color=INK, halign="left")
    rows = [("J13 SW-420 bump", "SW420"), ("J14 TCRT5000 cliff L", "CLIFF_L"), ("J15 TCRT5000 cliff R", "CLIFF_R"),
            ("J16 TSOP38238 dock IR", "DOCK_IR")]
    for i, (lab, net) in enumerate(rows):
        d += elm.Label().at((0.4, y - 0.8 - i * 0.7)).label(f"{lab:26s} DO -> {net} -> GPIO{pcb.GPIO[net]}",
                                                           fontsize=9, color=SIG, halign="left")
    d += elm.Label().at((0.4, y - 3.9)).label("TSOP VS filter: R14 100R from +3V3 + C3 4.7 µF to GND (Vishay datasheet)",
                                              fontsize=9, color=POWER, halign="left")
    save(d, "05_sensors")


def sheet_overview():
    d = new("Sheet 0 - CHOTU carrier board overview (90 x 65 mm, 2 layers)")
    from schemdraw import flow
    d.config(fontsize=10)
    blocks = {
        "bat": ((0, -1.5), "3S Li-ion 11.1 V\nBMS + XT60\nF1 10 A, rocker"),
        "buck": ((5.5, -1.5), "XL4015\n5 V / 5 A"),
        "pi": ((11, -1.5), "Raspberry Pi 4\nROS 2 + rosbridge\n(USB link to ESP32)"),
        "esp": ((5.5, -5.5), "ESP32-S3-DevKitC-1\n50 Hz real-time\nPID, safety, telemetry"),
        "tb": ((0, -9.5), "TB6612FNG\n2 x BO motor\n+ encoders"),
        "fet": ((5.5, -9.5), "2 x IRLZ44N\nBergmann vacuum\nside brush"),
        "sens": ((11, -9.5), "3 x HC-SR04, VL53L0X,\nMPU6050, 2 x TCRT5000,\nSW-420, TSOP38238"),
    }
    el = {}
    for k, (pos, text) in blocks.items():
        el[k] = d.add(flow.Box(w=4.4, h=2.0).at(pos).anchor("N").label(text, fontsize=9,
                      color=SIG if k == "esp" else INK))
    d += elm.Arrow(color=POWER).at(el["bat"].E).to(el["buck"].W).label("VBAT", color=POWER, fontsize=8)
    d += elm.Arrow(color=POWER).at(el["buck"].E).to(el["pi"].W).label("+5V", color=POWER, fontsize=8)
    d += elm.Arrow(color=POWER).at(el["buck"].S).to(el["esp"].N).label("+5V", color=POWER, fontsize=8, loc="right")
    d += elm.Arrow(color=SIG).at(el["pi"].S).to(el["esp"].E).label("UART 115200\nCOBS+CRC16", color=SIG, fontsize=8)
    d += elm.Arrow(color=SIG).at(el["esp"].SW).to(el["tb"].N).label("PWM/DIR/STBY", color=SIG, fontsize=8)
    d += elm.Arrow(color=SIG).at(el["esp"].S).to(el["fet"].N).label("20 kHz PWM", color=SIG, fontsize=8, loc="right")
    d += elm.Arrow(color=SIG).at(el["sens"].N).to(el["esp"].SE).label("I2C / echo / DO", color=SIG, fontsize=8)
    d += elm.Arrow(color=POWER).at(el["bat"].S).to(el["tb"].N).label("VM", color=POWER, fontsize=8, loc="left")
    save(d, "00_overview")


if __name__ == "__main__":
    sheet_overview()
    sheet_mcu()
    sheet_power()
    sheet_motor()
    sheet_actuators()
    sheet_sensors()
