"""M7 频控集成测试（docs/08 §5 阈值表）

| 接口 | 维度 | 阈值 |
|:---|:---|:---|
| POST /messages | 用户 | 20/分钟 |
| /auth/login | IP | 10/分钟 |
| /auth/register | IP | 3/分钟 |
| WS 连接 | IP | 20/分钟 |

计数在 Redis 里，conftest 的 `_reset_rate_limit` 每个测试前后清 `rl:*`，
所以这里可以放心把额度打满；超限要带 `Retry-After`（docs/08 §5 测试要求）。
"""

import asyncio
import uuid

import pytest
import uvicorn
import websockets
from httpx import AsyncClient
from redis.asyncio import Redis

from app.core.config import settings
from app.main import app

WS_PORT = 8768


def _uname() -> str:
    return f"r{uuid.uuid4().hex[:12]}"


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


async def _reset(pattern: str) -> None:
    """清掉某个频控前缀的计数，用来验证"可恢复" """
    client: Redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        keys = await client.keys(pattern)
        if keys:
            await client.delete(*keys)
    finally:
        await client.aclose()


async def _register(base: str) -> dict:
    async with AsyncClient(base_url=base) as c:
        username = _uname()
        r = await c.post(
            "/api/v1/auth/register", json={"username": username, "password": "abcd1234"}
        )
        assert r.status_code == 201, r.text
        r = await c.post(
            "/api/v1/auth/login", json={"username": username, "password": "abcd1234"}
        )
        data = r.json()["data"]
        return {"id": data["user"]["id"], "token": data["access_token"]}


async def _room(base: str, a: dict, b: dict) -> str:
    async with AsyncClient(base_url=base) as c:
        r = await c.post(
            "/api/v1/rooms/single",
            json={"target_uid": b["id"]},
            headers={"Authorization": f"Bearer {a['token']}"},
        )
        assert r.status_code == 201, r.text
        return r.json()["data"]["id"]


def _ws_url(token: str) -> str:
    return f"ws://127.0.0.1:{WS_PORT}/ws?token={token}&last_seq=0"


async def test_message_rate_limit_blocks_21st(server: str):
    alice = await _register(server)
    bob = await _register(server)
    room = await _room(server, alice, bob)

    async with AsyncClient(base_url=server) as c:
        for i in range(20):
            r = await c.post(
                "/api/v1/messages",
                json={"room_id": room, "type": 1, "content": f"msg{i}"},
                headers={"Authorization": f"Bearer {alice['token']}"},
            )
            assert r.status_code == 201, r.text

        over = await c.post(
            "/api/v1/messages",
            json={"room_id": room, "type": 1, "content": "one too many"},
            headers={"Authorization": f"Bearer {alice['token']}"},
        )

    assert over.status_code == 429
    assert over.json()["code"] == 90001
    assert "Retry-After" in over.headers


async def test_message_rate_limit_is_per_user(server: str):
    """额度按用户走：alice 打满不影响 bob"""
    alice = await _register(server)
    bob = await _register(server)
    room = await _room(server, alice, bob)

    async with AsyncClient(base_url=server) as c:
        for i in range(20):
            r = await c.post(
                "/api/v1/messages",
                json={"room_id": room, "type": 1, "content": f"a{i}"},
                headers={"Authorization": f"Bearer {alice['token']}"},
            )
            assert r.status_code == 201

        blocked = await c.post(
            "/api/v1/messages",
            json={"room_id": room, "type": 1, "content": "blocked"},
            headers={"Authorization": f"Bearer {alice['token']}"},
        )
        allowed = await c.post(
            "/api/v1/messages",
            json={"room_id": room, "type": 1, "content": "bob still ok"},
            headers={"Authorization": f"Bearer {bob['token']}"},
        )

    assert blocked.status_code == 429
    assert allowed.status_code == 201


async def test_message_rate_limit_recovers_after_reset(server: str):
    alice = await _register(server)
    bob = await _register(server)
    room = await _room(server, alice, bob)

    async with AsyncClient(base_url=server) as c:
        for i in range(20):
            await c.post(
                "/api/v1/messages",
                json={"room_id": room, "type": 1, "content": f"m{i}"},
                headers={"Authorization": f"Bearer {alice['token']}"},
            )
        over = await c.post(
            "/api/v1/messages",
            json={"room_id": room, "type": 1, "content": "over"},
            headers={"Authorization": f"Bearer {alice['token']}"},
        )
        assert over.status_code == 429

        await _reset("rl:msg:*")

        ok = await c.post(
            "/api/v1/messages",
            json={"room_id": room, "type": 1, "content": "ok now"},
            headers={"Authorization": f"Bearer {alice['token']}"},
        )
        assert ok.status_code == 201


async def test_login_rate_limit_by_ip(server: str):
    """频控在业务逻辑之前，所以用户名存不存在都会计数"""
    username = _uname()  # 没注册过；登录失败照样占频控额度
    async with AsyncClient(base_url=server) as c:
        for _ in range(10):
            r = await c.post(
                "/api/v1/auth/login", json={"username": username, "password": "abcd1234"}
            )
            # 用户名不存在也统一回 401 密码错误（防用户名枚举），不是 404
            assert r.status_code == 401, r.text

        over = await c.post(
            "/api/v1/auth/login", json={"username": username, "password": "abcd1234"}
        )

    assert over.status_code == 429
    assert over.json()["code"] == 90001
    assert "Retry-After" in over.headers


async def test_register_rate_limit_by_ip(server: str):
    async with AsyncClient(base_url=server) as c:
        for _ in range(3):
            r = await c.post(
                "/api/v1/auth/register",
                json={"username": _uname(), "password": "abcd1234"},
            )
            assert r.status_code == 201, r.text

        over = await c.post(
            "/api/v1/auth/register", json={"username": _uname(), "password": "abcd1234"}
        )

    assert over.status_code == 429
    assert over.json()["code"] == 90001


async def test_ws_connection_rate_limit(server: str):
    alice = await _register(server)
    url = _ws_url(alice["token"])

    for _ in range(20):
        async with websockets.connect(url) as ws:
            await asyncio.wait_for(ws.recv(), timeout=5)  # sync.done

    # 握手之前就被拒，客户端拿到的是 HTTP 403（WebSocket 关闭码传不过去，
    # 所以这里断言 HTTP 状态而不是 4002）
    with pytest.raises(websockets.exceptions.InvalidStatus) as ei:
        async with websockets.connect(url) as ws:
            await asyncio.wait_for(ws.recv(), timeout=5)

    assert ei.value.response.status_code == 403
