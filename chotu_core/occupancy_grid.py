"""Log-odds occupancy grid built from the ultrasonic + ToF range sensors.

The room outline is known in advance (Round 3 rules), so walls are seeded as
occupied; obstacles are discovered online.
"""
from __future__ import annotations

import math
from typing import Optional, Tuple

import numpy as np

L_OCC = 0.85
L_FREE = -0.35
L_MIN, L_MAX = -4.0, 6.0
OCC_THRESHOLD = 0.6
KEEPOUT = 50.0  # log-odds value that never decays: camera "avoid" zones


def disk_offsets(radius_cells: int):
    r = radius_cells
    return [(dy, dx) for dy in range(-r, r + 1) for dx in range(-r, r + 1)
            if dx * dx + dy * dy <= r * r]


def dilate(mask: np.ndarray, radius_cells: int) -> np.ndarray:
    """Binary dilation with a disk (numpy only - runs on the Pi without scipy)."""
    if radius_cells <= 0:
        return mask.copy()
    h, w = mask.shape
    out = mask.copy()
    for dy, dx in disk_offsets(radius_cells):
        ys0, ys1 = max(0, -dy), min(h, h - dy)
        xs0, xs1 = max(0, -dx), min(w, w - dx)
        out[ys0 + dy:ys1 + dy, xs0 + dx:xs1 + dx] |= mask[ys0:ys1, xs0:xs1]
    return out


