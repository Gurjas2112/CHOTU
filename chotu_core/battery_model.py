"""Battery / energy model (finale pitch: 11.1 V, 10 Ah, 111 Wh)."""
from __future__ import annotations

from dataclasses import dataclass

from .config import PowerConfig


def pitch_runtime_estimate(capacity_ah: float = 10.0,
                           currents_a=(2.5, 0.05, 0.02, 2.0, 0.05)) -> float:
    """Reproduce the finale-pitch calculation: Runtime_h = Ah / I_total.

    I_total = I_pi + I_vl53 + I_ultra + I_motors + I_driver = 4.62 A
    -> 10 / 4.62 = 2.16 h (the pitch rounds to 2.17 h / 130 min).
    """
    return capacity_ah / sum(currents_a)


@dataclass
class EnergySample:
    power_w: float
    soc: float


class BatteryModel:
    def __init__(self, cfg: PowerConfig = PowerConfig(), soc: float = 1.0):
        self.cfg = cfg
        self.capacity_wh = cfg.nominal_voltage * cfg.capacity_ah * cfg.usable_fraction
        self.energy_wh = self.capacity_wh * soc
        self.consumed_wh = 0.0
        self.last_power_w = 0.0

    def power(self, v_abs: float, v_max: float, suction: float, brush_on: bool) -> float:
        c = self.cfg
        drive = c.drive_w_at_full * min(1.0, 0.35 + 0.65 * v_abs / max(v_max, 1e-6)) if v_abs > 1e-3 else 0.4
        return (c.pi4_w + c.esp32_w + c.sensors_w + drive
                + c.vacuum_w_at_full * suction ** 1.5   # fan law: P ∝ duty^~1.5
                + (c.brush_w if brush_on else 0.0))

    def step(self, dt: float, v_abs: float, v_max: float, suction: float, brush_on: bool) -> EnergySample:
        p = self.power(v_abs, v_max, suction, brush_on)
        e = p * dt / 3600.0
        self.energy_wh = max(0.0, self.energy_wh - e)
        self.consumed_wh += e
        self.last_power_w = p
        return EnergySample(p, self.soc)

    @property
    def soc(self) -> float:
        return self.energy_wh / self.capacity_wh

    @property
    def voltage(self) -> float:
        # Simple 3S Li-ion OCV curve: 12.6 V full -> 9.9 V empty
        return 9.9 + 2.7 * self.soc

    def runtime_minutes(self, avg_power_w: float) -> float:
        return 60.0 * self.capacity_wh / max(avg_power_w, 1e-3)
