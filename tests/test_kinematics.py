import math

from chotu_core.kinematics import DiffDrive, FusedOdometry, Pose2D, wrap_angle


def test_wrap_angle():
    assert abs(abs(wrap_angle(3 * math.pi)) - math.pi) < 1e-9
    assert abs(wrap_angle(-0.5) + 0.5) < 1e-12


def test_twist_wheel_inverse():
    dd = DiffDrive(0.26, 0.0325, 20)
    vl, vr = dd.twist_to_wheels(0.2, 0.8)
    v, w = dd.wheels_to_twist(vl, vr)
    assert abs(v - 0.2) < 1e-12 and abs(w - 0.8) < 1e-12


def test_integrate_full_circle_returns_home():
    p = Pose2D(1, 1, 0)
    for _ in range(1000):
        p = DiffDrive.integrate(p, 0.2, 2 * math.pi / 10, 0.01)
    assert math.hypot(p.x - 1, p.y - 1) < 1e-6


def test_encoder_odometry_straight_line():
    dd = DiffDrive(0.26, 0.0325, 20)
    odo = FusedOdometry(dd, Pose2D(0, 0, 0))
    for _ in range(100):
        odo.update(1, 1, 0.0, 0.05)
    assert abs(odo.pose.x - 100 * dd.metres_per_tick) < 1e-9
    assert abs(odo.pose.y) < 1e-9
