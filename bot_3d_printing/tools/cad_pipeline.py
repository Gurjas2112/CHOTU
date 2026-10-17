#!/usr/bin/env python3
"""Build -> review -> export -> render pipeline for the CHOTU v3 printed body.

    python bot_3d_printing/tools/cad_pipeline.py            # everything (≈10 min)
    python bot_3d_printing/tools/cad_pipeline.py --no-video # skip the MP4

Outputs (all under bot_3d_printing/):
    stl/<part>.stl                    print-oriented, 0.05 mm tessellation
    step/chotu_v3_assembly.step       full assembly (printed + reference parts)
    step/<part>.step                  per printed part
    dxf/mdf_base_template.dxf         1:1 cutting / drilling template for the 6 mm MDF disc
    dxf/mdf_base_holes.csv            hole table
    previews/<part>_4view.png         4-view preview of every printed part
    flow/NN_*.png                     flow-wise design checkpoints (article workflow)
    video/chotu_v3_cad_walkthrough.mp4
    review_report.md                  automatic FDM design-review checklist
    print_plan.md                     plates, filament, print time
"""
from __future__ import annotations

import argparse
import math
import os
import sys
from typing import Dict, List, Sequence, Tuple

import cv2
import numpy as np
import trimesh

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "cad"))

import cadquery as cq  # noqa: E402
from chotu_v3 import P, Part, build, print_orientation  # noqa: E402
from video_writer import VideoWriter  # noqa: E402

W, H = 1280, 720
BG_TOP, BG_BOT = np.array([34, 20, 12]), np.array([12, 8, 5])          # BGR navy gradient (HUD theme)
CYAN_BGR = (255, 229, 0)
DIM = (150, 130, 115)
FONT = cv2.FONT_HERSHEY_DUPLEX
PETG_DENSITY = 1.27   # g/cm^3


# ================================================================ meshes
def to_mesh(shape: cq.Workplane, tol: float = 0.3) -> trimesh.Trimesh:
    verts, tris = shape.val().tessellate(tol, 0.3)
    v = np.array([(p.x, p.y, p.z) for p in verts], dtype=np.float64)
    m = trimesh.Trimesh(v, np.array(tris, dtype=np.int64), process=True)
    m.merge_vertices()
    return m


# ================================================================ renderer
class Camera:
    def __init__(self, azim: float, elev: float, target, dist: float, ortho: bool = False, fov: float = 32.0):
        self.target = np.asarray(target, dtype=float)
        a, e = math.radians(azim), math.radians(elev)
        self.eye = self.target + dist * np.array([math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)])
        f = self.target - self.eye
        f /= np.linalg.norm(f)
        up = np.array([0, 0, 1.0]) if abs(f[2]) < 0.99 else np.array([1.0, 0, 0])
        r = np.cross(f, up)
        r /= np.linalg.norm(r)
        u = np.cross(r, f)
        self.R = np.stack([r, u, -f])          # world -> camera
        self.ortho = ortho
        self.dist = dist
        self.fov = math.radians(fov)

    def project(self, pts: np.ndarray, scale: float, cx: float, cy: float):
        c = (pts - self.eye) @ self.R.T
        depth = -c[..., 2]
        if self.ortho:
            x, y = c[..., 0], c[..., 1]
        else:
            k = 1.0 / (np.maximum(depth, 1e-3) * math.tan(self.fov / 2))
            x, y = c[..., 0] * k * self.dist * math.tan(self.fov / 2), c[..., 1] * k * self.dist * math.tan(self.fov / 2)
        return np.stack([cx + x * scale, cy - y * scale], -1), depth


def background(w=W, h=H) -> np.ndarray:
    t = np.linspace(0, 1, h)[:, None, None]
    img = (BG_TOP * (1 - t) + BG_BOT * t).astype(np.uint8)
    return np.repeat(img, w, axis=1)


