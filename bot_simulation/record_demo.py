#!/usr/bin/env python3
"""Record the CHOTU demo package into ``simulation_screenshot_screen_recording/``.

Outputs
  01_..._NN_*.png                flow-wise screenshots (one per mission phase)
  chotu_full_mission_recording.mp4   full-length, real-time (1x) single-room run
  chotu_fleet_4_rooms_timelapse.mp4  4 robots / 4 rooms, 3x time-lapse
  benchmark_*.png / *.json       10-room benchmark + AI-vision ablation
  mission_metrics.json           metrics of the recorded run

Usage:  python bot_simulation/record_demo.py [--seed 2025] [--out DIR] [--quick]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import cv2  # noqa: E402

from chotu_sim import Simulation  # noqa: E402
from chotu_sim.renderer import FleetRenderer, HudRenderer  # noqa: E402
from chotu_sim.video import VideoWriter  # noqa: E402

DEFAULT_OUT = os.path.join(HERE, "simulation_screenshot_screen_recording")


class ShotPlanner:
    """Captures one screenshot the first time each mission milestone happens."""

    def __init__(self, out_dir: str):
        self.out = out_dir
        self.taken = set()
        self.n = 0
        self.pending = {}   # key -> (capture_at_t, filename, banner)
        self.files = []

    def schedule(self, key, t_capture, name, banner):
        if key not in self.taken and key not in self.pending:
            self.pending[key] = (t_capture, name, banner)

    def maybe_capture(self, t, renderer: HudRenderer):
        for key, (tc, name, banner) in sorted(self.pending.items(), key=lambda kv: kv[1][0]):
            if t >= tc:
                self.n += 1
                fn = os.path.join(self.out, f"{self.n:02d}_{name}.png")
                cv2.imwrite(fn, renderer.render(extra_banner=f"STEP {self.n} - {banner}"))
                self.files.append(os.path.basename(fn))
                self.taken.add(key)
                del self.pending[key]


def record_single(seed: int, out: str, fps: int) -> dict:
    sim = Simulation(seed)
    hud = HudRenderer(sim)
    video = VideoWriter(os.path.join(out, "chotu_full_mission_recording.mp4"), fps)
    shots = ShotPlanner(out)
    shots.schedule("start", 0.0, "mission_start_docked", "Robot on dock, mission start")
    first = {}
    stride = max(1, int(round((1 / sim.dt) / fps)))
    intro = hud.render(extra_banner="CHOTU - autonomous AtomQuest cleaning run (real-time)")
    for _ in range(fps * 2):
        video.write(intro)
    shots.maybe_capture(0.0, hud)
    tick = 0
    while True:
        alive = sim.step()
        tick += 1
        m = sim.mission
        st = m.state.value
        t = m.elapsed
        if st not in first:
            first[st] = t
            plan = {
                "UNDOCK": (t + 1.2, "undocking", "Undocking (encoder + gyro odometry)"),
                "SCAN": (t + 2.5, "mapping_scan_360", "360 deg ToF/ultrasonic mapping scan"),
                "COVER": (t + 25, "boustrophedon_coverage", "Boustrophedon zig-zag coverage"),
                "STUCK_RECOVERY": (t + 0.3, "stuck_recovery", "Stuck recovery: reverse + VFH escape turn"),
                "SPOT_CLEAN": (t + 3, "spot_clean_frontier_fill", "Spot clean & frontier fill of missed pockets"),
                "RETURN_TO_DOCK": (t + 2, "return_to_dock_astar", "A* return-to-dock (time-budget aware)"),
                "DOCKING": (t + 1.5, "ir_beacon_docking", "IR-beacon docking"),
            }
            if st in plan:
                shots.schedule(st, *plan[st])
        if t > 40 and sim.last_cmd.safety in ("slow", "blocked") and "avoid" not in shots.taken:
            shots.schedule("avoid", t, "obstacle_avoidance_reactive", "Reactive obstacle avoidance (3x HC-SR04 + VL53L0X)")
        if any(e.kind == "vision" for e in m.events):
            shots.schedule("vision", t + 0.6, "ai_vision_cable_keepout", "YOLOv8n 'AVOID' cable -> keep-out zone in map")
        if m.suction.mode == "BOOST" and t > 20:
            shots.schedule("boost", t, "adaptive_suction_boost", "Debris ahead: adaptive suction BOOST")
        shots.schedule("mid", 150.0, "coverage_progress_150s", "Coverage progress at T+150 s")
        shots.maybe_capture(t, hud)
        if tick % stride == 0 or not alive:
            video.write(hud.render())
        if not alive:
            break
    result = sim.result()
    report = hud.report(result)
    for _ in range(fps * 6):
        video.write(report)
    video.close()
    shots.n += 1
    fn = os.path.join(out, f"{shots.n:02d}_mission_report.png")
    cv2.imwrite(fn, report)
    shots.files.append(os.path.basename(fn))
    return {"result": asdict(result), "screenshots": shots.files, "state_entry_times": first}


def record_fleet(seed: int, n: int, out: str, fps: int, speedup: int = 3) -> dict:
    sims = [Simulation(seed + 100 + i) for i in range(n)]
    fr = FleetRenderer(sims, cols=2)
    video = VideoWriter(os.path.join(out, f"chotu_fleet_{n}_rooms_timelapse.mp4"), fps)
    stride = max(1, int(round((1 / sims[0].dt) / fps)) * speedup)
    tick, mid_done = 0, False
    while True:
        alive = [s.step() for s in sims]
        tick += 1
        if tick % stride == 0:
            frame = fr.render()
            video.write(frame)
            if not mid_done and sims[0].mission.elapsed > 120:
                cv2.imwrite(os.path.join(out, "fleet_dashboard_4_robots.png"), frame)
                mid_done = True
        if not any(alive):
            break
    final = fr.render()
    for _ in range(fps * 4):
        video.write(final)
    cv2.imwrite(os.path.join(out, "fleet_dashboard_final.png"), final)
    video.close()
    return {"rooms": [asdict(s.result()) for s in sims]}


def benchmark(seed: int, n: int, out: str) -> dict:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    rows = {True: [], False: []}
    for vision in (True, False):
        for s in range(seed, seed + n):
            rows[vision].append(Simulation(s, vision=vision).run())
    v, nv = rows[True], rows[False]
    seeds = list(range(seed, seed + n))
    plt.style.use("dark_background")
    fig, ax = plt.subplots(1, 3, figsize=(16, 5))
    ax[0].bar([str(s) for s in seeds], [r.coverage * 100 for r in v], color="#00e5ff")
    ax[0].axhline(sum(r.coverage for r in v) / n * 100, color="#ffbe00", ls="--", label="mean")
    ax[0].set_title("Coverage per random room (%)"); ax[0].set_xlabel("room seed"); ax[0].legend()
    ax[1].bar([str(s) for s in seeds], [r.elapsed_s for r in v], color="#5aff78")
    ax[1].axhline(300, color="#ff5a5a", ls="--", label="5 min limit")
    ax[1].set_title("Dock-to-dock time (s)"); ax[1].set_xlabel("room seed"); ax[1].legend()
    labels = ["AtomQuest score", "Cable incidents", "Collisions"]
    with_v = [sum(r.score["total"] for r in v) / n, sum(r.cable_incidents for r in v), sum(r.collisions for r in v)]
    without = [sum(r.score["total"] for r in nv) / n, sum(r.cable_incidents for r in nv), sum(r.collisions for r in nv)]
    x = range(len(labels))
    ax[2].bar([i - 0.2 for i in x], with_v, 0.4, label="YOLO suck/avoid ON", color="#00e5ff")
    ax[2].bar([i + 0.2 for i in x], without, 0.4, label="camera OFF", color="#c846ff")
    for i in x:
        ax[2].text(i - 0.2, with_v[i] + 0.5, f"{with_v[i]:.1f}", ha="center")
        ax[2].text(i + 0.2, without[i] + 0.5, f"{without[i]:.1f}", ha="center")
    ax[2].set_xticks(list(x)); ax[2].set_xticklabels(labels)
    ax[2].set_title(f"AI-vision ablation ({n} rooms)"); ax[2].legend()
    fig.suptitle("CHOTU autonomy benchmark - randomised AtomQuest rooms", color="#00e5ff")
    fig.tight_layout()
    fig.savefig(os.path.join(out, "benchmark_10_rooms_and_vision_ablation.png"), dpi=110)
    plt.close(fig)

    def summ(rs):
        return {"dock_success_rate": sum(r.docked for r in rs) / n,
                "mean_coverage": round(sum(r.coverage for r in rs) / n, 4),
                "mean_time_s": round(sum(r.elapsed_s for r in rs) / n, 1),
                "mean_score": round(sum(r.score["total"] for r in rs) / n, 1),
                "total_collisions": sum(r.collisions for r in rs),
                "total_cable_incidents": sum(r.cable_incidents for r in rs),
                "mean_efficiency_by_type": {k: round(sum(r.efficiency_by_type[k] for r in rs) / n, 3)
                                            for k in rs[0].efficiency_by_type}}
    return {"vision_on": summ(v), "vision_off": summ(nv), "seeds": seeds}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=2025)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--fps", type=int, default=20)
    ap.add_argument("--fleet", type=int, default=4)
    ap.add_argument("--bench", type=int, default=10)
    ap.add_argument("--quick", action="store_true", help="skip fleet + benchmark")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    t0 = time.time()
    metrics = {"single_run": record_single(args.seed, args.out, args.fps)}
    print(f"single run recorded in {time.time() - t0:.0f}s")
    if not args.quick:
        metrics["fleet"] = record_fleet(args.seed, args.fleet, args.out, args.fps)
        print(f"fleet recorded in {time.time() - t0:.0f}s")
        metrics["benchmark"] = benchmark(0, args.bench, args.out)
        print(f"benchmark done in {time.time() - t0:.0f}s")
    with open(os.path.join(args.out, "mission_metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2)
    print(json.dumps(metrics["single_run"]["result"]["score"], indent=2))
    print("screenshots:", *metrics["single_run"]["screenshots"], sep="\n  ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
