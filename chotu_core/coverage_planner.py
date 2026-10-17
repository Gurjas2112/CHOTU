"""Boustrophedon (zig-zag) coverage with online skipping + frontier fill.

1. ``BoustrophedonPlanner`` lays serpentine lanes over the *known* room
   outline (spacing < cleaning width, so lanes overlap).
2. While driving, waypoints that become blocked by newly mapped obstacles are
   skipped, and A* detours connect the remaining ones.
3. ``CoverageTracker`` stamps the swept area. When the lanes are exhausted,
   ``frontier_targets`` returns the centres of the remaining uncleaned pockets
   (behind obstacles, skipped waypoints), nearest first - the "path
   optimisation" the mentor review asked for.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import List, Tuple

import numpy as np

from .occupancy_grid import disk_offsets


@dataclass
class CoverageWaypoint:
    x: float
    y: float
    lane: int
    status: str = "pending"  # pending | done | skipped
    fails: int = 0
    retry_after: float = 0.0


class BoustrophedonPlanner:
    def __init__(self, width: float, height: float, lane_spacing: float,
                 wall_margin: float, step: float, start_y: float = 0.0):
        self.width = width
        self.height = height
        self.lane_spacing = lane_spacing
        self.margin = wall_margin
        self.step = step
        self.start_y = start_y

    def generate(self, start_x: float) -> List[CoverageWaypoint]:
        y0, y1 = self.margin, self.height - self.margin
        x0, x1 = self.margin, self.width - self.margin
        n_lanes = int(math.floor((y1 - y0) / self.lane_spacing)) + 1
        ys = [y0 + i * self.lane_spacing for i in range(n_lanes)]
        if ys[-1] < y1 - 0.05:
            ys.append(y1)
        n_pts = max(2, int(math.ceil((x1 - x0) / self.step)) + 1)
        xs = list(np.linspace(x0, x1, n_pts))
        # Start the first lane at the end closer to the robot
        left_first = abs(start_x - x0) <= abs(start_x - x1)
        wps: List[CoverageWaypoint] = []
        for lane, y in enumerate(ys):
            forward = (lane % 2 == 0) == left_first
            for x in (xs if forward else xs[::-1]):
                wps.append(CoverageWaypoint(float(x), float(y), lane))
        return wps


class CoverageTracker:
    def __init__(self, width: float, height: float, resolution: float, cleaning_width: float):
        self.res = resolution
        self.nx = int(math.ceil(width / resolution))
        self.ny = int(math.ceil(height / resolution))
        self.cleaned = np.zeros((self.ny, self.nx), dtype=bool)
        self._offsets = disk_offsets(max(1, int(round(cleaning_width / 2 / resolution))))

    def mark(self, x: float, y: float) -> None:
        cx, cy = int(x / self.res), int(y / self.res)
        for dy, dx in self._offsets:
            ix, iy = cx + dx, cy + dy
            if 0 <= ix < self.nx and 0 <= iy < self.ny:
                self.cleaned[iy, ix] = True

    def coverage_ratio(self, cleanable: np.ndarray) -> float:
        total = int(cleanable.sum())
        return 0.0 if total == 0 else float((self.cleaned & cleanable).sum()) / total

    def frontier_targets(self, centre_free: np.ndarray, rx: float, ry: float,
                         min_cells: int) -> List[Tuple[float, float, int]]:
        """Uncleaned pockets the robot centre can reach, sorted by distance.

        Returns ``(x, y, size_cells)`` where (x, y) is the pocket cell closest
        to the robot (so the robot sweeps into the pocket from its edge).
        """
        todo = centre_free & ~self.cleaned
        seen = np.zeros_like(todo)
        out = []
        ny, nx = todo.shape
        for sy, sx in zip(*np.nonzero(todo)):
            if seen[sy, sx]:
                continue
            comp = []
            q = deque([(sy, sx)])
            seen[sy, sx] = True
            while q:
                y, x = q.popleft()
                comp.append((y, x))
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    yy, xx = y + dy, x + dx
                    if 0 <= yy < ny and 0 <= xx < nx and todo[yy, xx] and not seen[yy, xx]:
                        seen[yy, xx] = True
                        q.append((yy, xx))
            if len(comp) < min_cells:
                continue
            arr = np.array(comp)
            wx = (arr[:, 1] + 0.5) * self.res
            wy = (arr[:, 0] + 0.5) * self.res
            # aim at the pocket's centroid cell (closest member to the centroid)
            cxm, cym = wx.mean(), wy.mean()
            k = int(np.argmin((wx - cxm) ** 2 + (wy - cym) ** 2))
            out.append((float(wx[k]), float(wy[k]), len(comp)))
        out.sort(key=lambda t: math.hypot(t[0] - rx, t[1] - ry) - 0.02 * t[2])
        return out
