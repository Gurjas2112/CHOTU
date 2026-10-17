#!/usr/bin/env python3
"""CHOTU simulation CLI.

Examples
--------
  python bot_simulation/run_simulation.py                     # one room, live window
  python bot_simulation/run_simulation.py --headless --seed 7 # metrics only
  python bot_simulation/run_simulation.py --benchmark 20      # 20 random rooms
  python bot_simulation/run_simulation.py --fleet 4           # 4 robots, 4 rooms
  python bot_simulation/run_simulation.py --no-vision         # ablation: camera off
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

from chotu_sim import Simulation  # noqa: E402


def run_single(args) -> int:
    sim = Simulation(args.seed, vision=not args.no_vision, noise=not args.no_noise)
    renderer = None
    if not args.headless:
        import cv2
        from chotu_sim.renderer import HudRenderer
        renderer = HudRenderer(sim)
        cv2.namedWindow("CHOTU digital twin", cv2.WINDOW_NORMAL)
    t0 = time.time()
    while sim.step():
        if renderer is not None and int(sim.t / sim.dt) % args.speed == 0:
            import cv2
            cv2.imshow("CHOTU digital twin", renderer.render())
            if cv2.waitKey(1) & 0xFF in (27, ord("q")):
                break
    result = sim.result()
    if renderer is not None:
        import cv2
        cv2.imshow("CHOTU digital twin", renderer.report(result))
        print("Press any key in the window to exit")
        cv2.waitKey(0)
        cv2.destroyAllWindows()
    print(json.dumps(asdict(result), indent=2))
    print(f"wall-clock {time.time() - t0:.1f}s")
    if args.json:
        with open(args.json, "w") as f:
            json.dump(asdict(result), f, indent=2)
    return 0 if result.docked else 1


def run_benchmark(args) -> int:
    rows = []
    for seed in range(args.seed, args.seed + args.benchmark):
        r = Simulation(seed, vision=not args.no_vision, noise=not args.no_noise).run()
        rows.append(r)
        print(f"room {seed:4d} | docked {str(r.docked):5s} | {r.elapsed_s:6.1f}s | coverage {r.coverage * 100:5.1f}% "
              f"| collisions {r.collisions:2d} | cable {r.cable_incidents} | score {r.score['total']:5.1f}")
    n = len(rows)
    summary = {
        "rooms": n,
        "dock_success_rate": sum(r.docked for r in rows) / n,
        "mean_time_s": round(sum(r.elapsed_s for r in rows) / n, 1),
        "mean_coverage": round(sum(r.coverage for r in rows) / n, 4),
        "mean_collisions": round(sum(r.collisions for r in rows) / n, 2),
        "total_cable_incidents": sum(r.cable_incidents for r in rows),
        "mean_score": round(sum(r.score["total"] for r in rows) / n, 1),
    }
    print(json.dumps(summary, indent=2))
    if args.json:
        with open(args.json, "w") as f:
            json.dump({"summary": summary, "runs": [asdict(r) for r in rows]}, f, indent=2)
    return 0 if summary["dock_success_rate"] == 1.0 else 1


def run_fleet(args) -> int:
    import cv2
    from chotu_sim.renderer import FleetRenderer
    sims = [Simulation(args.seed + i) for i in range(args.fleet)]
    fr = FleetRenderer(sims, cols=2 if args.fleet <= 4 else 3)
    if not args.headless:
        cv2.namedWindow("CHOTU fleet", cv2.WINDOW_NORMAL)
    while any([s.step() for s in sims]):
        if not args.headless and int(sims[0].t / sims[0].dt) % args.speed == 0:
            cv2.imshow("CHOTU fleet", fr.render())
            if cv2.waitKey(1) & 0xFF in (27, ord("q")):
                break
    for s in sims:
        r = s.result()
        print(f"room {s.seed}: docked={r.docked} coverage={r.coverage:.3f} score={r.score['total']}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=2025, help="random room layout seed")
    ap.add_argument("--headless", action="store_true", help="no window")
    ap.add_argument("--speed", type=int, default=2, help="render every N control ticks")
    ap.add_argument("--benchmark", type=int, default=0, help="run N rooms and summarise")
    ap.add_argument("--fleet", type=int, default=0, help="run N robots in N rooms")
    ap.add_argument("--no-vision", action="store_true", help="disable the AI camera (ablation)")
    ap.add_argument("--no-noise", action="store_true", help="ideal sensors/odometry")
    ap.add_argument("--json", help="write results to this JSON file")
    args = ap.parse_args()
    if args.benchmark:
        return run_benchmark(args)
    if args.fleet:
        return run_fleet(args)
    return run_single(args)


if __name__ == "__main__":
    sys.exit(main())
