"""Futuristic "mission control" HUD for the CHOTU digital twin (OpenCV only).

Left : top-down digital twin - ground truth room, live coverage heat-map,
       robot belief map, sensor rays, camera FOV, AI detections, A* path.
Right: mission FSM timeline, telemetry cards, per-garbage efficiency,
       live AtomQuest score projection, robot SLAM-map inset, event log.
"""
from __future__ import annotations

import math
from typing import List, Optional, Tuple

import cv2
import numpy as np

from chotu_core.config import GARBAGE_TYPES, PROTOTYPE_BOM_INR
from chotu_core.mission_fsm import MissionState
from chotu_core.scoring import WEIGHTS, RunResult, score

W, H = 1280, 720
BG = (22, 13, 9)
PANEL = (40, 25, 16)
PANEL_HI = (62, 40, 24)
GRID = (55, 40, 28)
CYAN = (255, 229, 0)
TEAL = (170, 200, 20)
MAGENTA = (200, 70, 255)
GREEN = (120, 255, 90)
AMBER = (0, 190, 255)
RED = (90, 80, 255)
WHITE = (238, 238, 238)
DIM = (150, 130, 115)
FONT = cv2.FONT_HERSHEY_SIMPLEX
FONT_B = cv2.FONT_HERSHEY_DUPLEX
AA = cv2.LINE_AA

STATE_CHIPS = [("UNDOCK", "UNDOCK"), ("SCAN", "SCAN 360"), ("COVER", "COVER"),
               ("SPOT_CLEAN", "SPOT/FILL"), ("RETURN_TO_DOCK", "RETURN"), ("DOCKING", "DOCKING"),
               ("DOCKED", "DOCKED")]
STATE_COLOURS = {"UNDOCK": (255, 160, 60), "SCAN": (255, 90, 190), "COVER": CYAN,
                 "SPOT_CLEAN": GREEN, "STUCK_RECOVERY": RED, "RETURN_TO_DOCK": AMBER,
                 "DOCKING": (80, 220, 255), "DOCKED": GREEN, "IDLE": DIM}


def ascii(s: str) -> str:
    return s.replace("°", " deg").encode("ascii", "ignore").decode()


def text(img, s, org, scale=0.5, colour=WHITE, thick=1, font=FONT):
    cv2.putText(img, ascii(s), org, font, scale, colour, thick, AA)


def panel(img, x, y, w, h, title: Optional[str] = None, colour=PANEL):
    cv2.rectangle(img, (x, y), (x + w, y + h), colour, -1)
    cv2.rectangle(img, (x, y), (x + w, y + h), (90, 60, 35), 1, AA)
    # corner brackets - the "sci-fi" look
    for cx, cy, dx, dy in ((x, y, 1, 1), (x + w, y, -1, 1), (x, y + h, 1, -1), (x + w, y + h, -1, -1)):
        cv2.line(img, (cx, cy), (cx + 12 * dx, cy), CYAN, 2, AA)
        cv2.line(img, (cx, cy), (cx, cy + 12 * dy), CYAN, 2, AA)
    if title:
        text(img, title, (x + 10, y + 18), 0.45, CYAN, 1)


def glow_circle(img, c, r, colour, thick=2):
    """Neon glow, blended only inside the bounding box (fast)."""
    pad = r + 14
    x0, y0 = max(0, c[0] - pad), max(0, c[1] - pad)
    x1, y1 = min(img.shape[1], c[0] + pad), min(img.shape[0], c[1] + pad)
    roi = img[y0:y1, x0:x1]
    cc = (c[0] - x0, c[1] - y0)
    for k, a in ((6, 0.15), (3, 0.3)):
        ov = roi.copy()
        cv2.circle(ov, cc, r + k, colour, thick + k, AA)
        cv2.addWeighted(ov, a, roi, 1 - a, 0, roi)
    cv2.circle(img, c, r, colour, thick, AA)