class OccupancyGrid:
    def __init__(self, width_m: float, height_m: float, resolution: float):
        self.res = resolution
        self.width_m = width_m
        self.height_m = height_m
        self.nx = int(math.ceil(width_m / resolution))
        self.ny = int(math.ceil(height_m / resolution))
        self.logodds = np.zeros((self.ny, self.nx), dtype=np.float32)
        self.observed = np.zeros((self.ny, self.nx), dtype=bool)
        # The room outline is known exactly (Round 3 rules), so walls are not
        # mapped from noisy echoes - they are an analytic band instead.
        self.wall_ignore = 0.12
        xc = (np.arange(self.nx) + 0.5) * resolution
        yc = (np.arange(self.ny) + 0.5) * resolution
        self._wall_dist = np.minimum.outer(np.minimum(yc, height_m - yc),
                                           np.minimum(xc, width_m - xc))
        self._version = 0
        self._inflated_cache: dict = {}

    # ------------------------------------------------------------- coords
    def world_to_cell(self, x: float, y: float) -> Tuple[int, int]:
        return int(math.floor(x / self.res)), int(math.floor(y / self.res))

    def cell_to_world(self, ix: int, iy: int) -> Tuple[float, float]:
        return (ix + 0.5) * self.res, (iy + 0.5) * self.res

    def in_bounds(self, ix: int, iy: int) -> bool:
        return 0 <= ix < self.nx and 0 <= iy < self.ny

    # ------------------------------------------------------------- updates
    def near_wall(self, x: float, y: float, margin: Optional[float] = None) -> bool:
        m = self.wall_ignore if margin is None else margin
        return min(x, y, self.width_m - x, self.height_m - y) < m

    def update_ray(self, ox: float, oy: float, angle: float, distance: float,
                   max_range: float, mark_hit: bool = True, free_scale: float = 1.0) -> None:
        """Integrate one range reading. ``distance >= max_range`` means no echo."""
        hit = distance < max_range * 0.98
        length = min(distance, max_range)
        n = max(2, int(length / (self.res * 0.5)))
        ts = np.linspace(0.0, length, n, endpoint=False)
        xs = ox + ts * math.cos(angle)
        ys = oy + ts * math.sin(angle)
        ix = np.floor(xs / self.res).astype(int)
        iy = np.floor(ys / self.res).astype(int)
        ok = (ix >= 0) & (ix < self.nx) & (iy >= 0) & (iy < self.ny)
        ix, iy = ix[ok], iy[ok]
        if hit:
            # keep the cell right in front of the hit unchanged (beam width)
            hx, hy = self.world_to_cell(ox + length * math.cos(angle), oy + length * math.sin(angle))
            keep = ~((ix == hx) & (iy == hy))
            ix, iy = ix[keep], iy[keep]
        cells = np.unique(iy * self.nx + ix)
        fy, fx = cells // self.nx, cells % self.nx
        free = self.logodds[fy, fx] < KEEPOUT
        self.logodds[fy[free], fx[free]] = np.maximum(L_MIN, self.logodds[fy[free], fx[free]] + L_FREE * free_scale)
        self.observed[fy, fx] = True
        if hit:
            px, py = ox + distance * math.cos(angle), oy + distance * math.sin(angle)
            hx, hy = self.world_to_cell(px, py)
            if mark_hit and self.in_bounds(hx, hy) and not self.near_wall(px, py):
                if self.logodds[hy, hx] < KEEPOUT:
                    self.logodds[hy, hx] = min(L_MAX, self.logodds[hy, hx] + L_OCC)
                self.observed[hy, hx] = True
        self._version += 1

    def mark_disc(self, x: float, y: float, radius: float, keepout: bool = False) -> None:
        cx, cy = self.world_to_cell(x, y)
        rc = max(0, int(round(radius / self.res)))
        for dy, dx in disk_offsets(rc):
            ix, iy = cx + dx, cy + dy
            if self.in_bounds(ix, iy):
                self.logodds[iy, ix] = KEEPOUT if keepout else max(self.logodds[iy, ix], L_MAX)
                self.observed[iy, ix] = True
        self._version += 1

    # ------------------------------------------------------------- queries
    def occupied_mask(self) -> np.ndarray:
        return self.logodds > OCC_THRESHOLD

    def wall_band(self, radius_m: float) -> np.ndarray:
        return self._wall_dist < radius_m + 0.02

    def inflated_mask(self, radius_m: float) -> np.ndarray:
        """Cells the robot *centre* must avoid: inflated obstacles + wall band."""
        rc = int(math.ceil(radius_m / self.res))
        key = round(radius_m, 4)
        cached = self._inflated_cache.get(key)
        if cached is not None and cached[0] == self._version:
            return cached[1]
        mask = dilate(self.occupied_mask(), rc) | self.wall_band(radius_m)
        self._inflated_cache[key] = (self._version, mask)
        return mask

    def is_free(self, x: float, y: float, radius_m: float) -> bool:
        ix, iy = self.world_to_cell(x, y)
        if not self.in_bounds(ix, iy):
            return False
        return not self.inflated_mask(radius_m)[iy, ix]

    def to_ros_data(self) -> np.ndarray:
        """int8 0..100 / -1 layout used by nav_msgs/OccupancyGrid (row-major, y-up)."""
        p = 1.0 - 1.0 / (1.0 + np.exp(np.clip(self.logodds, -10, 10)))
        data = (p * 100).astype(np.int8)
        data[~self.observed] = -1
        return data.reshape(-1)

    def nearest_free(self, x: float, y: float, radius_m: float,
                     search_m: float = 0.4) -> Optional[Tuple[float, float]]:
        mask = self.inflated_mask(radius_m)
        cx, cy = self.world_to_cell(x, y)
        rc = int(search_m / self.res)
        best, best_d = None, 1e9
        for dy in range(-rc, rc + 1):
            for dx in range(-rc, rc + 1):
                ix, iy = cx + dx, cy + dy
                if self.in_bounds(ix, iy) and not mask[iy, ix]:
                    d = dx * dx + dy * dy
                    if d < best_d:
                        best, best_d = (ix, iy), d
        return None if best is None else self.cell_to_world(*best)


def flood_fill(blocked: np.ndarray, start: Tuple[int, int]) -> np.ndarray:
    """4-connected reachability from ``start`` (ix, iy) over ~blocked cells."""
    from collections import deque
    ny, nx = blocked.shape
    seen = np.zeros_like(blocked, dtype=bool)
    sx, sy = start
    if not (0 <= sx < nx and 0 <= sy < ny):
        return seen
    seen[sy, sx] = True
    q = deque([(sx, sy)])
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            xx, yy = x + dx, y + dy
            if 0 <= xx < nx and 0 <= yy < ny and not seen[yy, xx] and not blocked[yy, xx]:
                seen[yy, xx] = True
                q.append((xx, yy))
    return seen
