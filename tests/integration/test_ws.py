"""M3 WebSocket 集成测试。

WS 是长连接，没法用 ASGITransport 测（httpx 不支持 WS），
所以在测试自己的 event loop 里起一个真实 uvicorn，再用 websockets 客户端连进去。
这样 DB 连接、Redis 连接、WS 全在同一个 loop 里，不会踩"跨 loop 用连接池"的坑。
"""

import asyncio
import uuid

import pytest
import uvicorn
import websockets
from httpx import AsyncClient

from app.main import app

WS_PORT = 8765


def _uname() -> str:
    return f"w{uuid.uuid4().hex[:12]}"


@pytest.fixture
async def server():
    config = uvicorn.Config(app, host="127.0.0.1", port=WS_PORT, log_level="warning")
    srv = uvicorn.Server(config)
    task = asyncio.create_task(srv.serve())
    for _ in range(100):
        if srv.started:
            break
        await asyncio.sleep(0.05)
    try:
        yield f"http://127.0.0.1:{WS_PORT}"
    finally:
        srv.should_exit = True
        await task


async def _register(base: str) -> dict:
    async with AsyncClient(base_url=base) as c:
        username = _uname()
        r = await c.post(
            "/api/v1/auth/register",
            json={"username": username, "password": "abcd1234"},
        )
        assert r.status_code == 201, r.text
        r = await c.post("/api/v1/auth/login", json={"username": username, "password": "abcd1234"})
        data = r.json()["data"]
        return {"id": data["user"]["id"], "token": data["access_token"]}


async def _single_room(base: str, a: dict, b: dict) -> str:
    async with AsyncClient(base_url=base) as c:
        r = await c.post(
            "/api/v1/rooms/single",
            json={"target_uid": b["id"]},
            headers={"Authorization": f"Bearer {a['token']}"},
        )
        assert r.status_code == 201, r.text
        return r.json()["data"]["id"]


async def _send(base: str, user: dict, room_id: str, content: str) -> None:
    async with AsyncClient(base_url=base) as c:
        r = await c.post(
            "/api/v1/messages",
            json={"room_id": room_id, "type": 1, "content": content},
            headers={"Authorization": f"Bearer {user['token']}"},
        )
        assert r.status_code == 201, r.text


def _ws_url(token: str, last_seq: int = 0) -> str:
    return f"ws://127.0.0.1:{WS_PORT}/ws?token={token}&last_seq={last_seq}"


async def test_connect_without_token_is_rejected(server: str):
    with pytest.raises(websockets.InvalidStatus):
        async with websockets.connect(f"ws://127.0.0.1:{WS_PORT}/ws"):
            pass


async def test_handshake_sends_sync_done(server: str):
    user = await _register(server)
    async with websockets.connect(_ws_url(user["token"])) as ws:
        first = await asyncio.wait_for(ws.recv(), timeout=5)
    import json

    assert json.loads(first)["type"] == "sync.done"


async def test_message_is_pushed_to_both_sides(server: str):
    alice = await _register(server)
    bob = await _register(server)
    room_id = await _single_room(server, alice, bob)

    async with (
        websockets.connect(_ws_url(alice["token"])) as ws_a,
        websockets.connect(_ws_url(bob["token"])) as ws_b,
    ):
        await asyncio.wait_for(ws_a.recv(), timeout=5)  # sync.done
        await asyncio.wait_for(ws_b.recv(), timeout=5)

        await _send(server, alice, room_id, "推送测试")

        got = await asyncio.wait_for(ws_b.recv(), timeout=5)
        assert got is not None
        import json

        event = json.loads(got)
        assert event["type"] == "message.new"
        assert event["data"]["content"] == "推送测试"
        assert event["data"]["room_id"] == room_id
        assert event["seq"] > 0

        # 发送者自己的另一个标签页也要收到（多端同步）
        own = json.loads(await asyncio.wait_for(ws_a.recv(), timeout=5))
        assert own["data"]["content"] == "推送测试"


async def test_offline_messages_are_replayed_on_reconnect(server: str):
    alice = await _register(server)
    bob = await _register(server)
    room_id = await _single_room(server, alice, bob)

    # bob 离线期间 alice 发两条
    await _send(server, alice, room_id, "离线第一条")
    await _send(server, alice, room_id, "离线第二条")

    async with websockets.connect(_ws_url(bob["token"], last_seq=0)) as ws:
        events = []
        for _ in range(3):  # 2 条补发 + sync.done
            events.append(await asyncio.wait_for(ws.recv(), timeout=5))

        import json

        types = [json.loads(e)["type"] for e in events]
        assert types == ["message.new", "message.new", "sync.done"]
        assert json.loads(events[0])["data"]["content"] == "离线第一条"
        assert json.loads(events[1])["data"]["content"] == "离线第二条"
        # 记录已收到的最大 seq，避免依赖全局计数器（跨测试共享、单调递增）
        last_seq = json.loads(events[1])["seq"]

    # 带真实 last_seq 重连不该重复补发
    async with websockets.connect(_ws_url(bob["token"], last_seq=last_seq)) as ws:
        first = await asyncio.wait_for(ws.recv(), timeout=5)
        import json

        assert json.loads(first)["type"] == "sync.done"


async def test_ping_returns_pong(server: str):
    import json

    user = await _register(server)
    async with websockets.connect(_ws_url(user["token"])) as ws:
        await asyncio.wait_for(ws.recv(), timeout=5)
        await ws.send(json.dumps({"type": "ping"}))
        reply = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        assert reply["type"] == "pong"
