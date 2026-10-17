"""Backend <-> robot link.

DemoRobotLink      replays sample_data/telemetry_replay.json for every robot (no hardware).
RosbridgeRobotLink connects to each robot's rosbridge WebSocket (ws://<pi>:9090), subscribes
                   to /chotu/status + /odom and forwards commands as rosbridge service calls.

Both push protocol envelopes (chotu_api.protocol) to in-process subscribers, which the
/ws/v1 WebSocket endpoint fans out to apps and dashboards.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Set, Tuple

from .. import protocol

log = logging.getLogger("chotu_api.robot_link")


class RobotLink(ABC):
    kind = "abstract"

    def __init__(self) -> None:
        self._latest: Dict[str, dict] = {}
        self._online: Dict[str, bool] = {}
        self._subs: Dict[str, Set[asyncio.Queue]] = {}
        self._seq: Dict[str, int] = {}

    # ---- fan-out
    def subscribe(self, robot_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=64)
        self._subs.setdefault(robot_id, set()).add(q)
        return q

    def unsubscribe(self, robot_id: str, q: asyncio.Queue) -> None:
        self._subs.get(robot_id, set()).discard(q)

    def emit(self, robot_id: str, type_: str, data: dict) -> dict:
        self._seq[robot_id] = self._seq.get(robot_id, 0) + 1
        env = protocol.envelope(type_, robot_id, self._seq[robot_id], data)
        for q in list(self._subs.get(robot_id, ())):
            if q.full():                       # slow client: drop its oldest frame, never block the link
                with contextlib.suppress(asyncio.QueueEmpty):
                    q.get_nowait()
            q.put_nowait(env)
        return env

    def _telemetry(self, robot_id: str, data: dict) -> None:
        prev = self._latest.get(robot_id, {}).get("state")
        self._latest[robot_id] = data
        self.emit(robot_id, "telemetry", data)
        if prev is not None and prev != data["state"]:
            self.emit(robot_id, "mission_event", {"from": prev, "to": data["state"], "t": data["t"]})

    def latest(self, robot_id: str) -> Optional[dict]:
        return self._latest.get(robot_id)

    def online(self, robot_id: str) -> bool:
        return self._online.get(robot_id, False)

    # ---- lifecycle + commands
    @abstractmethod
    async def start(self, robots: List[dict]) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    async def send_command(self, robot_id: str, action: str, data: dict) -> Tuple[bool, str, dict]: ...


class DemoRobotLink(RobotLink):
    """Replays the Gazebo mission timeline. Each robot starts at a different offset so a
    fleet dashboard shows four different states at once."""
    kind = "demo"

    def __init__(self, sample_dir: str, speed: float = 1.0) -> None:
        super().__init__()
        with open(os.path.join(sample_dir, "telemetry_replay.json"), encoding="utf-8") as f:
            replay = json.load(f)
        self.frames: List[dict] = replay["frames"]
        self.period = 1.0 / (replay.get("hz", 1) * max(speed, 1e-3))
        self._cursor: Dict[str, int] = {}
        self._tasks: List[asyncio.Task] = []
        self._call = 0

    async def start(self, robots: List[dict]) -> None:
        n = len(self.frames)
        for i, r in enumerate(robots):
            self._cursor[r["id"]] = (i * n // max(len(robots), 1)) % n
            self._online[r["id"]] = True
            self._telemetry(r["id"], self.frames[self._cursor[r["id"]]])
            self._tasks.append(asyncio.create_task(self._run(r["id"])))

    async def _run(self, robot_id: str) -> None:
        while True:
            await asyncio.sleep(self.period)
            self._cursor[robot_id] = (self._cursor[robot_id] + 1) % len(self.frames)
            self._telemetry(robot_id, self.frames[self._cursor[robot_id]])

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await t
        self._tasks.clear()

    async def send_command(self, robot_id, action, data):
        self._call += 1
        msg = protocol.to_rosbridge(action, data, f"demo-{self._call}")
        if robot_id not in self._cursor:
            return False, f"unknown robot {robot_id}", msg
        if action == "start_mission":
            self._cursor[robot_id] = 0
            text = "demo: mission restarted from the dock"
        elif action == "return_to_dock":
            self._cursor[robot_id] = next(i for i, f in enumerate(self.frames) if f["state"] == "RETURN_TO_DOCK")
            text = "demo: returning to dock"
        else:
            text = f"demo: {len(msg['args']['no_go'])} no-go zone(s) applied"
        self._telemetry(robot_id, self.frames[self._cursor[robot_id]])
        self.emit(robot_id, "ack", {"action": action, "accepted": True, "message": text})
        return True, text, msg


class RosbridgeRobotLink(RobotLink):
    """Real robots. One reconnecting WebSocket client per robot (rosbridge protocol v2)."""
    kind = "rosbridge"

    def __init__(self, timeout_s: float = 5.0) -> None:
        super().__init__()
        self.timeout_s = timeout_s
        self._ws: Dict[str, object] = {}
        self._pending: Dict[str, asyncio.Future] = {}
        self._tasks: List[asyncio.Task] = []
        self._call = 0

    async def start(self, robots: List[dict]) -> None:
        for r in robots:
            self._tasks.append(asyncio.create_task(self._run(r["id"], r["endpoint"])))

    async def _run(self, robot_id: str, url: str) -> None:
        import websockets  # imported here so the demo path has no network dependency

        backoff = 1.0
        while True:
            try:
                async with websockets.connect(url, open_timeout=self.timeout_s, ping_interval=10) as ws:
                    self._ws[robot_id], self._online[robot_id], backoff = ws, True, 1.0
                    log.info("connected to %s (%s)", robot_id, url)
                    for sub in protocol.SUBSCRIPTIONS:
                        await ws.send(json.dumps(dict(sub, op="subscribe", id=f"sub-{sub['topic']}")))
                    async for raw in ws:
                        self._on_message(robot_id, json.loads(raw))
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 - any network error -> reconnect
                log.warning("%s link down (%s); retry in %.0f s", robot_id, e, backoff)
            self._online[robot_id] = False
            self._ws.pop(robot_id, None)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)

    def _on_message(self, robot_id: str, msg: dict) -> None:
        if msg.get("op") == "publish":
            self._telemetry(robot_id, protocol.merge_rosbridge(self._latest.get(robot_id, {}), msg))
        elif msg.get("op") == "service_response":
            fut = self._pending.pop(msg.get("id", ""), None)
            if fut and not fut.done():
                fut.set_result(msg)

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await t
        self._tasks.clear()

    async def send_command(self, robot_id, action, data):
        self._call += 1
        call_id = f"chotu-api-{self._call}"
        msg = protocol.to_rosbridge(action, data, call_id)
        ws = self._ws.get(robot_id)
        if ws is None:
            return False, f"{robot_id} is offline", msg
        fut = asyncio.get_running_loop().create_future()
        self._pending[call_id] = fut
        await ws.send(json.dumps(msg))
        try:
            resp = await asyncio.wait_for(fut, self.timeout_s)
        except asyncio.TimeoutError:
            self._pending.pop(call_id, None)
            return False, f"{robot_id} did not answer within {self.timeout_s:.0f} s", msg
        values = resp.get("values") or {}
        ok = bool(resp.get("result")) and bool(values.get("accepted", False))
        text = values.get("message", "") or ("accepted" if ok else "rejected")
        self.emit(robot_id, "ack", {"action": action, "accepted": ok, "message": text})
        return ok, text, msg


def build_link(kind: str, sample_dir: str, speed: float) -> RobotLink:
    if kind == "demo":
        return DemoRobotLink(sample_dir, speed)
    if kind == "rosbridge":
        return RosbridgeRobotLink()
    raise ValueError(f"CHOTU_ROBOT_LINK must be 'demo' or 'rosbridge', got {kind!r}")