def render(items: Sequence[Tuple[trimesh.Trimesh, Tuple[float, float, float]]], cam: Camera,
           size=(W, H), scale: float = 1.0, center=None, img=None, floor: bool = True) -> np.ndarray:
    w, h = size
    img = background(w, h) if img is None else img
    cx, cy = (w / 2, h / 2) if center is None else center
    tris, cols = [], []
    for m, col in items:
        tris.append(m.triangles)
        cols.append(np.tile(np.array(col)[None, :], (len(m.triangles), 1)))
    if not tris:
        return img
    T = np.concatenate(tris)
    C = np.concatenate(cols)
    n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
    nl = np.linalg.norm(n, axis=1, keepdims=True)
    n = n / np.maximum(nl, 1e-12)
    view = cam.eye[None, :] - T.mean(1)
    facing = (n * view).sum(1) > 0
    T, C, n = T[facing], C[facing], n[facing]
    if floor and not cam.ortho:
        g = np.linspace(-300, 300, 13)
        for v in g:
            for a, b in (((v, -300, 0), (v, 300, 0)), ((-300, v, 0), (300, v, 0))):
                pa, _ = cam.project(np.array([a, b], float), scale, cx, cy)
                cv2.line(img, tuple(int(q) for q in pa[0]), tuple(int(q) for q in pa[1]), (60, 42, 28), 1, cv2.LINE_AA)
    L1 = cam.R.T @ np.array([-0.4, 0.6, 0.7])
    L1 /= np.linalg.norm(L1)
    L2 = np.array([0.3, -0.5, 0.8])
    L2 /= np.linalg.norm(L2)
    shade = 0.32 + 0.55 * np.clip(n @ L1, 0, 1) + 0.18 * np.clip(n @ L2, 0, 1)
    rgb = np.clip(C * shade[:, None], 0, 1)
    p2, depth = cam.project(T, scale, cx, cy)
    order = np.argsort(-depth.mean(1))
    p2 = np.round(p2[order] * 4).astype(np.int32)          # 2 bits sub-pixel precision
    bgr = (rgb[order][:, ::-1] * 255).astype(np.uint8)
    for poly, c in zip(p2, bgr):
        cv2.fillPoly(img, [poly], (int(c[0]), int(c[1]), int(c[2])), cv2.LINE_AA, shift=2)
    return img


def fit_scale(meshes, cam: Camera, size, margin=0.82):
    corners = np.concatenate([np.array([[mm.bounds[i][0], mm.bounds[j][1], mm.bounds[k][2]]
                                        for i in (0, 1) for j in (0, 1) for k in (0, 1)]) for mm, _ in meshes])
    p, _ = cam.project(corners, 1.0, 0, 0)
    span = np.maximum(p.max(0) - p.min(0), 1e-6)
    s = margin * min(size[0] / span[0], size[1] / span[1])
    mid = (p.max(0) + p.min(0)) / 2
    return s, (size[0] / 2 - mid[0] * s, size[1] / 2 - mid[1] * s)


def label(img, text, org, scale=0.6, col=(238, 238, 238), thick=1):
    cv2.putText(img, text, org, FONT, scale, col, thick, cv2.LINE_AA)


def banner(img, title, sub=""):
    cv2.rectangle(img, (0, 0), (img.shape[1], 54), (30, 18, 10), -1)
    cv2.line(img, (0, 54), (img.shape[1], 54), CYAN_BGR, 1, cv2.LINE_AA)
    label(img, title, (20, 36), 0.8, CYAN_BGR, 2)
    if sub:
        label(img, sub, (img.shape[1] - 12 - 9 * len(sub), 34), 0.5, DIM)


VIEWS = [("ISO", 35, 28, False), ("FRONT", 0, 0, True), ("TOP", 0, 89.9, True), ("SIDE", 90, 0, True)]


