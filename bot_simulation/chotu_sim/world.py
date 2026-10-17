"""Randomised AtomQuest challenge room.

Round 3 rules: the *nature and number* of obstacles and the garbage types
are known in advance, but their *placement* is randomised for every team.
``generate_room(seed)`` reproduces exactly that: a fixed obstacle inventory
placed at random, plus clustered + scattered garbage of every type.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import cv2
import numpy as np

from chotu_core.config import GARBAGE_TYPES, ChotuConfig, DEFAULT_CONFIG

RASTER_RES = 0.01  # 1 cm ground-truth raster


@dataclass
class Obstacle:
    kind: str                 # box | chair | bin | pillar
    shape: str                # rect | circle | chair
    cx: float
    cy: float
    w: float = 0.0
    h: float = 0.0
    r: float = 0.0
    angle: float = 0.0

    def footprint(self) -> List[Tuple[str, tuple]]:
        if self.shape == "circle":
            return [("circle", (self.cx, self.cy, self.r))]
        if self.shape == "chair":
            legs = []
            for sx in (-1, 1):
                for sy in (-1, 1):
                    lx, ly = sx * self.w / 2, sy * self.h / 2
                    c, s = math.cos(self.angle), math.sin(self.angle)
                    legs.append(("circle", (self.cx + c * lx - s * ly, self.cy + s * lx + c * ly, 0.03)))
            return legs
        return [("rect", (self.cx, self.cy, self.w, self.h, self.angle))]

    def bounding_radius(self) -> float:
        if self.shape == "circle":
            return self.r
        return math.hypot(self.w, self.h) / 2


@dataclass
class Cable:
    points: List[Tuple[float, float]]


@dataclass
class GarbageItem:
    gid: int
    kind: str
    x: float
    y: float
    collected: bool = False
    inside: bool = False
    attempts: int = 0


@dataclass
class Room:
    seed: int
    width: float
    height: float
    obstacles: List[Obstacle]
    cables: List[Cable]
    garbage: List[GarbageItem]
    raster: np.ndarray = field(repr=False)       # uint8, 1 = solid
    dist_m: np.ndarray = field(repr=False)       # distance to nearest solid (m)

    def dist_at(self, x: float, y: float) -> float:
        ix, iy = int(x / RASTER_RES), int(y / RASTER_RES)
        if not (0 <= ix < self.raster.shape[1] and 0 <= iy < self.raster.shape[0]):
            return 0.0
        return float(self.dist_m[iy, ix])

    def raycast(self, x: float, y: float, angle: float, max_range: float) -> float:
        ts = np.arange(0.0, max_range, RASTER_RES)
        xs = ((x + ts * math.cos(angle)) / RASTER_RES).astype(int)
        ys = ((y + ts * math.sin(angle)) / RASTER_RES).astype(int)
        h, w = self.raster.shape
        oob = (xs < 0) | (xs >= w) | (ys < 0) | (ys >= h)
        xs, ys = np.clip(xs, 0, w - 1), np.clip(ys, 0, h - 1)
        hit = oob | (self.raster[ys, xs] > 0)
        idx = np.argmax(hit)
        return float(ts[idx]) if hit[idx] else max_range

    def spawned_mass(self):
        out = {k: 0.0 for k in GARBAGE_TYPES}
        for g in self.garbage:
            out[g.kind] += GARBAGE_TYPES[g.kind].mass_g
        return out

    def collected_mass(self):
        out = {k: 0.0 for k in GARBAGE_TYPES}
        for g in self.garbage:
            if g.collected:
                out[g.kind] += GARBAGE_TYPES[g.kind].mass_g
        return out


def _rasterise(width: float, height: float, obstacles: List[Obstacle]) -> np.ndarray:
    w, h = int(round(width / RASTER_RES)), int(round(height / RASTER_RES))
    img = np.zeros((h, w), np.uint8)
    img[:2, :] = img[-2:, :] = 1
    img[:, :2] = img[:, -2:] = 1
    for ob in obstacles:
        for shape, p in ob.footprint():
            if shape == "circle":
                cx, cy, r = p
                cv2.circle(img, (int(cx / RASTER_RES), int(cy / RASTER_RES)), int(r / RASTER_RES), 1, -1)
            else:
                cx, cy, rw, rh, a = p
                box = cv2.boxPoints(((cx / RASTER_RES, cy / RASTER_RES), (rw / RASTER_RES, rh / RASTER_RES), math.degrees(a)))
                cv2.fillPoly(img, [np.int32(np.round(box))], 1)
    return img


def generate_room(seed: int, cfg: ChotuConfig = DEFAULT_CONFIG,
                  n_boxes: int = 2, n_chairs: int = 1, n_bins: int = 1, n_cables: int = 1,
                  garbage_counts: Optional[dict] = None) -> Room:
    rng = random.Random(seed)
    W, H = cfg.room.width, cfg.room.height
    dock = (cfg.room.dock_x, 0.0)
    garbage_counts = garbage_counts or {"dust": 46, "hair": 14, "paper": 10, "wrapper": 6, "wire_strand": 9}

    obstacles: List[Obstacle] = []
    inventory = ["chair"] * n_chairs + ["box"] * n_boxes + ["bin"] * n_bins
    for kind in inventory:
        for _ in range(400):
            if kind == "box":
                ob = Obstacle("box", "rect", 0, 0, w=rng.uniform(0.28, 0.45), h=rng.uniform(0.22, 0.38),
                              angle=rng.choice([0.0, 0.0, rng.uniform(-0.5, 0.5)]))
            elif kind == "chair":
                ob = Obstacle("chair", "chair", 0, 0, w=0.38, h=0.38, angle=rng.uniform(-0.4, 0.4))
            else:
                ob = Obstacle("bin", "circle", 0, 0, r=rng.uniform(0.11, 0.15))
            br = ob.bounding_radius()
            ob.cx = rng.uniform(0.25 + br, W - 0.25 - br)
            ob.cy = rng.uniform(0.25 + br, H - 0.25 - br)
            if math.hypot(ob.cx - dock[0], ob.cy - dock[1]) < 1.0 + br:
                continue
            # leave a robot-sized corridor between obstacles
            if any(math.hypot(ob.cx - o.cx, ob.cy - o.cy) < br + o.bounding_radius() + 0.42 for o in obstacles):
                continue
            obstacles.append(ob)
            break

    raster = _rasterise(W, H, obstacles)
    dist = cv2.distanceTransform((1 - raster).astype(np.uint8), cv2.DIST_L2, 5) * RASTER_RES

    cables: List[Cable] = []
    for _ in range(n_cables):
        for _ in range(400):
            x0, y0 = rng.uniform(0.5, W - 0.5), rng.uniform(1.0, H - 0.4)
            a = rng.uniform(0, math.pi)
            pts = [(x0, y0)]
            for _k in range(4):
                a += rng.uniform(-0.6, 0.6)
                pts.append((pts[-1][0] + 0.17 * math.cos(a), pts[-1][1] + 0.17 * math.sin(a)))
            if all(0.3 < px < W - 0.3 and 0.3 < py < H - 0.3 and
                   dist[int(py / RASTER_RES), int(px / RASTER_RES)] > 0.30 for px, py in pts):
                cables.append(Cable(pts))
                break

    def ok(x: float, y: float) -> bool:
        if not (0.06 < x < W - 0.06 and 0.06 < y < H - 0.06):
            return False
        if dist[int(y / RASTER_RES), int(x / RASTER_RES)] < 0.05:
            return False
        if math.hypot(x - dock[0], y - dock[1]) < 0.35:
            return False
        for c in cables:
            if min(math.hypot(x - px, y - py) for px, py in c.points) < 0.15:
                return False
        return True

    zones = [(rng.uniform(0.5, W - 0.5), rng.uniform(0.7, H - 0.5)) for _ in range(3)]
    garbage: List[GarbageItem] = []
    gid = 0
    for kind, n in garbage_counts.items():
        placed = 0
        while placed < n:
            if kind in ("dust", "hair") and rng.random() < 0.6:
                zx, zy = rng.choice(zones)
                x, y = rng.gauss(zx, 0.28), rng.gauss(zy, 0.28)
            else:
                x, y = rng.uniform(0.06, W - 0.06), rng.uniform(0.06, H - 0.06)
            if ok(x, y):
                garbage.append(GarbageItem(gid, kind, x, y))
                gid += 1
                placed += 1

    return Room(seed, W, H, obstacles, cables, garbage, raster, dist)
