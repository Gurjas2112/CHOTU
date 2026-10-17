"""/ws/v1/robots/{robot_id}: live telemetry + commands over one WebSocket (PROTOCOL.md §3)."""
from __future__ import annotations

import asyncio
import contextlib
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from .. import protocol
from ..deps import ws_key_ok

router = APIRouter()


@router.websocket("/ws/v1/robots/{robot_id}")
async def robot_socket(ws: WebSocket, robot_id: str):
    if not ws_key_ok(ws):
        await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason="missing or wrong api key")
        return
    repo, link = ws.app.state.repo, ws.app.state.link
    if repo.get_robot(robot_id) is None:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason=f"unknown robot {robot_id}")
        return
    await ws.accept()
    queue = link.subscribe(robot_id)
    seq = 0

    def own(type_: str, data: dict) -> dict:     # messages addressed to this client only
        nonlocal seq
        seq += 1
        return protocol.envelope(type_, robot_id, seq, data)

    await ws.send_json(own("hello", {"protocol": protocol.PROTOCOL_VERSION, "link": link.kind,
                                     "online": link.online(robot_id), "telemetry": link.latest(robot_id),
                                     "commands": sorted(protocol.COMMANDS)}))

    async def pump():
        while True:
            await ws.send_json(await queue.get())

    sender = asyncio.create_task(pump())
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json(own("error", {"reason": "invalid JSON"}))
                continue
            reason = protocol.validate_client(msg)
            if reason:
                await ws.send_json(own("error", {"reason": reason}))
            elif msg["type"] == "ping":
                await ws.send_json(own("pong", {"echo": msg.get("seq")}))
            else:
                data = msg.get("data") or {}
                ok, text, _ = await link.send_command(robot_id, data["action"], data)
                if not ok:                       # successes are acked by the link to every subscriber
                    await ws.send_json(own("error", {"action": data["action"], "reason": text}))
    except WebSocketDisconnect:
        pass
    finally:
        sender.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sender
        link.unsubscribe(robot_id, queue)