def four_view(items, title, sub="", target=None) -> np.ndarray:
    img = background()
    banner(img, title, sub)
    allpts = np.concatenate([m.vertices for m, _ in items])
    tgt = allpts.mean(0) if target is None else target
    rad = np.linalg.norm(allpts.max(0) - allpts.min(0))
    cells = [(0, 58), (640, 58), (0, 389), (640, 389)]
    for (name, az, el, ortho), (ox, oy) in zip(VIEWS, cells):
        cam = Camera(az, el, tgt, rad * 2.4, ortho=ortho)
        tile = background(640, 331)
        s, c = fit_scale(items, cam, (640, 331), 0.78)
        render(items, cam, (640, 331), s, c, tile, floor=False)
        cv2.rectangle(tile, (0, 0), (639, 330), (90, 60, 35), 1)
        label(tile, name, (12, 24), 0.55, CYAN_BGR)
        img[oy:oy + 331, ox:ox + 640] = tile
    return img


# ================================================================ review
def review(part: Part, mesh: trimesh.Trimesh) -> Dict:
    bb = mesh.bounds
    ext = bb[1] - bb[0]
    fn = mesh.face_normals
    area = mesh.area_faces
    zmin = bb[0][2]
    centers = mesh.triangles_center
    bottom = area[(fn[:, 2] < -0.99) & (centers[:, 2] < zmin + 0.05)].sum()
    above = centers[:, 2] > zmin + 0.3
    steep = (fn[:, 2] < -math.cos(math.radians(45))) & (fn[:, 2] > -0.999) & above   # needs support
    ceiling = (fn[:, 2] <= -0.999) & above                                           # bridges (spans < 20 mm by design)
    overhang = area[steep].sum()
    bridges = area[ceiling].sum()
    vol = mesh.volume / 1000.0                                   # cm^3 (solid)
    shell_frac = min(1.0, 0.35 + 6.0 / max(5.0, min(ext)))       # walls + 20 % gyroid estimate
    grams = vol * PETG_DENSITY * shell_frac
    checks = {
        "watertight": bool(mesh.is_watertight),
        "fits 220x220x250 bed": bool(ext[0] <= P["bed"] and ext[1] <= P["bed"] and ext[2] <= 250),
        "flat bottom >= 50 mm2": bool(bottom >= 50.0),
        "min wall >= 1.2 mm (params)": bool(min(P["shell_wall"], P["bin_wall"], P["lid_t"]) >= P["min_wall"]),
    }
    return dict(name=part.name, qty=part.qty, ext=ext, bottom=bottom, overhang=overhang, bridges=bridges, vol=vol,
                grams=grams, hours=grams / 11.0, checks=checks, ok=all(checks.values()),
                support=overhang > 150.0, note=part.note, material=part.material)


# ================================================================ main
def main() -> int:
    # one pipeline at a time: two concurrent runs would corrupt the shared outputs
    lock = os.path.join(ROOT, ".cad_pipeline.lock")
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        print(f"another cad_pipeline run is active (delete {lock} if it crashed)")
        return 1
    os.close(fd)
    try:
        return _run()
    finally:
        os.remove(lock)


