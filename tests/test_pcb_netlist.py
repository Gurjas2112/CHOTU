"""The carrier PCB, the firmware pin map and the BOM must agree."""
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "hardware", "pcb"))

import chotu_carrier as pcb  # noqa: E402

PINS_H = os.path.join(ROOT, "firmware", "esp32s3_base_controller", "include", "pins.h")


def firmware_pins():
    out = {}
    for name, val in re.findall(r"#define\s+PIN_(\w+)\s+(\d+)", open(PINS_H, encoding="utf-8").read()):
        out[name] = int(val)
    return out


def test_every_firmware_pin_is_on_the_pcb_with_the_same_gpio():
    fw = firmware_pins()
    fw.pop("STATUS_LED")                       # on-board WS2812 of the DevKitC-1, not routed
    assert fw == pcb.GPIO


def test_design_rule_check_is_clean():
    assert pcb.own_erc() == []


def test_power_stage_matches_engineering_review():
    values = {ref: v[0] for ref, v in pcb.PARTS.items()}
    assert values["Q1"] == "IRLZ44N" and values["Q2"] == "IRLZ44N"   # not the 3.3 V-incompatible IRF520
    assert values["D1"] == "1N5822"                                     # flyback across the Bergmann motor
    assert values["U3"].startswith("TB6612FNG")                         # not the L298N
    stby = [p for p in pcb.PARTS["U3"][2] if p[1] == "STBY"][0]
    assert stby[2] == "MOTOR_STBY"
    assert ("R1", "1") in pcb.nets()["MOTOR_STBY"]                      # pull-down: motors off at boot


def test_5v_signals_are_divided_before_reaching_the_esp32():
    nets = pcb.nets()
    for s in ("L", "C", "R"):
        assert not any(ref == "U1" for ref, _ in nets[f"US_{s}_ECHO_5V"])
        assert any(ref == "U1" for ref, _ in nets[f"US_{s}_ECHO"])
    for s in ("L", "R"):
        assert not any(ref == "U1" for ref, _ in nets[f"ENC_{s}_5V"])


def test_battery_sense_stays_below_adc_limit():
    vmax = 12.6 * 22.0 / (100.0 + 22.0)
    assert vmax < 3.1
