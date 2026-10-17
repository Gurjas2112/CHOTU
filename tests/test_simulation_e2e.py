"""End-to-end: the real CleaningMission brain drives the simulated robot.

Each case is a full 5-minute AtomQuest run in a randomised room.
"""
import pytest

from chotu_sim import Simulation
from chotu_sim.world import generate_room


@pytest.mark.parametrize("seed", [2025, 4, 9])
def test_full_mission_returns_to_dock_in_time(seed):
    r = Simulation(seed).run()
    assert r.docked, "robot must return to the docking station"
    assert r.elapsed_s <= 300.0
    assert r.final_dock_error_m < 0.06
    assert r.coverage >= 0.65
    assert r.collisions <= 5
    assert r.cable_incidents == 0
    assert r.score["total"] >= 70


def test_ai_vision_prevents_cable_incidents():
    on = sum(Simulation(s, vision=True).run().cable_incidents for s in (0, 1, 2))
    off = sum(Simulation(s, vision=False).run().cable_incidents for s in (0, 1, 2))
    assert on < off


def test_adaptive_suction_saves_energy():
    assert Simulation(5).run().eco_energy_saving_pct > 5.0


def test_room_generator_is_deterministic_and_randomised():
    a, b, c = generate_room(1), generate_room(1), generate_room(2)
    assert [(o.cx, o.cy) for o in a.obstacles] == [(o.cx, o.cy) for o in b.obstacles]
    assert [(o.cx, o.cy) for o in a.obstacles] != [(o.cx, o.cy) for o in c.obstacles]
    assert {g.kind for g in a.garbage} == {"dust", "hair", "paper", "wrapper", "wire_strand"}