def _run() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-video", action="store_true")
    ap.add_argument("--frames", type=int, default=420)
    args = ap.parse_args()
    for d in ("stl", "step", "dxf", "previews", "flow", "video"):
        os.makedirs(os.path.join(ROOT, d), exist_ok=True)

    parts3, base = build(3)
    print(f"built {len(parts3)} parts")
    base_mesh = to_mesh(base, 0.5)
    mesh_cache: Dict[str, trimesh.Trimesh] = {p.name: to_mesh(p.shape, 0.5) for p in parts3}
    WOOD = (0.76, 0.62, 0.42)

    # ---------------------------------------------------------------- exports
    reviews = []
    assy = cq.Assembly(name="chotu_v3")
    assy.add(base, name="mdf_base", color=cq.Color(*WOOD))
    for p in parts3:
        assy.add(p.shape, name=p.name, color=cq.Color(*p.colour))
        if not p.printed:
            continue
        po = print_orientation(p)
        cq.exporters.export(po, os.path.join(ROOT, "stl", f"{p.name}.stl"), tolerance=0.05, angularTolerance=0.1)
        cq.exporters.export(po, os.path.join(ROOT, "step", f"{p.name}.step"))
        pm = trimesh.load(os.path.join(ROOT, "stl", f"{p.name}.stl"))
        reviews.append(review(p, pm))
        img = four_view([(to_mesh(po, 0.4), p.colour)], f"CHOTU v3 // {p.name}",
                        f"{pm.extents[0]:.0f} x {pm.extents[1]:.0f} x {pm.extents[2]:.0f} mm  (print orientation)")
        cv2.imwrite(os.path.join(ROOT, "previews", f"{p.name}_4view.png"), img)
    try:
        assy.save(os.path.join(ROOT, "step", "chotu_v3_assembly.step"))
    except Exception:
        assy.export(os.path.join(ROOT, "step", "chotu_v3_assembly.step"))
    section = base.section(P["base_z"] + P["base_t"] / 2)
    cq.exporters.export(section, os.path.join(ROOT, "dxf", "mdf_base_template.dxf"))
    screws = sorted({(round(x, 1), round(y, 1)) for p in parts3 for x, y in p.screw_pts})
    with open(os.path.join(ROOT, "dxf", "mdf_base_holes.csv"), "w") as f:
        f.write("x_mm,y_mm,diameter_mm,purpose\n")
        for (x, y) in screws:
            owner = next(p.name for p in parts3 if any(abs(px - x) < 0.1 and abs(py - y) < 0.1 for px, py in p.screw_pts))
            f.write(f"{x},{y},{P['m3']},M3 for {owner}\n")
        f.write(f"{P['nozzle_x']},0,{2 * P['duct_r'] + 1},suction duct\n")

    # ---------------------------------------------------------------- review report
    with open(os.path.join(ROOT, "review_report.md"), "w", encoding="utf-8") as f:
        f.write("# Automatic FDM design review - CHOTU v3\n\n")
        f.write("Generated by `tools/cad_pipeline.py` after every build (checklist from the Towards AI "
                "*cad-skill* workflow: watertight, bed fit, flat bottom, wall thickness, overhangs).\n\n")
        f.write("| Part | Qty | Size (mm) | Watertight | Bed fit | Flat bottom (mm²) | Overhang >45° (mm²) | Supports | Est. PETG (g) | Est. time (h) | Result |\n")
        f.write("|---|---|---|---|---|---|---|---|---|---|---|\n")
        for r in reviews:
            e = r["ext"]
            c = r["checks"]
            f.write(f"| {r['name']} | {r['qty']} | {e[0]:.0f}×{e[1]:.0f}×{e[2]:.0f} | {'✔' if c['watertight'] else '✘'} | "
                    f"{'✔' if c['fits 220x220x250 bed'] else '✘'} | {r['bottom']:.0f} | {r['overhang']:.0f} | {r['bridges']:.0f} | "
                    f"{'yes (see note)' if r['support'] else 'none'} | {r['grams']:.0f} | {r['hours']:.1f} | "
                    f"{'PASS' if r['ok'] else 'FAIL'} |\n")
        tg = sum(r["grams"] * r["qty"] for r in reviews)
        th = sum(r["hours"] * r["qty"] for r in reviews)
        f.write(f"\n**Totals:** {len(reviews)} printed parts, ≈ {tg:.0f} g PETG (≈ ₹{tg * 1.0:.0f} at ₹1/g), "
                f"≈ {th:.0f} h on a 0.4 mm nozzle at 0.2 mm layers.\n")
        f.write(f"\nAll parts pass: **{all(r['ok'] for r in reviews)}**. *Bridges* are flat ceilings designed to "
                "span less than 20 mm (printable without supports). *Steep overhang* is surface between 45 deg and "
                "horizontal: on `bumper_front` it is the upper half of the six 16.6 mm transducer holes and the ToF "
                "window, which print cleanly without supports at 0.2 mm layers.\n")
    print(f"review: {sum(r['ok'] for r in reviews)}/{len(reviews)} parts pass")

    # ---------------------------------------------------------------- flow-wise checkpoints
    built = {3: (parts3, base)}          # CadQuery builds are slow: once per phase, not once per frame

    def scene(phase: int, explode: float = 0.0, refs: bool = True, with_dock: bool = False):
        if phase not in built:
            built[phase] = build(phase)
        parts, _ = built[phase]
        items = [(base_mesh, WOOD)]
        for p in parts:
            if (not refs and not p.printed) or (p.name == "dock_station" and not with_dock):
                continue
            m = mesh_cache[p.name].copy()
            if explode:
                m.apply_translation(np.array(p.explode) * explode)
            items.append((m, p.colour))
        return items

    target = np.array([0, 0, 110.0])
    flows = [
        ("01_requirements_envelope", "STEP 1 - Requirements: AtomQuest envelope 457 x 457 x 305 mm", "envelope"),
        ("02_phase1_base_shape", "STEP 2 - Phase 1 base shape: MDF disc + 4-part shell + 4 lid tiles", 1),
        ("03_phase2_features_drive_cleaning", "STEP 3 - Phase 2 features: drive, nozzle, bin, sensors, deck", 2),
        ("04_phase3_cleanup_quick_release", "STEP 4 - Phase 3 clean-up: magnetic hatch, skid, chamfers, dock", 3),
        ("05_exploded_assembly", "STEP 5 - Exploded assembly (service & repair order)", "exploded"),
        ("06_final_assembly_with_dock", "STEP 6 - Final assembly docked on the charging station", "final"),
    ]
    for fname, title, what in flows:
        if what == "envelope":
            env = trimesh.creation.box(extents=(457.2, 457.2, 304.8))
            env.apply_translation((0, 0, 152.4))
            items = scene(3)
            cam = Camera(35, 24, target, 1500)
            s, c = fit_scale([(env, (0, 0, 0))], cam, (W, H - 60), 0.86)
            img = background()
            render(items, cam, (W, H), s, (c[0], c[1] + 40), img)
            edges = env.vertices[np.array([[0, 1], [0, 2], [0, 4], [1, 3], [1, 5], [2, 3], [2, 6], [3, 7], [4, 5], [4, 6], [5, 7], [6, 7]])]
            for a, b2 in edges:
                pa, _ = cam.project(np.array([a, b2]), s, c[0], c[1] + 40)
                cv2.line(img, tuple(int(v) for v in pa[0]), tuple(int(v) for v in pa[1]), (255, 120, 255), 1, cv2.LINE_AA)
            banner(img, title)
            label(img, "CHOTU v3: 306 mm dia x 230 mm high (fits 1.5 x 1.5 x 1 ft)", (20, 690), 0.6, CYAN_BGR)
        elif what in ("exploded", "final"):
            items = scene(3, explode=1.0 if what == "exploded" else 0.0, with_dock=what == "final")
            cam = Camera(35 if what == "exploded" else 25, 24, target if what == "exploded" else np.array([-80, 0, 90]), 1500)
            s, c = fit_scale(items, cam, (W, H - 60), 0.88)
            img = background()
            render(items, cam, (W, H), s, (c[0], c[1] + 30), img)
            banner(img, title)
        else:
            items = scene(what, refs=(what >= 2))
            img = four_view(items, title, f"phase {what} of 3", target=target)
        cv2.imwrite(os.path.join(ROOT, "flow", f"{fname}.png"), img)
        print("flow", fname)
    # print-plate layout (220 x 220 beds)
    plate_img = print_plates(parts3)
    cv2.imwrite(os.path.join(ROOT, "flow", "07_print_plates_220mm_bed.png"), plate_img)

    # ---------------------------------------------------------------- video
    if not args.no_video:
        final_mp4 = os.path.join(ROOT, "video", "chotu_v3_cad_walkthrough.mp4")
        part_mp4 = final_mp4 + ".part.mp4"       # encode aside, publish atomically when complete
        vw = VideoWriter(part_mp4, 30, (W, H))
        n = args.frames
        for i in range(n):
            t = i / (n - 1)
            if t < 0.3:                      # build-up by phase
                ph = 1 if t < 0.1 else (2 if t < 0.2 else 3)
                items, ex, title = scene(ph), 0.0, f"Phase {ph} of 3 - {['base shape', 'features', 'clean-up'][ph - 1]}"
            elif t < 0.55:                   # explode
                k = (t - 0.3) / 0.25
                items, ex, title = scene(3, explode=0.5 - 0.5 * math.cos(math.pi * k)), 1, "Exploded assembly"
            elif t < 0.7:                    # collapse
                k = (t - 0.55) / 0.15
                items, ex, title = scene(3, explode=0.5 + 0.5 * math.cos(math.pi * k)), 1, "Re-assembly"
            else:
                items, ex, title = scene(3, with_dock=True), 0, "Docked on the charging station"
            az = 35 + 360 * t
            cam = Camera(az, 24, target, 1500)
            img = background()
            render(items, cam, (W, H), 1.25, (W / 2, H / 2 + 120), img)
            banner(img, "CHOTU v3 // 3D-printable re-engineered body (CadQuery)", title)
            label(img, f"{len(reviews)} printed parts in PETG on a 220 mm bed  |  MDF base reused  |  "
                       "magnetic quick-release bin",
                  (20, 700), 0.55, DIM)
            vw.write(img)
            if i % 60 == 0:
                print(f"video frame {i}/{n}")
        vw.close()
        os.replace(part_mp4, final_mp4)
    print("done")
    return 0