class HudRenderer:
    def __init__(self, sim, title: str = "CHOTU // AUTONOMOUS CLEANING DIGITAL TWIN"):
        self.sim = sim
        self.title = title
        self.view = 584
        self.vx, self.vy = 38, 70
        self.scale = self.view / max(sim.room.width, sim.room.height)
        self._static = self._build_static()
        self.frame_no = 0

    # ------------------------------------------------------------ coords
    def px(self, x: float, y: float) -> Tuple[int, int]:
        return (int(self.vx + x * self.scale), int(self.vy + self.view - y * self.scale))

    # ------------------------------------------------------------ static layer
    def _build_static(self) -> np.ndarray:
        img = np.zeros((H, W, 3), np.uint8)
        img[:] = BG
        room = self.sim.room
        x0, y0 = self.px(0, 0)
        x1, y1 = self.px(room.width, room.height)
        cv2.rectangle(img, (x0, y1), (x1, y0), (30, 20, 14), -1)
        step = 0.25
        for i in range(int(room.width / step) + 1):
            p = self.px(i * step, 0)
            cv2.line(img, (p[0], y1), (p[0], y0), GRID if i % 4 else (75, 55, 38), 1)
        for j in range(int(room.height / step) + 1):
            p = self.px(0, j * step)
            cv2.line(img, (x0, p[1]), (x1, p[1]), GRID if j % 4 else (75, 55, 38), 1)
        cv2.rectangle(img, (x0, y1), (x1, y0), CYAN, 2, AA)
        for m in range(0, int(room.width) + 1):
            text(img, f"{m}m", (self.px(m, 0)[0] + 3, y1 + 13), 0.35, DIM)
        return img

    # ------------------------------------------------------------ main
    def render(self, extra_banner: Optional[str] = None) -> np.ndarray:
        sim = self.sim
        img = self._static.copy()
        self._draw_room(img)
        self._draw_header(img)
        self._draw_side(img)
        self._draw_timebar(img)
        if extra_banner:
            self._banner(img, extra_banner)
        self.frame_no += 1
        return img

    def _draw_header(self, img):
        sim = self.sim
        cv2.rectangle(img, (0, 0), (W, 56), (30, 18, 10), -1)
        cv2.line(img, (0, 56), (W, 56), CYAN, 1, AA)
        text(img, self.title, (20, 36), 0.78, CYAN, 2, FONT_B)
        text(img, f"AtomQuest 2025 | Hack O' Giants | room #{sim.seed}", (700, 24), 0.46, DIM)
        t = sim.mission.elapsed
        text(img, f"T+{int(t // 60):01d}:{t % 60:04.1f}", (700, 47), 0.62, WHITE, 1, FONT_B)
        left = max(0.0, sim.cfg.mission.time_budget_s - t)
        text(img, f"budget left {left:5.1f}s", (840, 47), 0.5, AMBER if left < 60 else GREEN)
        st = sim.mission.state.value
        col = STATE_COLOURS.get(st, WHITE)
        cv2.rectangle(img, (1060, 14), (1262, 44), col, 1, AA)
        text(img, st.replace("_", " "), (1070, 36), 0.55, col, 1, FONT_B)

    def _draw_room(self, img):
        sim, room, mission = self.sim, self.sim.room, self.sim.mission
        s = self.scale
        x0, y0 = self.px(0, 0)
        x1, y1 = self.px(room.width, room.height)
        roi = img[y1:y0, x0:x1]
        # live coverage (ground truth swept area)
        cov = sim.truth_cov.cleaned[::-1, :].astype(np.uint8) * 255
        cov = cv2.resize(cov, (roi.shape[1], roi.shape[0]), interpolation=cv2.INTER_NEAREST)
        tint = np.zeros_like(roi)
        tint[:] = (90, 75, 10)
        mask = cov > 0
        roi[mask] = cv2.addWeighted(roi, 0.45, tint, 0.55, 0)[mask]
        # robot belief: occupied cells
        occ = mission.grid.occupied_mask()[::-1, :].astype(np.uint8) * 255
        occ = cv2.resize(occ, (roi.shape[1], roi.shape[0]), interpolation=cv2.INTER_NEAREST)
        om = occ > 0
        mtint = np.zeros_like(roi)
        mtint[:] = (120, 30, 150)
        roi[om] = cv2.addWeighted(roi, 0.35, mtint, 0.65, 0)[om]
        # ground truth obstacles
        for ob in room.obstacles:
            for shape, p in ob.footprint():
                if shape == "circle":
                    c = self.px(p[0], p[1])
                    cv2.circle(img, c, max(2, int(p[2] * s)), (70, 60, 55), -1, AA)
                    cv2.circle(img, c, max(2, int(p[2] * s)), (230, 200, 160), 1, AA)
                else:
                    cx, cy, rw, rh, a = p
                    box = cv2.boxPoints(((0, 0), (rw, rh), math.degrees(a)))
                    pts = np.array([self.px(cx + bx, cy + by) for bx, by in box], np.int32)
                    cv2.fillPoly(img, [pts], (70, 60, 55), AA)
                    cv2.polylines(img, [pts], True, (230, 200, 160), 1, AA)
            if ob.kind != "chair":
                lc = self.px(ob.cx, ob.cy)
                text(img, ob.kind.upper(), (lc[0] - 14, lc[1] + 4), 0.32, (200, 190, 170))
            else:
                lc = self.px(ob.cx, ob.cy)
                text(img, "CHAIR", (lc[0] - 16, lc[1] + 4), 0.32, (200, 190, 170))
        # cables (low obstacle - invisible to range sensors)
        for c in room.cables:
            pts = np.array([self.px(x, y) for x, y in c.points], np.int32)
            cv2.polylines(img, [pts], False, (120, 40, 160), 7, AA)
            cv2.polylines(img, [pts], False, MAGENTA, 3, AA)
        # garbage
        for g in room.garbage:
            if g.collected:
                continue
            col = GARBAGE_TYPES[g.kind].colour_bgr
            c = self.px(g.x, g.y)
            if g.kind == "dust":
                cv2.circle(img, c, 2, col, -1, AA)
            elif g.kind == "hair":
                cv2.line(img, (c[0] - 3, c[1] - 2), (c[0] + 3, c[1] + 2), col, 1, AA)
            elif g.kind == "wire_strand":
                cv2.line(img, (c[0] - 4, c[1] + 1), (c[0] + 4, c[1] - 1), col, 2, AA)
            else:
                cv2.rectangle(img, (c[0] - 3, c[1] - 3), (c[0] + 3, c[1] + 3), col, -1, AA)
        # dock
        dx, dy = self.px(sim.cfg.room.dock_x, 0)
        pulse = 0.5 + 0.5 * math.sin(self.frame_no * 0.15)
        cv2.rectangle(img, (dx - 34, dy - 10), (dx + 34, dy), (int(60 + 100 * pulse), 200, 60), -1)
        text(img, "DOCK", (dx - 16, dy - 1), 0.36, (20, 20, 20), 1)
        # trail
        if len(sim.trail) > 1:
            pts = np.array([self.px(x, y) for x, y in sim.trail[-1500:]], np.int32)
            cv2.polylines(img, [pts], False, (140, 110, 40), 1, AA)
        # planned path
        p = sim.true_pose
        if mission.path:
            pts = [self.px(p.x, p.y)] + [self.px(*self._odom_to_world(x, y)) for x, y in mission.path]
            for a, b in zip(pts, pts[1:]):
                self._dashed(img, a, b, AMBER)
            cv2.circle(img, pts[-1], 5, AMBER, 1, AA)
        # pending coverage waypoints
        for wp in mission.waypoints:
            if wp.status == "pending":
                cv2.circle(img, self.px(*self._odom_to_world(wp.x, wp.y)), 1, (160, 140, 60), -1)
        # camera FOV
        fov = math.radians(sim.cfg.sensors.camera_fov_deg) / 2
        rng = sim.cfg.sensors.camera_range
        poly = [self.px(p.x, p.y)]
        for k in range(9):
            a = p.theta - fov + 2 * fov * k / 8
            poly.append(self.px(p.x + rng * math.cos(a), p.y + rng * math.sin(a)))
        arr = np.array(poly, np.int32)
        bx0, by0 = np.maximum(arr.min(0), 0)
        bx1, by1 = np.minimum(arr.max(0) + 1, (W, H))
        roi = img[by0:by1, bx0:bx1]
        ov = roi.copy()
        cv2.fillPoly(ov, [arr - (bx0, by0)], (90, 60, 20))
        cv2.addWeighted(ov, 0.25, roi, 0.75, 0, roi)
        # range sensor rays
        for ox, oy, ang, d, mx, src in sim.last_rays:
            end = (ox + d * math.cos(ang), oy + d * math.sin(ang))
            col = GREEN if d > 0.35 else (AMBER if d > 0.12 else RED)
            if src == "tof":
                col = (255, 120, 255) if d > 0.35 else RED
            cv2.line(img, self.px(ox, oy), self.px(*end), col, 1, AA)
            if d < mx * 0.98:
                cv2.circle(img, self.px(*end), 3, col, -1, AA)
        # AI detections
        for d in mission.last_detections:
            wx, wy = self._odom_to_world(d.x, d.y)
            c = self.px(wx, wy)
            col = GREEN if d.action == "suck" else MAGENTA
            r = 7
            for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
                cv2.line(img, (c[0] + sx * r, c[1] + sy * r), (c[0] + sx * (r - 4), c[1] + sy * r), col, 1, AA)
                cv2.line(img, (c[0] + sx * r, c[1] + sy * r), (c[0] + sx * r, c[1] + sy * (r - 4)), col, 1, AA)
            if d.action == "avoid":
                text(img, f"AVOID {d.label}", (c[0] + 9, c[1] - 6), 0.33, MAGENTA)
        # robot
        c = self.px(p.x, p.y)
        rr = int(sim.cfg.robot.radius * self.scale)
        cv2.circle(img, c, rr, (60, 45, 30), -1, AA)
        glow_circle(img, c, rr, CYAN, 2)
        hx = (int(c[0] + rr * math.cos(p.theta)), int(c[1] - rr * math.sin(p.theta)))
        cv2.line(img, c, hx, WHITE, 2, AA)
        hw = sim.cfg.robot.cleaning_width / 2
        nx, ny = -math.sin(p.theta), math.cos(p.theta)
        a = self.px(p.x + hw * nx, p.y + hw * ny)
        b = self.px(p.x - hw * nx, p.y - hw * ny)
        suction = sim.last_cmd.suction
        cv2.line(img, a, b, (0, int(120 + 135 * suction), 255) if suction > 0.05 else DIM, 2, AA)
        text(img, "CHOTU", (c[0] - 18, c[1] + 4), 0.32, WHITE)
        # legend
        lx, ly = self.vx, self.vy + self.view + 18
        for label, col in (("swept", (90, 75, 10)), ("robot map", (120, 30, 150)), ("A* path", AMBER),
                           ("cable (AI-avoid)", MAGENTA), ("debris", (90, 200, 255))):
            cv2.rectangle(img, (lx, ly - 8), (lx + 10, ly + 2), col, -1)
            text(img, label, (lx + 14, ly + 1), 0.36, DIM)
            lx += 30 + 8 * len(label)

    def _odom_to_world(self, x: float, y: float) -> Tuple[float, float]:
        """Robot belief (odom frame) -> ground truth frame for display."""
        sim = self.sim
        e, t = sim.odom.pose, sim.true_pose
        dth = t.theta - e.theta
        dx, dy = x - e.x, y - e.y
        c, s = math.cos(dth), math.sin(dth)
        return t.x + c * dx - s * dy, t.y + s * dx + c * dy

    @staticmethod
    def _dashed(img, a, b, col, dash=7):
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        n = max(1, int(d / dash))
        for i in range(0, n, 2):
            p0 = (int(a[0] + (b[0] - a[0]) * i / n), int(a[1] + (b[1] - a[1]) * i / n))
            p1 = (int(a[0] + (b[0] - a[0]) * min(n, i + 1) / n), int(a[1] + (b[1] - a[1]) * min(n, i + 1) / n))
            cv2.line(img, p0, p1, col, 2, AA)

    # ------------------------------------------------------------ side panel
    def live_score(self):
        sim = self.sim
        avg_p = sim.battery.consumed_wh * 3600 / max(sim.t, 1e-6)
        rr = RunResult(True, sim.mission.elapsed, sim.cfg.mission.time_budget_s,
                       sim.room.collected_mass(), sim.room.spawned_mass(), True,
                       sim.collisions, sim.cable_incidents, 0,
                       sim.battery.runtime_minutes(avg_p), PROTOTYPE_BOM_INR)
        return score(rr), avg_p

    def _draw_side(self, img):
        sim = self.sim
        X = 660
        # FSM chips
        panel(img, X, 72, 600, 62, "MISSION STATE MACHINE")
        cur = sim.mission.state.value
        visited = {tr.dst.value for tr in sim.mission.fsm.history} | {"IDLE"}
        cx = X + 10
        for key, label in STATE_CHIPS:
            w = 12 + 8 * len(label)
            col = STATE_COLOURS.get(key, WHITE)
            if key == cur or (cur == "STUCK_RECOVERY" and key == (sim.mission.fsm.resume_state or MissionState.COVER).value):
                cv2.rectangle(img, (cx, 96), (cx + w, 124), col, -1, AA)
                text(img, label, (cx + 6, 115), 0.42, (20, 20, 20), 1)
            else:
                cv2.rectangle(img, (cx, 96), (cx + w, 124), col if key in visited else (90, 70, 55), 1, AA)
                text(img, label, (cx + 6, 115), 0.42, col if key in visited else (110, 95, 80))
            cx += w + 6
        if cur == "STUCK_RECOVERY":
            text(img, "RECOVERY", (X + 520, 90), 0.4, RED)

        # telemetry cards
        card, avg_p = self.live_score()
        cov = sim.truth_cov.coverage_ratio(sim.cleanable)
        col_g = sum(sim.room.collected_mass().values())
        tot_g = sum(sim.room.spawned_mass().values())
        cards = [
            ("COVERAGE", f"{cov * 100:5.1f}%", CYAN, cov),
            ("DEBRIS w/w", f"{col_g:4.1f}/{tot_g:.0f} g", GREEN, col_g / max(tot_g, 1e-6)),
            ("BATTERY", f"{sim.battery.soc * 100:5.1f}%  {sim.battery.voltage:4.1f}V", AMBER, sim.battery.soc),
            ("POWER", f"{sim.battery.last_power_w:4.1f} W", (255, 160, 60), sim.battery.last_power_w / 60),
            ("SUCTION", f"{sim.mission.suction.mode} {sim.last_cmd.suction * 100:3.0f}%", (0, 140, 255), sim.last_cmd.suction),
            ("SPEED", f"{abs(sim.v_act):4.2f} m/s", (255, 90, 190), abs(sim.v_act) / sim.cfg.robot.max_linear),
        ]
        for i, (lab, val, col, frac) in enumerate(cards):
            x = X + (i % 3) * 202
            y = 144 + (i // 3) * 70
            panel(img, x, y, 194, 62)
            text(img, lab, (x + 10, y + 18), 0.4, DIM)
            text(img, val, (x + 10, y + 42), 0.58, col, 1, FONT_B)
            cv2.rectangle(img, (x + 10, y + 50), (x + 184, y + 54), (70, 50, 35), -1)
            cv2.rectangle(img, (x + 10, y + 50), (x + 10 + int(174 * max(0, min(1, frac))), y + 54), col, -1)

        # per-type efficiency + score
        panel(img, X, 288, 296, 168, "EFFICIENCY PER GARBAGE TYPE")
        spawned, collected = sim.room.spawned_mass(), sim.room.collected_mass()
        for i, k in enumerate(GARBAGE_TYPES):
            y = 316 + i * 27
            eff = collected[k] / spawned[k] if spawned[k] else 0
            text(img, k.replace("_", " "), (X + 10, y + 10), 0.4, WHITE)
            cv2.rectangle(img, (X + 100, y), (X + 250, y + 12), (70, 50, 35), -1)
            cv2.rectangle(img, (X + 100, y), (X + 100 + int(150 * eff), y + 12), GARBAGE_TYPES[k].colour_bgr, -1)
            text(img, f"{eff * 100:3.0f}%", (X + 254, y + 11), 0.38, DIM)

        panel(img, X + 304, 288, 296, 168, "ATOMQUEST SCORE (LIVE PROJECTION)")
        text(img, f"{card.total:5.1f}", (X + 316, 352), 1.5, CYAN, 2, FONT_B)
        text(img, "/ 100", (X + 440, 352), 0.6, DIM)
        names = {"completion_time": "time", "efficiency": "eff.", "autonomy": "auto",
                 "battery": "batt", "aesthetics": "aesth", "container": "bin", "cost": "cost"}
        for i, (k, v) in enumerate(card.parts.items()):
            x = X + 314 + (i % 4) * 70
            y = 378 + (i // 4) * 36
            text(img, names[k], (x, y), 0.34, DIM)
            text(img, f"{v:4.1f}/{WEIGHTS[k]}", (x, y + 15), 0.38, WHITE)

        # SLAM inset
        panel(img, X, 464, 196, 196, "ROBOT MAP (BELIEF)")
        g = sim.mission.grid
        inflated = g.inflated_mask(sim.mission.clearance)
        m = np.zeros((g.ny, g.nx, 3), np.uint8)
        m[:] = (30, 20, 14)
        m[g.observed] = (70, 55, 35)
        m[inflated & g.observed] = (90, 40, 100)
        m[g.occupied_mask()] = (200, 70, 255)
        m[sim.mission.coverage.cleaned & ~inflated] = (120, 110, 20)
        m = cv2.resize(m[::-1], (172, 172), interpolation=cv2.INTER_NEAREST)
        e = sim.odom.pose
        rx, ry = int(e.x / g.res * 172 / g.nx), int(172 - e.y / g.res * 172 / g.ny)
        cv2.circle(m, (rx, ry), 4, CYAN, -1, AA)
        img[480:652, X + 12:X + 184] = m

        # event log
        panel(img, X + 204, 464, 396, 196, "EVENT LOG")
        evs = sim.mission.events[-8:]
        for i, ev in enumerate(evs):
            col = {"state": CYAN, "vision": MAGENTA, "warn": AMBER}.get(ev.kind, WHITE)
            text(img, f"{ev.t:6.1f}s  {ev.text}"[:56], (X + 214, 492 + i * 21), 0.38, col)

    def _draw_timebar(self, img):
        sim = self.sim
        x0, x1, y = 660, 1260, 682
        budget = sim.cfg.mission.time_budget_s
        cv2.rectangle(img, (x0, y), (x1, y + 14), (60, 40, 25), -1)
        hist = sim.mission.fsm.history
        start = sim.mission.start_t or 0.0
        segs = []
        for i, tr in enumerate(hist):
            t0 = tr.t - start
            t1 = (hist[i + 1].t - start) if i + 1 < len(hist) else sim.mission.elapsed
            segs.append((t0, t1, tr.dst.value))
        for t0, t1, st in segs:
            a = x0 + int((x1 - x0) * min(1, t0 / budget))
            b = x0 + int((x1 - x0) * min(1, t1 / budget))
            cv2.rectangle(img, (a, y), (max(a + 1, b), y + 14), STATE_COLOURS.get(st, WHITE), -1)
        text(img, "0s", (x0, y + 32), 0.36, DIM)
        text(img, f"{int(budget)}s (5 min limit)", (x1 - 120, y + 32), 0.36, DIM)
        text(img, "mission timeline", (x0 + 250, y + 32), 0.36, DIM)

    def _banner(self, img, s: str):
        ov = img.copy()
        cv2.rectangle(ov, (20, 680), (640, 714), (20, 20, 20), -1)
        cv2.addWeighted(ov, 0.8, img, 0.2, 0, img)
        cv2.rectangle(img, (20, 680), (640, 714), CYAN, 1, AA)
        text(img, s, (32, 703), 0.52, CYAN, 1, FONT_B)

    # ------------------------------------------------------------ report card
    def report(self, result) -> np.ndarray:
        img = self.render()
        ov = img.copy()
        cv2.rectangle(ov, (120, 90), (1160, 660), (12, 8, 5), -1)
        cv2.addWeighted(ov, 0.88, img, 0.12, 0, img)
        panel(img, 120, 90, 1040, 570)
        text(img, "MISSION REPORT - CHOTU AUTONOMOUS RUN", (150, 140), 0.9, CYAN, 2, FONT_B)
        ok = result.docked
        text(img, "RETURNED TO DOCK" if ok else "INCOMPLETE - NOT DOCKED", (150, 178), 0.65, GREEN if ok else RED, 1, FONT_B)
        rows = [
            ("Completion time", f"{result.elapsed_s:.1f} s  (limit 300 s)"),
            ("Area coverage", f"{result.coverage * 100:.1f} %"),
            ("Debris collected", f"{sum(result.collected_g.values()):.1f} / {sum(result.spawned_g.values()):.1f} g"),
            ("Collisions / cable incidents", f"{result.collisions} / {result.cable_incidents}"),
            ("Stuck recoveries / replans", f"{result.recoveries} / {result.replans}"),
            ("Energy used", f"{result.energy_wh:.2f} Wh  (avg {result.avg_power_w:.1f} W)"),
            ("Adaptive suction saving", f"{result.eco_energy_saving_pct:.1f} % vs. constant max"),
            ("Dock alignment error", f"{result.final_dock_error_m * 100:.1f} cm"),
        ]
        for i, (k, v) in enumerate(rows):
            text(img, k, (150, 228 + i * 34), 0.55, DIM)
            text(img, v, (450, 228 + i * 34), 0.6, WHITE, 1, FONT_B)
        text(img, "ATOMQUEST RUBRIC (projected)", (760, 228), 0.55, CYAN)
        for i, (k, v) in enumerate(result.score["parts"].items()):
            y = 256 + i * 34
            text(img, k.replace("_", " "), (760, y + 12), 0.45, DIM)
            cv2.rectangle(img, (900, y), (1080, y + 14), (60, 40, 25), -1)
            cv2.rectangle(img, (900, y), (900 + int(180 * v / WEIGHTS[k]), y + 14), CYAN, -1)
            text(img, f"{v:.1f}/{WEIGHTS[k]}", (1088, y + 12), 0.42, WHITE)
        text(img, f"TOTAL {result.score['total']:.1f} / 100", (760, 520), 1.0, GREEN, 2, FONT_B)
        text(img, "Per-type efficiency: " + "  ".join(f"{k.replace('_', ' ')} {v * 100:.0f}%"
                                                     for k, v in result.efficiency_by_type.items()),
             (150, 600), 0.48, WHITE)
        text(img, "Same chotu_core autonomy code runs on the Raspberry Pi 4 via ROS 2 (mission_manager_node).",
             (150, 632), 0.45, DIM)
        return img


class FleetRenderer:
    """2 x 2 (or N) tiled dashboard - one CHOTU per room, shared fleet KPIs."""

    def __init__(self, sims: List, cols: int = 2):
        self.sims = sims
        self.cols = cols
        self.rows = int(math.ceil(len(sims) / cols))
        self.tw = W // cols
        self.th = (H - 60) // self.rows
        self.frame_no = 0

    def render(self) -> np.ndarray:
        img = np.zeros((H, W, 3), np.uint8)
        img[:] = BG
        cv2.rectangle(img, (0, 0), (W, 56), (30, 18, 10), -1)
        cv2.line(img, (0, 56), (W, 56), CYAN, 1, AA)
        text(img, "CHOTU FLEET OPS // MULTI-ROOM SCALABILITY DEMO", (20, 36), 0.75, CYAN, 2, FONT_B)
        docked = sum(1 for s in self.sims if s.mission.state == MissionState.DOCKED)
        cov = np.mean([s.truth_cov.coverage_ratio(s.cleanable) for s in self.sims])
        kg = sum(sum(s.room.collected_mass().values()) for s in self.sims)
        t = max(s.mission.elapsed for s in self.sims)
        text(img, f"robots {len(self.sims)} | docked {docked} | mean coverage {cov * 100:4.1f}% | debris {kg:5.1f} g | T+{t:5.1f}s",
             (720, 36), 0.45, WHITE)
        for i, sim in enumerate(self.sims):
            r, c = divmod(i, self.cols)
            x, y = c * self.tw, 60 + r * self.th
            self._tile(img, sim, x + 6, y + 4, self.tw - 12, self.th - 8, i)
        self.frame_no += 1
        return img

    def _tile(self, img, sim, x, y, w, h, idx):
        panel(img, x, y, w, h, f"CHOTU-{idx + 1:02d}  room #{sim.seed}")
        size = h - 34
        sc = size / max(sim.room.width, sim.room.height)
        ox, oy = x + 10, y + 26

        def px(px_, py_):
            return int(ox + px_ * sc), int(oy + size - py_ * sc)
        cv2.rectangle(img, px(0, 0), px(sim.room.width, sim.room.height), (30, 20, 14), -1)
        roi = img[oy:oy + size, ox:ox + size]
        cov = sim.truth_cov.cleaned[::-1].astype(np.uint8) * 255
        cov = cv2.resize(cov, (roi.shape[1], roi.shape[0]), interpolation=cv2.INTER_NEAREST) > 0
        roi[cov] = (110, 90, 15)
        cv2.rectangle(img, px(0, 0), px(sim.room.width, sim.room.height), CYAN, 1, AA)
        for ob in sim.room.obstacles:
            for shape, p in ob.footprint():
                if shape == "circle":
                    cv2.circle(img, px(p[0], p[1]), max(1, int(p[2] * sc)), (200, 180, 150), -1, AA)
                else:
                    cx, cy, rw, rh, a = p
                    box = cv2.boxPoints(((0, 0), (rw, rh), math.degrees(a)))
                    cv2.fillPoly(img, [np.array([px(cx + bx, cy + by) for bx, by in box], np.int32)], (200, 180, 150))
        for cab in sim.room.cables:
            cv2.polylines(img, [np.array([px(a, b) for a, b in cab.points], np.int32)], False, MAGENTA, 2, AA)
        for g in sim.room.garbage:
            if not g.collected:
                cv2.circle(img, px(g.x, g.y), 1, GARBAGE_TYPES[g.kind].colour_bgr, -1)
        p = sim.true_pose
        c = px(p.x, p.y)
        cv2.circle(img, c, int(sim.cfg.robot.radius * sc), CYAN, 2, AA)
        cv2.line(img, c, (int(c[0] + 10 * math.cos(p.theta)), int(c[1] - 10 * math.sin(p.theta))), WHITE, 2, AA)
        sx = ox + size + 14
        st = sim.mission.state.value
        rows = [("STATE", st.replace("_", " "), STATE_COLOURS.get(st, WHITE)),
                ("COVERAGE", f"{sim.truth_cov.coverage_ratio(sim.cleanable) * 100:4.1f} %", CYAN),
                ("DEBRIS", f"{sum(sim.room.collected_mass().values()):4.1f} g", GREEN),
                ("BATTERY", f"{sim.battery.soc * 100:4.1f} %", AMBER),
                ("COLLISIONS", f"{sim.collisions}", WHITE),
                ("T", f"{sim.mission.elapsed:5.1f} s", WHITE)]
        for i, (k, v, col) in enumerate(rows):
            text(img, k, (sx, y + 50 + i * 40), 0.38, DIM)
            text(img, v, (sx, y + 68 + i * 40), 0.5, col, 1, FONT_B)
