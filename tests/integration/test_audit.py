"""M7 审计日志集成测试（docs/08 抵赖风险）

落点：登录成功/失败、踢人/退群、敏感词命中、频控拦截。
审计是旁路写入，但写完了必须查得到——查不到等于没记。
"""

import asyncio
import uuid

import pytest
import uvicorn
from httpx import AsyncClient

from app.db import session_factory
from app.main import app
from app.models.enums import AuditResult
from app.repositories.audit_repo import AuditRepo

WS_PORT = 8769


def _uname() -> str:
    return f"a{uuid.uuid4().hex[:12]}"


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


async def _logs(*, action: str | None = None, user_id: int | None = None):
    async with session_factory() as session:
        return await AuditRepo.list_recent(session, action=action, user_id=user_id)


async def test_login_success_is_audited(server: str):
    user = await _register(server)

    logs = await _logs(action="login", user_id=int(user["id"]))
    assert logs, "登录成功应该留一条审计"
    assert int(logs[0].result) == int(AuditResult.SUCCESS)
    assert logs[0].user_id == int(user["id"])


async def test_login_failure_is_audited(server: str):
    async with AsyncClient(base_url=server) as c:
        r = await c.post(
            "/api/v1/auth/login", json={"username": _uname(), "password": "abcd1234"}
        )
        assert r.status_code == 401

    logs = await _logs(action="login")
    denied = [x for x in logs if int(x.result) == int(AuditResult.DENIED)]
    assert denied, "登录失败要留痕，否则撞库无从追溯"
    # 失败时没有 user_id，只能靠 detail 里的用户名追溯
    assert denied[0].user_id is None
    assert denied[0].detail


async def test_kick_member_is_audited(server: str):
    owner = await _register(server)
    member = await _register(server)

    async with AsyncClient(base_url=server) as c:
        r = await c.post(
            "/api/v1/rooms/group",
            json={"name": "审计测试群", "member_ids": [int(member["id"])]},
            headers={"Authorization": f"Bearer {owner['token']}"},
        )
        assert r.status_code == 201, r.text
        room_id = r.json()["data"]["id"]

        r = await c.delete(
            f"/api/v1/rooms/{room_id}/members/{member['id']}",
            headers={"Authorization": f"Bearer {owner['token']}"},
        )
        assert r.status_code == 200, r.text

    logs = await _logs(action="room.kick", user_id=int(owner["id"]))
    assert logs, "踢人属于不可逆操作，必须留痕"
    assert logs[0].target_id == str(room_id)
    assert str(member["id"]) in (logs[0].detail or "")


async def test_sensitive_word_hit_is_audited(server: str):
    alice = await _register(server)
    bob = await _register(server)
    room = await _room(server, alice, bob)

    async with AsyncClient(base_url=server) as c:
        r = await c.post(
            "/api/v1/messages",
            json={"room_id": room, "type": 1, "content": "你这个傻逼"},
            headers={"Authorization": f"Bearer {alice['token']}"},
        )
        assert r.status_code == 201, r.text
        # 命中后是替换放行，内容里应出现 ***
        assert "***" in r.json()["data"]["content"]

    logs = await _logs(action="msg.sensitive", user_id=int(alice["id"]))
    assert logs, "敏感词命中要留痕"


async def test_rate_limit_block_is_audited(server: str):
    username = _uname()
    async with AsyncClient(base_url=server) as c:
        for _ in range(10):
            await c.post(
                "/api/v1/auth/login", json={"username": username, "password": "abcd1234"}
            )
        over = await c.post(
            "/api/v1/auth/login", json={"username": username, "password": "abcd1234"}
        )
        assert over.status_code == 429

    logs = await _logs(action="rate.blocked")
    assert logs, "频控拦截是安全事件，要留痕"
    assert int(logs[0].result) == int(AuditResult.DENIED)
    assert logs[0].ip, "IP 维度的频控要把 IP 记下来"