def print_plates(parts: List[Part]) -> np.ndarray:
    """Greedy shelf packing of print-oriented footprints onto 220 x 220 plates."""
    items = []
    for p in parts:
        if not p.printed:
            continue
        bb = print_orientation(p).val().BoundingBox()
        items.append((p.name, bb.xlen, bb.ylen, p.colour))
    items.sort(key=lambda it: -it[2] * it[1])
    plates: List[List[Tuple[str, float, float, float, float, tuple]]] = []
    for name, w, h, col in items:
        placed = False
        for pl in plates:
            for x in range(0, 221 - int(w), 5):
                for y in range(0, 221 - int(h), 5):
                    if all(x + w + 4 <= ox or ox + ow + 4 <= x or y + h + 4 <= oy or oy + oh + 4 <= y
                           for _, ox, oy, ow, oh, _ in pl):
                        pl.append((name, x, y, w, h, col))
                        placed = True
                        break
                if placed:
                    break
            if placed:
                break
        if not placed:
            plates.append([(name, 0, 0, w, h, col)])
    img = background()
    banner(img, "STEP 7 - Print plan: plates on a 220 x 220 mm bed", f"{len(plates)} plates")
    cols = 5
    cell = 240
    for k, pl in enumerate(plates):
        ox, oy = 20 + (k % cols) * (cell + 8), 70 + (k // cols) * (cell + 40)
        sc = 200 / 220
        cv2.rectangle(img, (ox, oy), (ox + int(220 * sc), oy + int(220 * sc)), (90, 60, 35), 1)
        label(img, f"plate {k + 1}", (ox, oy - 6), 0.45, CYAN_BGR)
        for name, x, y, w, h, col in pl:
            p0 = (ox + int(x * sc), oy + int(y * sc))
            p1 = (ox + int((x + w) * sc), oy + int((y + h) * sc))
            bgr = tuple(int(c * 255) for c in col[::-1])
            cv2.rectangle(img, p0, p1, bgr, -1)
            cv2.rectangle(img, p0, p1, (20, 20, 20), 1)
            label(img, name[:14], (p0[0] + 2, p0[1] + 12), 0.3, (20, 20, 20))
    return img


if __name__ == "__main__":
    sys.exit(main())
