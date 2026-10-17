import math

import numpy as np

from chotu_core.coverage_planner import BoustrophedonPlanner, CoverageTracker
from chotu_core.occupancy_grid import OccupancyGrid, dilate
from chotu_core.path_planner import GridPlanner, astar, path_length


def test_ray_marks_hit_and_free():
    g = OccupancyGrid(3, 3, 0.05)
    for _ in range(3):
        g.update_ray(0.5, 1.5, 0.0, 1.0, 1.5)
    hx, hy = g.world_to_cell(1.5, 1.5)
    assert g.occupied_mask()[hy, hx]
    ix, iy = g.world_to_cell(1.0, 1.5)
    assert g.logodds[iy, ix] < 0


def test_wall_echo_is_not_mapped_as_obstacle():
    g = OccupancyGrid(3, 3, 0.05)
    g.update_ray(1.5, 1.5, 0.0, 1.47, 1.5)   # hits the right wall at x = 2.97
    assert not g.occupied_mask().any()
    # the analytic wall band still keeps the robot centre away from the wall
    assert not g.is_free(0.1, 1.5, 0.19) and g.is_free(0.3, 1.5, 0.19)


def test_dilate_disk():
    m = np.zeros((11, 11), bool)
    m[5, 5] = True
    d = dilate(m, 2)
    assert d.sum() == 13 and d[5, 7] and not d[7, 7]


def test_astar_around_wall_and_unreachable():
    blocked = np.zeros((20, 20), bool)
    blocked[2:18, 10] = True
    path = astar(blocked, (2, 10), (17, 10))
    assert path is not None and path[0] == (2, 10) and path[-1] == (17, 10)
    assert all(not blocked[y, x] for x, y in path)
    blocked[:, 10] = True
    assert astar(blocked, (2, 10), (17, 10)) is None


def test_grid_planner_detours_around_mapped_box():
    g = OccupancyGrid(3, 3, 0.05)
    g.mark_disc(1.5, 1.5, 0.25)
    pts = GridPlanner(g, 0.19).plan(0.5, 1.5, 2.5, 1.5)
    assert pts is not None and pts[-1] == (2.5, 1.5)
    assert path_length([(0.5, 1.5)] + pts) > 2.0      # longer than the straight line
    for x, y in pts:
        assert math.hypot(x - 1.5, y - 1.5) > 0.3


def test_boustrophedon_serpentine():
    wps = BoustrophedonPlanner(3.0, 3.0, 0.22, 0.24, 0.3).generate(start_x=1.5)
    lanes = sorted({w.lane for w in wps})
    assert len(lanes) == 13
    lane0 = [w for w in wps if w.lane == 0]
    lane1 = [w for w in wps if w.lane == 1]
    assert (lane0[0].x < lane0[-1].x) != (lane1[0].x < lane1[-1].x)   # direction alternates


def test_coverage_tracker_and_frontiers():
    t = CoverageTracker(2.0, 2.0, 0.05, 0.24)
    free = np.ones((40, 40), bool)
    for x in np.linspace(0.0, 2.0, 60):   # stripe wall-to-wall
        t.mark(x, 1.0)
    assert 0.1 < t.coverage_ratio(free) < 0.2
    targets = t.frontier_targets(free, 1.0, 1.0, 5)
    assert len(targets) == 2   # pocket above and below the swept stripe
