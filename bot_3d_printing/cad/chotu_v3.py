"""CHOTU v3 - parametric, 3D-printable re-engineered body (CadQuery).

Workflow follows "I Taught Claude to Design 3D-Printable Parts" (Towards AI,
2026) / flowful-ai/cad-skill: every dimension is a named parameter, parts are
built in three checkpoints (base shape -> features -> clean-up), previewed
from four views and self-reviewed against an FDM checklist before export.

Frame: x forward, y left, z up, floor z = 0, robot centre at (0, 0). mm.
The Ø300 base disc is the team's existing 6 mm MDF board (cost sheet) - it is
exported as a DXF drilling/cutting template, not printed. Every printed part
fits a 220 x 220 mm bed (Ender-3 class) in its export orientation.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import cadquery as cq

# =============================================================== parameters
P: Dict[str, float] = dict(
    # envelope (AtomQuest: <= 457 x 457 x 305 mm)
    body_r=150.0,            # MDF base radius (Ø300)
    base_t=6.0,              # MDF thickness
    base_z=38.0,             # underside height above floor (wheel axle 32.5)
    shell_wall=3.0,          # bumper/shell wall (>= 2 mm FDM rule)
    shell_gap=0.5,           # clearance shell <-> MDF edge
    shell_top_z=204.0,       # shell height (top of bumper ring)
    lid_t=3.0,
    skirt=8.0,               # shell skirt covering the MDF edge
    # drive
    wheel_r=32.5, wheel_w=26.0, wheel_y=130.0,
    well_len=80.0, well_w=34.0,
    motor_len=64.0, motor_w=22.0, motor_h=18.0,
    caster_x=125.0, caster_unit_h=20.0,
    # cleaning
    nozzle_x=60.0, nozzle_span=200.0, nozzle_depth=16.0, nozzle_floor_gap=5.0,
    duct_r=16.0,
    bin_x0=10.0, bin_x1=110.0, bin_w=90.0, bin_h=70.0, bin_wall=2.0, bin_floor=2.5,
    standpipe_h=36.0, clearance=0.3,
    magnet_d=10.2, magnet_t=3.2,          # 10 x 3 mm N52 disc + clearance
    motor_can_r=29.0,                      # Bergmann BAV-60 motor can (measure before printing)
    collar_h=20.0,
    # electronics
    deck_x0=-115.0, deck_x1=-15.0, deck_half_w=80.0, deck_z=84.0, deck_t=3.0,
    standoff_h=6.0,
    pi_holes=(58.0, 49.0), pcb_size=(90.0, 65.0),
    batt=(70.0, 55.0, 20.0),               # BT-65 11.1 V 18650 pack (Bill-2)
    # sensors (angles from +x, deg)
    us_angles=(35.0, 0.0, -35.0), us_z=70.0, us_hole_d=16.6, us_pitch=26.0,
    tof_z=96.0,
    # fasteners / FDM
    m3=3.4, m25=2.7, chamfer=0.6, min_wall=1.2,
    bed=220.0,
)

# =============================================================== helpers


def box(x0, x1, y0, y1, z0, z1) -> cq.Workplane:
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    z0, z1 = sorted((z0, z1))
    return cq.Workplane("XY").box(x1 - x0, y1 - y0, z1 - z0, centered=False).translate((x0, y0, z0))


def cyl(r, z0, h, x=0.0, y=0.0) -> cq.Workplane:
    return cq.Workplane("XY").circle(r).extrude(h).translate((x, y, z0))


def ring(r_out, r_in, z0, h, x=0.0, y=0.0) -> cq.Workplane:
    return cq.Workplane("XY").circle(r_out).circle(r_in).extrude(h).translate((x, y, z0))


def radial_cyl(r_start, length, ang_deg, z, d) -> cq.Workplane:
    a = math.radians(ang_deg)
    s = cq.Solid.makeCylinder(d / 2, length, cq.Vector(r_start * math.cos(a), r_start * math.sin(a), z),
                              cq.Vector(math.cos(a), math.sin(a), 0))
    return cq.Workplane("XY").add(s)


def radial_box(r_start, length, ang_deg, z, w, h) -> cq.Workplane:
    """Rectangular window through a curved wall (w tangential, h vertical)."""
    a = math.radians(ang_deg)
    b = box(0, length, -w / 2, w / 2, -h / 2, h / 2)
    return b.rotate((0, 0, 0), (0, 0, 1), ang_deg).translate((r_start * math.cos(a), r_start * math.sin(a), z))


def wedge(r, a0, a1, z0, h) -> cq.Workplane:
    pts = [(0, 0)] + [(r * math.cos(math.radians(a0 + (a1 - a0) * i / 24)),
                       r * math.sin(math.radians(a0 + (a1 - a0) * i / 24))) for i in range(25)]
    return cq.Workplane("XY").polyline(pts).close().extrude(h).translate((0, 0, z0))


def m3_holes(wp: cq.Workplane, pts, z0, h, d=None) -> cq.Workplane:
    for x, y in pts:
        wp = wp.cut(cyl((d or P["m3"]) / 2, z0 - 1, h + 2, x, y))
    return wp


def chamfer_bottom(wp: cq.Workplane) -> cq.Workplane:
    """FDM rule: chamfer (not fillet) the bed edges -> no elephant foot, no supports."""
    try:
        return wp.faces("<Z").edges().chamfer(P["chamfer"])
    except Exception:
        return wp


# =============================================================== parts
@dataclass
class Part:
    name: str
    shape: cq.Workplane
    colour: Tuple[float, float, float]
    printed: bool = True
    flip: bool = False                     # export upside-down (flat face on the bed)
    qty: int = 1
    material: str = "PETG"
    phase: int = 2                          # checkpoint where the part first appears
    explode: Tuple[float, float, float] = (0, 0, 0)
    screw_pts: List[Tuple[float, float]] = field(default_factory=list)  # holes drilled in the MDF
    note: str = ""


CYAN = (0.0, 0.85, 0.95)
MAG = (0.85, 0.25, 0.95)
GREY = (0.55, 0.57, 0.62)
DARK = (0.22, 0.24, 0.30)
WOOD = (0.76, 0.62, 0.42)
AMBER = (1.0, 0.72, 0.1)
WHITE = (0.92, 0.93, 0.95)
GREEN = (0.35, 0.85, 0.45)


def mdf_base(screws: List[Tuple[float, float]]) -> cq.Workplane:
    R, t, z = P["body_r"], P["base_t"], P["base_z"]
    b = cyl(R, z, t)
    for sy in (1, -1):    # wheel wells
        b = b.cut(box(-P["well_len"] / 2, P["well_len"] / 2,
                      sy * P["wheel_y"] - P["well_w"] / 2, sy * P["wheel_y"] + P["well_w"] / 2, z - 1, z + t + 1))
    b = b.cut(cyl(P["duct_r"] + 0.5, z - 1, t + 2, P["nozzle_x"], 0))                 # suction duct
    b = b.cut(box(-20, -10, -30, 30, z - 1, z + t + 1))                                # cable pass to deck
    for x, y in screws:
        b = b.cut(cyl(P["m3"] / 2, z - 1, t + 2, x, y))
    return b


def bumper_segment(a0: float, a1: float, kind: str) -> Part:
    R_in = P["body_r"] + P["shell_gap"]
    R_out = R_in + P["shell_wall"]
    z0 = P["base_z"] - P["skirt"]                                   # skirt hides the MDF edge
    h = P["shell_top_z"] - z0
    seg = ring(R_out, R_in, z0, h).intersect(wedge(R_out + 5, a0, a1, z0 - 1, h + 2))
    # internal ledge the segment hangs on (sits on the MDF top surface)
    zt = P["base_z"] + P["base_t"]
    screws = []
    for k in (0.3, 0.7):
        a = math.radians(a0 + (a1 - a0) * k)
        tab = box(-8, 8, 0, 14, zt, zt + 4).rotate((0, 0, 0), (0, 0, 1), math.degrees(a) - 90)
        tab = tab.translate(((R_in - 13) * math.cos(a), (R_in - 13) * math.sin(a), 0))
        seg = seg.union(tab.intersect(cyl(R_in + 1, zt, 4)))
        sx, sy = (R_in - 7) * math.cos(a), (R_in - 7) * math.sin(a)
        seg = seg.cut(cyl(P["m3"] / 2, zt - 1, 6, sx, sy))
        screws.append((sx, sy))
    # top ledge for the lid tiles
    seg = seg.union(ring(R_in, R_in - 10, P["shell_top_z"] - P["lid_t"] - 6, 6).intersect(
        wedge(R_out + 5, a0 + 2, a1 - 2, 0, 300)))
    if kind == "front":
        for ang in P["us_angles"]:   # 3 x HC-SR04 transducer holes
            a = math.radians(ang)
            for s in (-1, 1):
                off = s * P["us_pitch"] / 2
                da = math.degrees(off / R_in)
                seg = seg.cut(radial_cyl(R_in - 10, 25, ang + da, P["us_z"], P["us_hole_d"]))
        seg = seg.cut(radial_box(R_in - 10, 25, 0.0, P["tof_z"], 12.0, 7.0))           # VL53L0X window
    if kind == "rear":
        seg = seg.cut(radial_cyl(R_in - 10, 25, 180.0, 70.0, 6.0))                       # TSOP38238 dock IR
        for da in (-12, 12):                                                             # charging contacts
            seg = seg.cut(radial_box(R_in - 10, 25, 180.0 + da, 52.0, 12.0, 6.0))
    seg = chamfer_bottom(seg)
    mid = math.radians((a0 + a1) / 2)
    return Part(f"bumper_{kind}", seg, CYAN if kind == "front" else WHITE, phase=1,
                explode=(60 * math.cos(mid), 60 * math.sin(mid), 0), screw_pts=screws,
                note="Shell segment; sensors behind windows" if kind in ("front", "rear") else "Shell segment")


def lid_tile(q: int) -> Part:
    """One quarter of the top lid (4 tiles -> each fits a 220 mm bed)."""
    a0 = 90.0 * q
    R = P["body_r"] + P["shell_gap"] - 0.3
    z = P["shell_top_z"] - P["lid_t"]
    t = cyl(R, z, P["lid_t"]).intersect(wedge(R + 2, a0, a0 + 90, z - 1, 10))
    t = t.cut(box(P["bin_x0"] - 5, P["bin_x1"] + 5, -P["bin_w"] / 2 - 5, P["bin_w"] / 2 + 5, z - 1, z + 10))  # hatch
    # tongue under the joint lines -> tiles key into each other
    # two M3 holes per tile into heat-set inserts in the shell's top ledge
    for k in (0.25, 0.75):
        a = math.radians(a0 + 90 * k)
        t = t.cut(cyl(P["m3"] / 2, z - 1, P["lid_t"] + 2, (R - 6) * math.cos(a), (R - 6) * math.sin(a)))
    if q == 1:                                 # rear-left tile: embossed logo
        try:
            logo = (cq.Workplane("XY").workplane(offset=P["shell_top_z"])
                    .center(-75, 60).text("CHOTU", 16, 0.8, kind="bold"))
            t = t.union(logo)
        except Exception:
            pass
    if q in (1, 2):                            # rear tiles: electronics vent slots
        for i in range(5):
            t = t.cut(box(-110 + i * 16, -102 + i * 16, -6 if q == 2 else 6, 50 if q == 1 else -50, z - 1, z + 10)
                      .intersect(box(-130, -20, -60, 60, z - 1, z + 10)))
    mid = math.radians(a0 + 45)
    return Part(f"lid_tile_{q + 1}", t, DARK if q != 1 else CYAN, phase=1,
                explode=(50 * math.cos(mid), 50 * math.sin(mid), 120))


def hatch() -> Part:
    c = P["clearance"]
    z = P["shell_top_z"] - P["lid_t"]
    x0, x1 = P["bin_x0"] - 5 + c, P["bin_x1"] + 5 - c
    y = P["bin_w"] / 2 + 5 - c
    h = box(x0, x1, -y, y, z, z + P["lid_t"])
    h = h.union(box(x0 - 4, x1 + 4, -y - 4, y + 4, z + P["lid_t"], z + P["lid_t"] + 2))   # overlapping rim
    for i in range(6):                                                             # motor exhaust grille
        h = h.cut(box(x0 + 18 + i * 13, x0 + 24 + i * 13, -30, 30, z - 1, z + 10))
    h = h.cut(box(x1 - 6, x1 + 5, -14, 14, z + 1.0, z + 10))                      # finger pull
    for x, yy in ((x0 + 8, y - 8), (x0 + 8, -y + 8), (x1 - 8, y - 8), (x1 - 8, -y + 8)):
        h = h.cut(cyl(P["magnet_d"] / 2, z - 0.01, P["magnet_t"], x, yy))          # magnet latch pockets
    return Part("bin_hatch", h, MAG, flip=True, phase=3, explode=(0, 0, 200),
                note="Magnetic quick-release hatch over the dust bin")


def dust_bin() -> Part:
    x0, x1, w, hgt = P["bin_x0"], P["bin_x1"], P["bin_w"], P["bin_h"]
    z0 = P["base_z"] + P["base_t"]
    t, f = P["bin_wall"], P["bin_floor"]
    b = box(x0, x1, -w / 2, w / 2, z0, z0 + hgt)
    b = b.cut(box(x0 + t, x1 - t, -w / 2 + t, w / 2 - t, z0 + f, z0 + hgt + 1))
    b = b.cut(cyl(P["duct_r"] - 1.5, z0 - 1, f + 2, P["nozzle_x"], 0))            # inlet from nozzle
    b = b.union(ring(P["duct_r"] + 0.5, P["duct_r"] - 1.5, z0 + f, P["standpipe_h"], P["nozzle_x"], 0))  # anti-spill standpipe
    for xx in (x0 + 22, x1 - 22):
        for s in (1, -1):
            hole = cq.Solid.makeCylinder(P["magnet_d"] / 2, P["magnet_t"],
                                         cq.Vector(xx, s * (w / 2 + 0.01), z0 + hgt / 2), cq.Vector(0, -s, 0))
            b = b.cut(cq.Workplane("XY").add(hole))
    b = b.cut(cyl(10, z0 + hgt - 6, 10, x1, 0))                                    # finger notch at the front rim
    b = chamfer_bottom(b)
    vol_ml = (x1 - x0 - 2 * t) * (w - 2 * t) * (hgt - f) / 1000.0
    return Part("dust_bin", b, (0.75, 0.9, 1.0), phase=2, explode=(0, 0, 150),
                note=f"Transparent PETG, ~{vol_ml:.0f} mL, lifts straight out through the hatch")


def bin_lid() -> Part:
    x0, x1, w = P["bin_x0"], P["bin_x1"], P["bin_w"]
    t, c = P["bin_wall"], P["clearance"]
    z = P["base_z"] + P["base_t"] + P["bin_h"]
    lid = box(x0, x1, -w / 2, w / 2, z, z + 3)
    lid = lid.union(box(x0 + t + c, x1 - t - c, -w / 2 + t + c, w / 2 - t - c, z - 5, z)
                    .cut(box(x0 + t + c + 1.6, x1 - t - c - 1.6, -w / 2 + t + c + 1.6, w / 2 - t - c - 1.6, z - 6, z)))
    cx = (x0 + x1) / 2
    for i in range(-3, 4):                                                          # pre-filter grid (Ø3)
        for j in range(-3, 4):
            if math.hypot(i * 7, j * 7) < P["motor_can_r"] - 4:
                lid = lid.cut(cyl(1.5, z - 1, 5, cx + i * 7, j * 7))
    lid = lid.union(ring(P["motor_can_r"] + 2.3, P["motor_can_r"] + P["clearance"], z + 3, P["collar_h"], cx, 0))
    for s in (1, -1):                                                               # strap slots for the motor
        lid = lid.cut(box(cx - 3, cx + 3, s * (P["motor_can_r"] - 1) - 4, s * (P["motor_can_r"] + 4), z + 8, z + 14))
    return Part("bin_filter_lid", lid, (0.6, 0.8, 0.95), phase=2, explode=(0, 0, 175),
                note="HEPA/mesh pre-filter + Bergmann motor collar (XT30 quick plug on the motor lead)")


def bin_cradle() -> Part:
    x0, x1, w = P["bin_x0"], P["bin_x1"], P["bin_w"]
    c = P["clearance"]
    z0 = P["base_z"] + P["base_t"]
    h = 40.0
    rail_in = w / 2 + c
    cr = box(x0 - 4, x1, rail_in, rail_in + 4, z0, z0 + h)
    cr = cr.union(box(x0 - 4, x1, -rail_in - 4, -rail_in, z0, z0 + h))
    cr = cr.union(box(x0 - 4 - c - 0.01, x0 - c, -rail_in - 4, rail_in + 4, z0, z0 + h))   # rear stop
    screws = []
    for xx in (x0 + 15, x1 - 15):
        for s in (1, -1):
            cr = cr.union(box(xx - 7, xx + 7, s * (rail_in + 4) - (7 if s < 0 else 0),
                              s * (rail_in + 4) + (7 if s > 0 else 0), z0, z0 + 4))
            cr = cr.cut(cyl(P["m3"] / 2, z0 - 1, 6, xx, s * (rail_in + 7.5)))
            screws.append((xx, s * (rail_in + 7.5)))
    for xx in (x0 + 22, x1 - 22):                                                   # magnets facing the bin's
        for s in (1, -1):
            hole = cq.Solid.makeCylinder(P["magnet_d"] / 2, P["magnet_t"],
                                         cq.Vector(xx, s * (rail_in - 0.01), z0 + 35), cq.Vector(0, s, 0))
            cr = cr.cut(cq.Workplane("XY").add(hole))
    return Part("bin_cradle", chamfer_bottom(cr), GREY, phase=2, explode=(0, 0, 40), screw_pts=screws)


def suction_nozzle() -> Part:
    x, d, span = P["nozzle_x"], P["nozzle_depth"], P["nozzle_span"]
    zb, gap = P["base_z"], P["nozzle_floor_gap"]
    x0, x1 = x - d / 2, x + d / 2
    n = box(x0, x1, -span / 2, span / 2, gap, zb - 4)
    n = n.cut(box(x0 + 2, x1 - 2, -span / 2 + 2, span / 2 - 2, gap - 1, zb - 6))   # 12 mm bridge (< 20 mm)
    n = n.union(cyl(P["duct_r"], zb - 4, 4 + P["base_t"], x, 0))
    screws = []
    for s in (1, -1):        # full-height screw ribs on the rear face (no cantilever), inside the 200 mm span
        yy = s * (span / 2 - 14)
        n = n.union(box(x0 - 12, x0, yy - 8, yy + 8, gap, zb))
        n = n.cut(cyl(P["m3"] / 2 - 0.4, zb - 10, 11, x0 - 6, yy))       # self-tapping M3 from above
        screws.append((x0 - 6, yy))
    n = n.cut(cyl(P["duct_r"] - 2, zb - 7, 8 + P["base_t"], x, 0))      # bore cut last -> clean manifold
    return Part("suction_nozzle", n, AMBER, phase=2, explode=(0, 0, -70), screw_pts=screws,
                note="24 cm-class mouth, 5 mm floor gap; brush fibres glued along the rear lip")


def motor_bracket(side: int) -> Part:
    L, W, H = P["motor_len"], P["motor_w"], P["motor_h"]
    zb = P["base_z"]
    yc = side * (P["wheel_y"] - P["wheel_w"] / 2 - 3 - W / 2)
    x0 = -L / 2 + 10
    c = P["clearance"]
    br = box(x0, x0 + 40, yc - W / 2 - 3, yc + W / 2 + 3, zb - H - 3, zb)
    br = br.cut(box(x0 - 1, x0 + 41, yc - W / 2 - c, yc + W / 2 + c, zb - H - c, zb - 3))
    br = br.union(box(x0 + 10, x0 + 30, yc - W / 2 - 13, yc + W / 2 + 13, zb - 3, zb))
    screws = [(x0 + 20, yc - W / 2 - 8), (x0 + 20, yc + W / 2 + 8)]
    for sx, sy in screws:
        br = br.cut(cyl(P["m3"] / 2, zb - 4, 5, sx, sy))
    hole = cq.Solid.makeCylinder(1.7, W + 10, cq.Vector(x0 + 20, yc - W / 2 - 5, zb - H / 2), cq.Vector(0, 1, 0))
    br = br.cut(cq.Workplane("XY").add(hole))                                       # BO motor through-bolt
    return Part(f"motor_bracket_{'left' if side > 0 else 'right'}", br, GREY, flip=True, phase=2,
                explode=(0, side * 40, -40), screw_pts=screws)


def caster_mount() -> Part:
    x = P["caster_x"]
    h = P["base_z"] - P["caster_unit_h"]
    m = cyl(16, P["caster_unit_h"], h, x, 0)
    for a in (0, 120, 240):
        rx, ry = x + 10 * math.cos(math.radians(a)), 10 * math.sin(math.radians(a))
        m = m.cut(cyl(P["m3"] / 2, P["caster_unit_h"] - 1, h + 2, rx, ry))
    return Part("caster_spacer", chamfer_bottom(m), GREY, phase=2, explode=(0, 0, -60),
                screw_pts=[(x + 10 * math.cos(math.radians(a)), 10 * math.sin(math.radians(a))) for a in (0, 120, 240)])


def rear_skid() -> Part:
    zb = P["base_z"]
    s = cyl(9, 4, zb - 4, -128, 0)
    s = s.faces("<Z").chamfer(4.0)
    s = s.cut(cyl(P["m3"] / 2, zb - 12, 13, -128, 0))
    return Part("rear_skid", s, GREY, flip=True, phase=3, explode=(0, 0, -60), screw_pts=[(-128, 0)],
                note="Anti-tip skid, 4 mm floor clearance")


def side_brush_mount() -> Part:
    x, y = 100.0, -92.0
    zb = P["base_z"]
    m = box(x - 15, x + 15, y - 15, y + 15, zb - 26, zb)
    m = m.cut(cyl(6.2, zb - 27, 22, x, y))                                         # N20 / 130 brush motor
    m = m.cut(box(x - 12.3, x + 12.3, y - 6.3, y + 6.3, zb - 27, zb - 4))
    pts = [(x - 10, y + 10), (x + 10, y + 10)]
    for px, py in pts:
        m = m.cut(cyl(P["m3"] / 2, zb - 6, 7, px, py))
    return Part("side_brush_mount", m, GREY, flip=True, phase=2, explode=(30, -30, -60), screw_pts=pts)


def cliff_mount(side: int) -> Part:
    x, y = 112.0, side * 72.0
    zb = P["base_z"]
    m = box(x - 8, x + 8, y - 18, y + 18, zb - 22, zb)
    m = m.cut(box(x - 5.3, x + 5.3, y - 15.3, y + 15.3, zb - 23, zb - 3))          # TCRT5000 board pocket
    m = m.cut(cyl(P["m3"] / 2, zb - 4, 5, x, y))
    return Part(f"cliff_mount_{'left' if side > 0 else 'right'}", m, GREY, flip=True, phase=2,
                explode=(30, side * 20, -60), screw_pts=[(x, y)])


def battery_tray() -> Part:
    bx, by, bz = P["batt"]
    z0 = P["base_z"] + P["base_t"]
    x0, x1 = -103.0, -103.0 + bx + 6
    t = box(x0, x1, -by / 2 - 3, by / 2 + 3, z0, z0 + 12)
    t = t.cut(box(x0 + 3, x1 - 3, -by / 2, by / 2, z0 + 2, z0 + 13))
    for xx in (x0 + 15, x1 - 15):                                                    # velcro strap slots
        t = t.cut(box(xx - 10, xx + 10, -by / 2 - 4, by / 2 + 4, z0 + 2, z0 + 5))
    screws = [(x0 + 3 + (bx) / 2, -by / 4), (x0 + 3 + bx / 2, by / 4)]
    for sx, sy in screws:
        t = t.cut(cyl(P["m3"] / 2, z0 - 1, 4, sx, sy))
    return Part("battery_tray", chamfer_bottom(t), GREY, phase=2, explode=(0, 0, 30), screw_pts=screws,
                note="BT-65 11.1 V pack + 3S BMS, 2 velcro straps")


def deck_pillar(i: int, x: float, y: float) -> Part:
    z0 = P["base_z"] + P["base_t"]
    p = cyl(6, z0, P["deck_z"] - z0, x, y).cut(cyl(P["m3"] / 2, z0 - 1, P["deck_z"] - z0 + 2, x, y))
    return Part(f"deck_pillar_{i}", chamfer_bottom(p), GREY, qty=1, phase=2, explode=(0, 0, 60), screw_pts=[(x, y)])


def electronics_deck(pillars) -> Part:
    x0, x1, hw = P["deck_x0"], P["deck_x1"], P["deck_half_w"]
    z, t = P["deck_z"], P["deck_t"]
    d = box(x0, x1, -hw, hw, z, z + t)
    for x, y in pillars:
        d = d.cut(cyl(P["m3"] / 2, z - 1, t + 2, x, y))
    # Raspberry Pi 4 (85 x 56): 56 along x, 85 along y, M2.5 holes 58 x 49
    pi_x0, pi_y0 = x0 + 6, -hw + 4
    hx, hy = P["pi_holes"]
    for i in (0, 1):
        for j in (0, 1):
            px, py = pi_x0 + 3.5 + j * hy, pi_y0 + 3.5 + i * hx
            d = d.union(ring(3.2, P["m25"] / 2, z + t, P["standoff_h"], px, py))
            d = d.cut(cyl(P["m25"] / 2, z - 1, t + 2, px, py))
    # CHOTU carrier PCB (hardware/pcb), 90 x 65, M3 holes 4 mm in from the corners
    pw, ph = P["pcb_size"]
    cx0, cy0 = x0 + 6, hw - ph - 3
    for i in (0, 1):
        for j in (0, 1):
            px, py = cx0 + 4 + i * (pw - 8), cy0 + 4 + j * (ph - 8)
            d = d.union(ring(3.4, P["m3"] / 2, z + t, P["standoff_h"], px, py))
            d = d.cut(cyl(P["m3"] / 2, z - 1, t + 2, px, py))
    d = d.cut(box(x1 - 14, x1 - 4, -30, 30, z - 1, z + t + 1))                     # cable slot
    return Part("electronics_deck", chamfer_bottom(d), DARK, phase=2, explode=(0, 0, 90),
                note="Raspberry Pi 4 + CHOTU carrier PCB on standoffs")


def camera_pod() -> Part:
    z = P["shell_top_z"]
    x0, x1 = 112.0, 138.0
    p = box(x0, x1, -16, 16, z, z + 26)
    cut = box(-14, 14, -13, 13, -1.5, 1.5).rotate((0, 0, 0), (0, 1, 0), 90 - 25)   # Pi cam (25 x 24) slot, 25° down
    p = p.cut(cut.translate((x1 - 8, 0, z + 13)))
    lens = cq.Solid.makeCylinder(4.5, 20, cq.Vector(x1 - 10, 0, z + 13),
                                 cq.Vector(math.cos(math.radians(-25)), 0, math.sin(math.radians(-25))))
    p = p.cut(cq.Workplane("XY").add(lens))
    p = p.cut(box(x0 - 1, x0 + 8, -6, 6, z - 1, z + 3))                             # ribbon slot
    for y in (-10, 10):
        p = p.cut(cyl(P["m3"] / 2, z - 1, 8, x0 + 5, y))
    return Part("camera_pod", chamfer_bottom(p), CYAN, phase=2, explode=(30, 0, 160),
                note="Pi Camera 5 MP, 25° down-tilt for the YOLO suck/avoid model")


def dock() -> Part:
    """Charging dock, placed behind the robot (the robot reverses onto it)."""
    w, dpt, h, t = 200.0, 90.0, 110.0, 2.5
    face = -P["body_r"] - P["shell_gap"] - P["shell_wall"] - 6      # 6 mm gap to the robot's rear
    x0, x1 = face - dpt, face
    d = box(x0, x1, -w / 2, w / 2, 0, h)
    d = d.cut(box(x0 + t, x1 - t, -w / 2 + t, w / 2 - t, -1, h - t))              # open-bottom shell
    led = cq.Solid.makeCylinder(2.6, 10, cq.Vector(x1 - 5, 0, 70), cq.Vector(1, 0, 0))
    d = d.cut(cq.Workplane("XY").add(led))                                          # 38 kHz IR beacon window
    for y in (-30, 30):
        d = d.cut(box(x1 - 4, x1 + 1, y - 6, y + 6, 46, 58))                        # spring contact pads
    d = d.cut(box(x0 - 1, x0 + 4, -10, 10, -1, 14))                                 # DC jack / cable exit
    d = d.union(box(x0 + t, x1 - t, -4, 4, h - 20, h - t))                          # stiffening rib
    return Part("dock_station", d, WHITE, flip=True, phase=3, explode=(-80, 0, 0),
                note="IR beacon (38 kHz LED) + 2 spring contacts, 12.6 V CC/CV charger inside")


# ---------------------------------------------------------- reference (non-printed) parts
def references() -> List[Part]:
    refs = []
    for s in (1, -1):
        w = cq.Solid.makeCylinder(P["wheel_r"], P["wheel_w"], cq.Vector(0, s * P["wheel_y"] - P["wheel_w"] / 2, P["wheel_r"]),
                                  cq.Vector(0, 1, 0))
        refs.append(Part(f"ref_wheel_{s}", cq.Workplane("XY").add(w), (0.12, 0.12, 0.12), printed=False,
                         explode=(0, s * 70, -40)))
        L, W, H = P["motor_len"], P["motor_w"], P["motor_h"]
        yc = s * (P["wheel_y"] - P["wheel_w"] / 2 - 3 - W / 2)
        refs.append(Part(f"ref_bo_motor_{s}", box(-L / 2 + 10, L / 2 + 10, yc - W / 2, yc + W / 2,
                                                  P["base_z"] - H - 0.5, P["base_z"] - 3.5),
                         (0.95, 0.8, 0.1), printed=False, explode=(0, s * 40, -40)))
    z = P["base_z"] + P["base_t"] + P["bin_h"] + 3
    cx = (P["bin_x0"] + P["bin_x1"]) / 2
    refs.append(Part("ref_bergmann_motor", cyl(P["motor_can_r"], z, 70, cx, 0), (0.75, 0.75, 0.78),
                     printed=False, explode=(0, 0, 210)))
    bx, by, bz = P["batt"]
    zb = P["base_z"] + P["base_t"] + 2
    refs.append(Part("ref_battery_bt65", box(-100, -100 + bx, -by / 2, by / 2, zb, zb + bz), (0.2, 0.35, 0.9),
                     printed=False, explode=(0, 0, 30)))
    zd = P["deck_z"] + P["deck_t"] + P["standoff_h"]
    hw = P["deck_half_w"]
    refs.append(Part("ref_raspberry_pi4", box(P["deck_x0"] + 6, P["deck_x0"] + 62, -hw + 4, -hw + 89, zd, zd + 18),
                     (0.1, 0.55, 0.25), printed=False, explode=(0, 0, 90)))
    pw, ph = P["pcb_size"]
    refs.append(Part("ref_carrier_pcb", box(P["deck_x0"] + 6, P["deck_x0"] + 6 + pw, hw - ph - 3, hw - 3, zd, zd + 14),
                     (0.05, 0.35, 0.15), printed=False, explode=(0, 0, 90)))
    refs.append(Part("ref_caster", cyl(13, 0, P["caster_unit_h"], P["caster_x"], 0), (0.3, 0.3, 0.3),
                     printed=False, explode=(0, 0, -60)))
    refs.append(Part("ref_side_brush", cyl(50, 1.0, 1.5, 100.0, -92.0), (0.95, 0.3, 0.3), printed=False,
                     explode=(30, -30, -80)))
    return refs


# ============================================================ build
def build(phase: int = 3) -> Tuple[List[Part], cq.Workplane]:
    """Return (parts visible at this checkpoint, MDF base)."""
    parts: List[Part] = []
    parts += [bumper_segment(-45, 45, "front"), bumper_segment(45, 135, "left"),
              bumper_segment(135, 225, "rear"), bumper_segment(225, 315, "right")]
    parts += [lid_tile(q) for q in range(4)]
    if phase >= 2:
        parts += [suction_nozzle(), dust_bin(), bin_lid(), bin_cradle(),
                  motor_bracket(1), motor_bracket(-1), caster_mount(), side_brush_mount(),
                  cliff_mount(1), cliff_mount(-1), battery_tray(), camera_pod()]
        pillars = [(P["deck_x0"] + 8, -P["deck_half_w"] + 30), (P["deck_x0"] + 8, P["deck_half_w"] - 30),
                   (P["deck_x1"] - 8, -P["deck_half_w"] + 30), (P["deck_x1"] - 8, P["deck_half_w"] - 30)]
        parts += [deck_pillar(i + 1, x, y) for i, (x, y) in enumerate(pillars)]
        parts.append(electronics_deck(pillars))
        parts += references()
    if phase >= 3:
        parts += [hatch(), rear_skid(), dock()]
    screws = [pt for p in parts for pt in p.screw_pts if p.name not in ("camera_pod",)]
    base = mdf_base(screws)
    return parts, base


def print_orientation(p: Part) -> cq.Workplane:
    s = p.shape
    if p.flip:
        s = s.rotate((0, 0, 0), (1, 0, 0), 180)
    bb = s.val().BoundingBox()
    return s.translate((-(bb.xmin + bb.xmax) / 2, -(bb.ymin + bb.ymax) / 2, -bb.zmin))


if __name__ == "__main__":
    parts, base = build(3)
    for p in parts:
        bb = p.shape.val().BoundingBox()
        print(f"{p.name:24s} {'print' if p.printed else 'ref  '} {bb.xlen:6.1f} x {bb.ylen:6.1f} x {bb.zlen:6.1f}")
