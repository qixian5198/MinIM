"""M4 好友 / 群聊集成测试。

好友与群聊的 REST 走真 uvicorn（和 test_ws 同模式）；
WS 推送同样起真 server + websockets 客户端连进去，验证事件实时到达。
"""

import asyncio
import json
import uuid

import pytest
import uvicorn
import websockets
from httpx import AsyncClient

from app.main import app

WS_PORT = 8767


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
        r = await c.post(
            "/api/v1/auth/login", json={"username": username, "password": "abcd1234"}
        )
        data = r.json()["data"]
        return {"id": data["user"]["id"], "token": data["access_token"]}


async def _apply(base: str, frm: dict, to_uid: str):
    async with AsyncClient(base_url=base) as c:
        return await c.post(
            "/api/v1/friends/requests",
            json={"to_uid": to_uid},
            headers={"Authorization": f"Bearer {frm['token']}"},
        )


async def _accept(base: str, to_user: dict, req_id: str, action: str = "accept"):
    async with AsyncClient(base_url=base) as c:
        return await c.put(
            f"/api/v1/friends/requests/{req_id}",
            json={"action": action},
            headers={"Authorization": f"Bearer {to_user['token']}"},
        )


async def _create_group(base: str, owner: dict, member_ids: list[int], limit: int | None = None):
    async with AsyncClient(base_url=base) as c:
        body = {"name": "测试群", "member_ids": member_ids}
        if limit is not None:
            body["member_limit"] = limit
        return await c.post(
            "/api/v1/rooms/group",
            json=body,
            headers={"Authorization": f"Bearer {owner['token']}"},
        )


def _ws_url(token: str, last_seq: int = 0) -> str:
    return f"ws://127.0.0.1:{WS_PORT}/ws?token={token}&last_seq={last_seq}"


# ---------------- 好友 ----------------
async def test_friend_apply_and_accept(server: str):
    alice = await _register(server)
    bob = await _register(server)

    r = await _apply(server, alice, bob["id"])
    assert r.status_code == 201, r.text

    # B 的收件箱有 1 条待处理，from_user 是 A
    async with AsyncClient(base_url=server) as c:
        inbox = await c.get(
            "/api/v1/friends/requests", headers={"Authorization": f"Bearer {bob['token']}"}
        )
        reqs = inbox.json()["data"]["list"]
        assert len(reqs) == 1
        assert reqs[0]["from_user"]["id"] == alice["id"]
        req_id = reqs[0]["id"]

        # B 接受 → 双向好友，返回 room_id（建立的单聊）
        acc = await _accept(server, bob, req_id)
        assert acc.status_code == 200, acc.text
        assert acc.json()["data"]["room_id"]

        # 双方好友列表都含对方
        fa = await c.get("/api/v1/friends", headers={"Authorization": f"Bearer {alice['token']}"})
        fb = await c.get("/api/v1/friends", headers={"Authorization": f"Bearer {bob['token']}"})
        assert bob["id"] in [f["user_id"] for f in fa.json()["data"]["list"]]
        assert alice["id"] in [f["user_id"] for f in fb.json()["data"]["list"]]


async def test_friend_apply_already_friend(server: str):
    alice = await _register(server)
    bob = await _register(server)
    await _apply(server, alice, bob["id"])
    async with AsyncClient(base_url=server) as c:
        inbox = await c.get(
            "/api/v1/friends/requests", headers={"Authorization": f"Bearer {bob['token']}"}
        )
        await _accept(server, bob, inbox.json()["data"]["list"][0]["id"])
        # 再申请 → 已是好友
        r = await _apply(server, alice, bob["id"])
        assert r.status_code == 409
        assert r.json()["code"] == 50001


async def test_friend_apply_self_is_rejected(server: str):
    alice = await _register(server)
    async with AsyncClient(base_url=server) as c:
        r = await c.post(
            "/api/v1/friends/requests",
            json={"to_uid": alice["id"]},
            headers={"Authorization": f"Bearer {alice['token']}"},
        )
        assert r.status_code == 400
        assert r.json()["code"] == 30005


