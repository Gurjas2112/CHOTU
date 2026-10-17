#!/usr/bin/env python3
"""Record a full CHOTU mission in Gazebo (runs inside the chotu/dev Docker image).

Subscribes to the overhead observer camera of `atomquest_room.sdf`, the robot's
odometry, planned path and `/chotu/status`, and writes
  * chotu_gazebo_full_mission.mp4  - full length, 1x sim-time (10 fps)
  * NN_<state>.png                 - one flow-wise screenshot per mission phase
  * gazebo_mission_metrics.json    - final status

Started by run_gazebo_recording.sh; stops when the robot reports DOCKED.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
from typing import List, Optional, Tuple

import cv2
import numpy as np
import rclpy
from nav_msgs.msg import Odometry, Path
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Image

from chotu_interfaces.msg import CleaningStatus

W, H, CAM = 1280, 720, 720
ROOM_C = 1.524            # camera above the room centre
CAM_H = 4.2
HFOV = 0.76
CYAN, MAG, AMBER, GREEN, WHITE, DIM = (255, 229, 0), (200, 70, 255), (0, 190, 255), (120, 255, 90), (238, 238, 238), (150, 130, 115)
STATE_COL = {"UNDOCK": (255, 160, 60), "SCAN": (255, 90, 190), "COVER": CYAN, "SPOT_CLEAN": GREEN,
             "STUCK_RECOVERY": (90, 80, 255), "RETURN_TO_DOCK": AMBER, "DOCKING": (80, 220, 255), "DOCKED": GREEN}
TITLES = {"UNDOCK": "Undocking from the charging station", "SCAN": "360 deg ultrasonic + ToF mapping scan",
          "COVER": "Boustrophedon coverage with A* detours", "SPOT_CLEAN": "Spot clean & frontier fill",
          "STUCK_RECOVERY": "Stuck recovery (reverse + VFH escape)", "RETURN_TO_DOCK": "A* return to dock",
          "DOCKING": "IR-beacon docking", "DOCKED": "Docked - mission complete"}
FONT = cv2.FONT_HERSHEY_DUPLEX


def txt(img, s, org, sc=0.55, col=WHITE, th=1):
    cv2.putText(img, s, org, FONT, sc, col, th, cv2.LINE_AA)


class Recorder(Node):
    def __init__(self, out: str, max_sim_s: float):
        super().__init__("chotu_gazebo_recorder")
        self.out = out
        self.max_sim_s = max_sim_s
        os.makedirs(out, exist_ok=True)
        self.fx = (CAM / 2) / math.tan(HFOV / 2)
        self.trail: List[Tuple[float, float]] = []
        self.path: List[Tuple[float, float]] = []
        self.status: Optional[CleaningStatus] = None
        self.seen_states: List[Tuple[float, str]] = []
        self.t0: Optional[float] = None
        self.t = 0.0
        self.shots = 0
        self.pending_shot: Optional[Tuple[float, str]] = None
        self.done_at: Optional[float] = None
        self.frames = 0
        ffmpeg = shutil.which("ffmpeg")
        self.proc = subprocess.Popen(
            [ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
             "-r", "10", "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
             "-pix_fmt", "yuv420p", "-movflags", "+faststart", os.path.join(out, "chotu_gazebo_full_mission.mp4")],
            stdin=subprocess.PIPE)
        # reliable: a 1.5 MB image is fragmented by DDS; best-effort drops whole samples
        self.create_subscription(Image, "/overhead/image", self.on_image,
                                 QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE))
        self.create_subscription(Odometry, "/odom", self.on_odom, 20)
        self.create_subscription(Path, "/chotu/plan", self.on_path, 10)
        self.create_subscription(CleaningStatus, "/chotu/status", self.on_status, 10)
        self.get_logger().info(f"recording to {out}")

    # --------------------------------------------------------------- inputs
    def on_odom(self, m: Odometry):
        p = m.pose.pose.position
        if not self.trail or math.hypot(p.x - self.trail[-1][0], p.y - self.trail[-1][1]) > 0.01:
            self.trail.append((p.x, p.y))

    def on_path(self, m: Path):
        self.path = [(ps.pose.position.x, ps.pose.position.y) for ps in m.poses]

    def on_status(self, m: CleaningStatus):
        self.status = m
        if not self.seen_states or self.seen_states[-1][1] != m.state:
            self.seen_states.append((self.t, m.state))
            if m.state not in [s for _, s in self.seen_states[:-1]] and m.state != "IDLE":
                # screenshot slightly after entering the phase so the action is visible
                self.pending_shot = (self.t + (0.5 if m.state == "DOCKED" else 2.0), m.state)
        if m.state == "DOCKED" and self.done_at is None:
            self.done_at = self.t

    # --------------------------------------------------------------- frames
    def px(self, x: float, y: float) -> Tuple[int, int]:
        return (int(CAM / 2 + self.fx * (x - ROOM_C) / CAM_H), int(CAM / 2 - self.fx * (y - ROOM_C) / CAM_H))

    def on_image(self, m: Image):
        stamp = m.header.stamp.sec + m.header.stamp.nanosec * 1e-9
        if self.t0 is None:
            self.t0 = stamp
        self.t = stamp - self.t0
        buf = np.frombuffer(m.data, np.uint8).reshape(m.height, m.width, -1)
        cam = cv2.cvtColor(buf[:, :, :3], cv2.COLOR_RGB2BGR) if m.encoding.startswith("rgb") else buf[:, :, :3].copy()
        cam = cv2.resize(cam, (CAM, CAM))
        frame = self.compose(cam)
        self.proc.stdin.write(frame.tobytes())
        self.frames += 1
        if self.pending_shot and self.t >= self.pending_shot[0]:
            self.shots += 1
            name = f"{self.shots:02d}_{self.pending_shot[1].lower()}.png"
            cv2.imwrite(os.path.join(self.out, name), frame)
            self.get_logger().info(f"screenshot {name}")
            self.pending_shot = None
        if (self.done_at is not None and self.t > self.done_at + 3.0) or self.t > self.max_sim_s:
            self.finish()

    def compose(self, cam: np.ndarray) -> np.ndarray:
        img = np.zeros((H, W, 3), np.uint8)
        img[:] = (22, 13, 9)
        if len(self.trail) > 1:
            cv2.polylines(cam, [np.array([self.px(*p) for p in self.trail], np.int32)], False, CYAN, 2, cv2.LINE_AA)
        if self.path:
            pts = [self.px(*p) for p in self.path]
            for a, b in zip(pts, pts[1:]):
                cv2.line(cam, a, b, AMBER, 1, cv2.LINE_AA)
            cv2.circle(cam, pts[-1], 6, AMBER, 1, cv2.LINE_AA)
        img[:, :CAM] = cam
        cv2.rectangle(img, (0, 0), (CAM - 1, H - 1), CYAN, 1)
        txt(img, "GAZEBO FORTRESS  |  overhead observer camera", (12, 24), 0.5, CYAN)
        X = CAM + 20
        txt(img, "CHOTU // GAZEBO MISSION", (X, 40), 0.75, CYAN, 2)
        txt(img, "ROS 2 Humble  -  real mission_manager_node", (X, 66), 0.45, DIM)
        st = self.status
        state = st.state if st else "IDLE"
        col = STATE_COL.get(state, WHITE)
        cv2.rectangle(img, (X, 86), (W - 20, 124), col, 1)
        txt(img, state.replace("_", " "), (X + 12, 113), 0.7, col, 1)
        txt(img, TITLES.get(state, "Waiting for /chotu/start_mission"), (X, 150), 0.5, WHITE)
        rows = [("SIM TIME", f"{self.t:6.1f} s  (limit 300 s)"),
                ("TIME LEFT", f"{st.time_left_s:6.1f} s" if st else "-"),
                ("COVERAGE (robot est.)", f"{st.coverage_estimate * 100:5.1f} %" if st else "-"),
                ("WAYPOINTS", f"{st.waypoints_done}/{st.waypoints_total}  skipped {st.waypoints_skipped}" if st else "-"),
                ("SUCTION", f"{st.suction_mode} {st.suction_duty * 100:3.0f} %" if st else "-"),
                ("SAFETY LAYER", st.safety if st else "-"),
                ("RECOVERIES / REPLANS", f"{st.recoveries} / {st.replans}" if st else "-")]
        for i, (k, v) in enumerate(rows):
            y = 190 + i * 46
            txt(img, k, (X, y), 0.42, DIM)
            txt(img, v, (X, y + 22), 0.6, WHITE)
        txt(img, "LAST EVENT", (X, 530), 0.42, DIM)
        txt(img, (st.last_event if st else "")[:44], (X, 552), 0.48, MAG)
        # state timeline
        x0, x1, y = X, W - 20, 600
        cv2.rectangle(img, (x0, y), (x1, y + 14), (60, 40, 25), -1)
        for k, (ts, s) in enumerate(self.seen_states):
            te = self.seen_states[k + 1][0] if k + 1 < len(self.seen_states) else self.t
            a = x0 + int((x1 - x0) * min(1, ts / 300.0))
            b = x0 + int((x1 - x0) * min(1, te / 300.0))
            cv2.rectangle(img, (a, y), (max(a + 1, b), y + 14), STATE_COL.get(s, DIM), -1)
        txt(img, "mission timeline (0 - 300 s)", (x0, y + 34), 0.4, DIM)
        txt(img, "AtomQuest 2025 | Team Hack O' Giants | demo world", (X, 690), 0.42, DIM)
        return img

    def finish(self):
        if self.proc:
            self.proc.stdin.close()
            self.proc.wait()
            self.proc = None
            st = self.status
            metrics = dict(sim_time_s=round(self.t, 1), frames=self.frames, screenshots=self.shots,
                           docked=bool(st and st.state == "DOCKED"),
                           final_state=st.state if st else None,
                           coverage_estimate=round(st.coverage_estimate, 4) if st else None,
                           waypoints_done=st.waypoints_done if st else None,
                           waypoints_total=st.waypoints_total if st else None,
                           recoveries=st.recoveries if st else None,
                           states=[dict(t=round(t, 1), state=s) for t, s in self.seen_states])
            with open(os.path.join(self.out, "gazebo_mission_metrics.json"), "w") as f:
                json.dump(metrics, f, indent=2)
            self.get_logger().info(f"finished: {metrics}")
        raise SystemExit(0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/workspace/bot_simulation/gazebo_recording")
    ap.add_argument("--max-sim-s", type=float, default=340.0)
    args = ap.parse_args()
    rclpy.init()
    node = Recorder(args.out, args.max_sim_s)
    try:
        rclpy.spin(node)
    except SystemExit:
        pass
    finally:
        if node.proc:                      # interrupted: still close the MP4 cleanly
            node.proc.stdin.close()
            node.proc.wait()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
