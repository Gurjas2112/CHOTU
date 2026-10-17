import math

import pytest

from chotu_core.battery_model import BatteryModel, pitch_runtime_estimate
from chotu_core.kinematics import Pose2D
from chotu_core.mission_fsm import InvalidTransition, MissionFSM, MissionState as S
from chotu_core.obstacle_avoidance import RangeReading, ReactiveSafety
from chotu_core.perception import CameraModel, Detection, MockDetector, action_for, debris_ahead
from chotu_core.scoring import RunResult, score
from chotu_core.suction_controller import AdaptiveSuction


def rd(deg, d, mx=1.5):
    return RangeReading(math.radians(deg), d, mx)


def test_safety_levels():
    s = ReactiveSafety(0.05, 0.12, 0.17)
    assert s.filter(0.25, 0, [rd(0, 1.0)])[2].level == "clear"
    v, _, st = s.filter(0.25, 0, [rd(0, 0.09)])
    assert st.level == "slow" and 0 < v < 0.25
    assert s.filter(0.25, 0, [rd(0, 0.03)])[0] == 0.0
    assert s.filter(0.25, 0, [rd(0, 1.0)], cliff=True)[2].level == "cliff"
    assert s.filter(-0.1, 0, [rd(0, 0.01)])[0] == -0.1   # reversing is always allowed


def test_parallel_wall_on_side_sensor_does_not_block():
    s = ReactiveSafety(0.05, 0.12, 0.17)
    d = 0.03 / math.sin(math.radians(35))          # wall 3 cm beside the chassis
    assert s.filter(0.25, 0, [rd(35, d)])[2].level in ("clear", "slow")


def test_fsm_happy_path_and_invalid():
    f = MissionFSM()
    for st in (S.UNDOCK, S.SCAN, S.COVER, S.STUCK_RECOVERY, S.COVER, S.SPOT_CLEAN,
               S.RETURN_TO_DOCK, S.DOCKING, S.DOCKED):
        f.transition(st, 1.0)
    assert f.state == S.DOCKED and len(f.history) == 9
    with pytest.raises(InvalidTransition):
        MissionFSM().transition(S.COVER, 0.0)


def test_adaptive_suction_modes():
    a = AdaptiveSuction()
    for i in range(40):
        a.update(i * 0.05, 0.05, True, 0)
    assert a.mode == "ECO" and abs(a.duty - 0.55) < 1e-6
    for i in range(40):
        a.update(2 + i * 0.05, 0.05, True, 1)
    assert a.mode == "BOOST" and a.duty == pytest.approx(1.0)
    a.update(10, 0.05, False, 0)
    assert a.mode == "OFF"


def test_battery_pitch_numbers():
    assert pitch_runtime_estimate() == pytest.approx(10 / 4.62)
    b = BatteryModel()
    for _ in range(36000):          # one hour at full suction
        b.step(0.1, 0.25, 0.25, 1.0, True)
    assert 0 < b.soc < 0.7


def test_scoring_rewards_docking():
    base = dict(completion_time_s=200, time_budget_s=300, collected_g={"dust": 8},
                spawned_g={"dust": 10}, autonomous=True, collisions=0, cable_incidents=0,
                restarts=0, runtime_estimate_min=90, cost_inr=11480)
    docked = score(RunResult(docked=True, **base))
    not_docked = score(RunResult(docked=False, **base))
    assert docked.total > not_docked.total
    assert docked.parts["efficiency"] == pytest.approx(20.0)


def test_perception_mapping_and_projection():
    assert action_for("hair") == "suck" and action_for("power_cable") == "avoid"
    assert action_for("unknown") is None
    cam = CameraModel()
    fwd, left = cam.pixel_to_floor(cam.width / 2, cam.height - 1)
    assert fwd > cam.forward_offset and abs(left) < 1e-9


def test_mock_detector_fov_and_debris_ahead():
    det = MockDetector(recall_near=1.0, recall_far=1.0, pos_noise=0.0)
    pose = Pose2D(0, 0, 0)
    out = det.detect(pose, [("dust", 0.4, 0.0, 0.03), ("dust", -0.4, 0.0, 0.03), ("sock", 0.5, 0.1, 0.05)])
    assert {d.label for d in out} == {"dust", "sock"}
    assert debris_ahead(out, pose) == 1
    assert debris_ahead([Detection("dust", "suck", 1, 0.3, 0.5)], pose) == 0