async def test_friend_apply_duplicate_pending_is_rejected(server: str):
    alice = await _register(server)
    bob = await _register(server)
    await _apply(server, alice, bob["id"])
    r = await _apply(server, alice, bob["id"])  # 第二次仍是 pending
    assert r.status_code == 409
    assert r.json()["code"] == 50004


async def test_friend_apply_blocked_is_rejected(server: str):
    alice = await _register(server)
    bob = await _register(server)
    async with AsyncClient(base_url=server) as c:
        blk = await c.post(
            "/api/v1/friends/blocks",
            json={"uid": alice["id"]},
            headers={"Authorization": f"Bearer {bob['token']}"},
        )
        assert blk.status_code == 200
        r = await _apply(server, alice, bob["id"])  # A 申请被 B 拉黑的 B
        assert r.status_code == 403
        assert r.json()["code"] == 50003


async def test_friend_reject_does_not_create_friendship(server: str):
    alice = await _register(server)
    bob = await _register(server)
    await _apply(server, alice, bob["id"])
    async with AsyncClient(base_url=server) as c:
        inbox = await c.get(
            "/api/v1/friends/requests", headers={"Authorization": f"Bearer {bob['token']}"}
        )
        r = await _accept(server, bob, inbox.json()["data"]["list"][0]["id"], action="reject")
        assert r.status_code == 200
        fa = await c.get("/api/v1/friends", headers={"Authorization": f"Bearer {alice['token']}"})
        assert fa.json()["data"]["list"] == []


async def test_block_unblock_list(server: str):
    alice = await _register(server)
    bob = await _register(server)
    async with AsyncClient(base_url=server) as c:
        await c.post(
            "/api/v1/friends/blocks",
            json={"uid": bob["id"]},
            headers={"Authorization": f"Bearer {alice['token']}"},
        )
        bl = await c.get("/api/v1/friends/blocks", headers={"Authorization": f"Bearer {alice['token']}"})
        assert bob["id"] in [x["user_id"] for x in bl.json()["data"]["list"]]
        await c.delete(
            f"/api/v1/friends/blocks/{bob['id']}",
            headers={"Authorization": f"Bearer {alice['token']}"},
        )
        bl2 = await c.get("/api/v1/friends/blocks", headers={"Authorization": f"Bearer {alice['token']}"})
        assert bl2.json()["data"]["list"] == []


# ---------------- 群聊 ----------------
async def test_create_group_and_members(server: str):
    owner = await _register(server)
    b = await _register(server)
    c = await _register(server)
    r = await _create_group(server, owner, [int(b["id"]), int(c["id"])])
    assert r.status_code == 201, r.text
    room = r.json()["data"]
    assert room["type"] == 2  # 群聊

    async with AsyncClient(base_url=server) as cl:
        members = await cl.get(
            f"/api/v1/rooms/{room['id']}/members",
            headers={"Authorization": f"Bearer {owner['token']}"},
        )
        ids = {m["user_id"] for m in members.json()["data"]["list"]}
        assert ids == {owner["id"], b["id"], c["id"]}
        # owner 角色是 1
        roles = {m["user_id"]: m["role"] for m in members.json()["data"]["list"]}
        assert roles[owner["id"]] == 1
        # 建群系统消息已落库
        msgs = await cl.get(
            f"/api/v1/rooms/{room['id']}/messages?limit=5",
            headers={"Authorization": f"Bearer {owner['token']}"},
        )
        contents = [m["content"] for m in msgs.json()["data"]["list"]]
        assert any("创建了群聊" in ctn for ctn in contents)


async def test_add_member_requires_owner(server: str):
    owner = await _register(server)
    b = await _register(server)
    d = await _register(server)
    room = (await _create_group(server, owner, [int(b["id"])])).json()["data"]
    async with AsyncClient(base_url=server) as c:
        # B 不是群主，加人应 403
        r = await c.post(
            f"/api/v1/rooms/{room['id']}/members",
            json={"user_ids": [int(d["id"])]},
            headers={"Authorization": f"Bearer {b['token']}"},
        )
        assert r.status_code == 403
        assert r.json()["code"] == 30004


