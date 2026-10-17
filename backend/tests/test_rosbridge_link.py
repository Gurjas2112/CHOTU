"""RosbridgeRobotLink against a fake rosbridge server (same JSON ops as rosbridge_server 1.x)."""
import asyncio
import json

import websockets

from chotu_api.services.robot_link import RosbridgeRobotLink


async def fake_rosbridge(ws, seen):
    async for raw in ws:
        msg = json.loads(raw)
        seen.append(msg)
        if msg["op"] == "subscribe" and msg["topic"] == "/chotu/status":
            await ws.send(json.dumps({"op": "publish", "topic": "/chotu/status",
                                      "msg": {"state": "COVER", "coverage_estimate": 0.42, "battery_soc": 0.88,
                                              "suction_duty": 1.0, "elapsed_s": 61.5}}))
        elif msg["op"] == "call_service":
            await ws.send(json.dumps({"op": "service_response", "id": msg["id"], "service": msg["service"],
                                      "result": True, "values": {"accepted": True, "message": "returning"}}))


def test_rosbridge_link_end_to_end():
    async def run():
        seen = []
        server = await websockets.serve(lambda ws: fake_rosbridge(ws, seen), "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        link = RosbridgeRobotLink(timeout_s=2.0)
        q = link.subscribe("chotu-01")
        await link.start([{"id": "chotu-01", "endpoint": f"ws://127.0.0.1:{port}"}])
        tel = await asyncio.wait_for(q.get(), 3)
        assert tel["type"] == "telemetry"
        assert tel["data"]["state"] == "COVER" and tel["data"]["battery_pct"] == 88.0
        assert tel["data"]["suction_pct"] == 100 and link.online("chotu-01")

        ok, text, sent = await link.send_command("chotu-01", "return_to_dock", {})
        assert ok and text == "returning"
        call = next(m for m in seen if m["op"] == "call_service")
        assert call == sent and call["args"] == {"abort": True, "time_budget_s": 0.0}
        assert {m["topic"] for m in seen if m["op"] == "subscribe"} == {"/chotu/status", "/odom"}

        await link.stop()
        server.close()
        await server.wait_closed()
        ok, text, _ = await link.send_command("chotu-02", "start_mission", {})
        assert not ok and "offline" in text

    asyncio.run(run())
