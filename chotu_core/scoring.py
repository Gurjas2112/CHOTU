"""AtomQuest 2025 Grand Finale scoring rubric (Round 3 PDF, out of 100).

a. Completion time            20 %
b. Efficiency per garbage type (w/w cleaning ratio)   25 %
c. Autonomous vs manual (+ obstacle avoidance)         20 %
d. Battery life               15 %
e. Aesthetics                  5 %
f. Ease of removing / reattaching the storage container 10 %
g. Cost of the system          5 %

The organisers only published the weights, so the per-criterion curves below
are our transparent assumptions; (e) and (f) are judged by people, so they
are passed in as design self-assessments.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict

WEIGHTS = {"completion_time": 20, "efficiency": 25, "autonomy": 20,
           "battery": 15, "aesthetics": 5, "container": 10, "cost": 5}


@dataclass
class RunResult:
    docked: bool
    completion_time_s: float
    time_budget_s: float
    collected_g: Dict[str, float]
    spawned_g: Dict[str, float]
    autonomous: bool
    collisions: int
    cable_incidents: int
    restarts: int
    runtime_estimate_min: float
    cost_inr: float
    aesthetics_self: float = 0.8     # 0..1
    container_self: float = 0.9      # quick-release modular dustbin, 0..1


@dataclass
class ScoreCard:
    parts: Dict[str, float] = field(default_factory=dict)

    @property
    def total(self) -> float:
        return round(sum(self.parts.values()), 1)

    def as_dict(self) -> Dict:
        d = asdict(self)
        d["total"] = self.total
        return d


def per_type_efficiency(collected: Dict[str, float], spawned: Dict[str, float]) -> Dict[str, float]:
    return {k: (collected.get(k, 0.0) / v if v > 0 else 1.0) for k, v in spawned.items()}


def score(r: RunResult) -> ScoreCard:
    s = ScoreCard()
    # (a) time: full marks when docked well inside the budget, 0 when not docked
    if r.docked:
        frac = min(1.0, r.completion_time_s / r.time_budget_s)
        s.parts["completion_time"] = WEIGHTS["completion_time"] * (1.0 - 0.4 * frac)
    else:
        s.parts["completion_time"] = 0.0
    # (b) mean w/w efficiency across garbage types
    eff = per_type_efficiency(r.collected_g, r.spawned_g)
    s.parts["efficiency"] = WEIGHTS["efficiency"] * (sum(eff.values()) / max(1, len(eff)))
    # (c) autonomy x obstacle-avoidance effectiveness
    avoid = max(0.0, 1.0 - 0.08 * r.collisions - 0.15 * r.cable_incidents - 0.1 * r.restarts)
    s.parts["autonomy"] = WEIGHTS["autonomy"] * (1.0 if r.autonomous else 0.5) * avoid
    # (d) battery: 60 min of runtime or more = full marks
    s.parts["battery"] = WEIGHTS["battery"] * min(1.0, r.runtime_estimate_min / 60.0)
    s.parts["aesthetics"] = WEIGHTS["aesthetics"] * r.aesthetics_self
    s.parts["container"] = WEIGHTS["container"] * r.container_self
    # (g) cost: <= 5k INR full marks, >= 15k INR zero
    s.parts["cost"] = WEIGHTS["cost"] * max(0.0, min(1.0, (15000 - r.cost_inr) / 10000))
    s.parts = {k: round(v, 2) for k, v in s.parts.items()}
    return s