async def test_add_member_exceeds_limit(server: str):
    owner = await _register(server)
    b = await _register(server)
    c = await _register(server)
    # limit=2：A+1 成员（B），再加 C 超限
    room = (await _create_group(server, owner, [int(b["id"])], limit=2)).json()["data"]
    async with AsyncClient(base_url=server) as cl:
        r = await cl.post(
            f"/api/v1/rooms/{room['id']}/members",
            json={"user_ids": [int(c["id"])]},
            headers={"Authorization": f"Bearer {owner['token']}"},
        )
        assert r.status_code == 403
        assert r.json()["code"] == 30003


async def test_owner_cannot_leave_group(server: str):
    owner = await _register(server)
    b = await _register(server)
    room = (await _create_group(server, owner, [int(b["id"])])).json()["data"]
    async with AsyncClient(base_url=server) as c:
        r = await c.delete(
            f"/api/v1/rooms/{room['id']}/members/{owner['id']}",
            headers={"Authorization": f"Bearer {owner['token']}"},
        )
        assert r.status_code == 400
        assert r.json()["code"] == 30006


async def test_kick_member_and_cannot_kick_owner(server: str):
    owner = await _register(server)
    b = await _register(server)
    c = await _register(server)
    room = (await _create_group(server, owner, [int(b["id"]), int(c["id"])])).json()["data"]
    async with AsyncClient(base_url=server) as cl:
        # owner 踢 C
        r = await cl.delete(
            f"/api/v1/rooms/{room['id']}/members/{c['id']}",
            headers={"Authorization": f"Bearer {owner['token']}"},
        )
        assert r.status_code == 200
        members = (await cl.get(
            f"/api/v1/rooms/{room['id']}/members",
            headers={"Authorization": f"Bearer {owner['token']}"},
        )).json()["data"]["list"]
        assert c["id"] not in [m["user_id"] for m in members]
        # 群主不能移除自己（等价于退群，30006）；非群主本就无法踢人（30004）
        r2 = await cl.delete(
            f"/api/v1/rooms/{room['id']}/members/{owner['id']}",
            headers={"Authorization": f"Bearer {owner['token']}"},
        )
        assert r2.status_code == 400
        assert r2.json()["code"] == 30006


# ---------------- WS 推送 ----------------
async def test_group_created_pushes_room_created(server: str):
    alice = await _register(server)
    bob = await _register(server)
    async with websockets.connect(_ws_url(bob["token"])) as ws:
        await asyncio.wait_for(ws.recv(), timeout=5)  # sync.done
        await _create_group(server, alice, [int(bob["id"])])
        event = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        assert event["type"] == "room.created"
        assert event["data"]["owner_id"] == alice["id"]


async def test_friend_request_pushes_new_and_accepted(server: str):
    alice = await _register(server)
    bob = await _register(server)
    async with websockets.connect(_ws_url(bob["token"])) as ws_b:
        await asyncio.wait_for(ws_b.recv(), timeout=5)  # sync.done
        # A 申请 B → B 收到 friend.request.new
        await _apply(server, alice, bob["id"])
        new_ev = json.loads(await asyncio.wait_for(ws_b.recv(), timeout=5))
        assert new_ev["type"] == "friend.request.new"
        assert new_ev["data"]["from_user"]["id"] == alice["id"]

        # B 接受前 A 连 WS → A 收到 friend.request.accepted
        async with websockets.connect(_ws_url(alice["token"])) as ws_a:
            await asyncio.wait_for(ws_a.recv(), timeout=5)  # sync.done
            inbox = await (
                AsyncClient(base_url=server)
            ).get("/api/v1/friends/requests", headers={"Authorization": f"Bearer {bob['token']}"})
            req_id = inbox.json()["data"]["list"][0]["id"]
            await _accept(server, bob, req_id)
            acc_ev = json.loads(await asyncio.wait_for(ws_a.recv(), timeout=5))
            assert acc_ev["type"] == "friend.request.accepted"
            assert acc_ev["data"]["room_id"]
