"""8-connected A* on a two-tier cost map, with line-of-sight smoothing.

* **hard** cells - the robot centre physically cannot be there (obstacle
  dilated by slightly less than the robot radius, and the known walls).
* **soft** cells - the safety inflation band.  Paths never use them, except
  inside a small *escape disc* around the robot's current cell, so the robot
  can always plan its way out of a tight spot instead of freezing - while
  never being routed through narrow gaps such as between chair legs.
"""
from __future__ import annotations

import heapq
import math
from typing import Dict, List, Optional, Tuple

import numpy as np

from .occupancy_grid import dilate

Cell = Tuple[int, int]  # (ix, iy)

_SQ2 = math.sqrt(2)
_NEIGHBOURS = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
               (1, 1, _SQ2), (1, -1, _SQ2), (-1, 1, _SQ2), (-1, -1, _SQ2)]


def astar(blocked: np.ndarray, start: Cell, goal: Cell,
          soft: Optional[np.ndarray] = None, soft_cost: float = 8.0,
          max_expansions: int = 60000) -> Optional[List[Cell]]:
    """Return a list of cells from start to goal (inclusive) or None.

    ``blocked[iy, ix]`` True = impassable.  ``soft`` cells cost ``soft_cost``
    times more.  The start cell is always allowed.
    """
    ny, nx = blocked.shape
    sx, sy = start
    gx, gy = goal
    if not (0 <= gx < nx and 0 <= gy < ny) or blocked[gy, gx]:
        return None
    if start == goal:
        return [start]

    def h(x: int, y: int) -> float:
        dx, dy = abs(x - gx), abs(y - gy)
        return (dx + dy) + (_SQ2 - 2) * min(dx, dy)

    g: Dict[Cell, float] = {start: 0.0}
    parent: Dict[Cell, Optional[Cell]] = {start: None}
    open_heap = [(h(sx, sy), 0.0, start)]
    closed = set()
    expansions = 0
    while open_heap:
        _, gc, cur = heapq.heappop(open_heap)
        if cur in closed:
            continue
        if cur == goal:
            path = [cur]
            prev = parent[cur]
            while prev is not None:
                path.append(prev)
                prev = parent[prev]
            return path[::-1]
        closed.add(cur)
        expansions += 1
        if expansions > max_expansions:
            return None
        cx, cy = cur
        for dx, dy, cost in _NEIGHBOURS:
            x, y = cx + dx, cy + dy
            if not (0 <= x < nx and 0 <= y < ny) or blocked[y, x]:
                continue
            if dx and dy and (blocked[cy, x] or blocked[y, cx]):
                continue  # no corner cutting
            if soft is not None and soft[y, x]:
                cost *= soft_cost
            ng = gc + cost
            if ng < g.get((x, y), 1e18):
                g[(x, y)] = ng
                parent[(x, y)] = cur
                heapq.heappush(open_heap, (ng + h(x, y), ng, (x, y)))
    return None


def line_of_sight(blocked: np.ndarray, a: Cell, b: Cell) -> bool:
    (x0, y0), (x1, y1) = a, b
    n = int(max(abs(x1 - x0), abs(y1 - y0)) * 2) + 1
    for i in range(n + 1):
        t = i / n
        x = int(round(x0 + (x1 - x0) * t))
        y = int(round(y0 + (y1 - y0) * t))
        if blocked[y, x] and (x, y) != a:
            return False
    return True


def smooth(blocked: np.ndarray, path: List[Cell]) -> List[Cell]:
    """Greedy string-pulling: keep only the cells needed for line of sight.

    Cells already on the A* path are treated as passable, so smoothing never
    routes the robot through *new* soft/blocked cells.
    """
    if len(path) <= 2:
        return list(path)
    mask = blocked.copy()
    for x, y in path:
        mask[y, x] = False
    out = [path[0]]
    i = 0
    while i < len(path) - 1:
        j = len(path) - 1
        while j > i + 1 and not line_of_sight(mask, path[i], path[j]):
            j -= 1
        out.append(path[j])
        i = j
    return out


def path_length(points: List[Tuple[float, float]]) -> float:
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:]))


class GridPlanner:
    """Plans in world coordinates on an OccupancyGrid."""

    def __init__(self, grid, robot_clearance: float, hard_shrink: float = 0.05,
                 escape_radius: float = 0.3):
        self.grid = grid
        self.clearance = robot_clearance
        self.hard_shrink = hard_shrink
        self.escape_cells = int(round(escape_radius / grid.res))
        self._hard_cache = (-1, None)

    def masks(self) -> Tuple[np.ndarray, np.ndarray]:
        soft = self.grid.inflated_mask(self.clearance)
        if self._hard_cache[0] != self.grid._version:
            rc = int(math.ceil((self.clearance - self.hard_shrink) / self.grid.res))
            hard = dilate(self.grid.occupied_mask(), rc) | self.grid.wall_band(self.clearance)
            self._hard_cache = (self.grid._version, hard)
        return self._hard_cache[1], soft

    def plan(self, sx: float, sy: float, gx: float, gy: float,
             snap_goal: bool = True, relaxed: bool = False) -> Optional[List[Tuple[float, float]]]:
        """Plan a path. ``relaxed=True`` (last resort, e.g. getting home when
        boxed in by stale map evidence) lets the path cross the soft clearance
        band anywhere, at 8x cost - only hard cells are forbidden."""
        hard, soft = self.masks()
        start = self.grid.world_to_cell(sx, sy)
        goal = self.grid.world_to_cell(gx, gy)
        if not self.grid.in_bounds(*goal) or not self.grid.in_bounds(*start):
            return None
        exact_goal = not soft[goal[1], goal[0]]
        if not exact_goal:
            if not snap_goal:
                return None
            snapped = self.grid.nearest_free(gx, gy, self.clearance, search_m=0.15)
            if snapped is None:
                return None
            goal = self.grid.world_to_cell(*snapped)
        blocked = hard if relaxed else soft
        if not relaxed and soft[start[1], start[0]]:
            blocked = soft.copy()
            r = self.escape_cells
            y0, y1 = max(0, start[1] - r), min(soft.shape[0], start[1] + r + 1)
            x0, x1 = max(0, start[0] - r), min(soft.shape[1], start[0] + r + 1)
            blocked[y0:y1, x0:x1] = hard[y0:y1, x0:x1]
        cells = astar(blocked, start, goal, soft=soft)
        if cells is None:
            return None
        cells = smooth(soft, cells)
        pts = [self.grid.cell_to_world(ix, iy) for ix, iy in cells[1:]]
        if exact_goal:
            if pts:
                pts[-1] = (gx, gy)
            else:
                pts = [(gx, gy)]
        return pts
