import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


def _uname() -> str:
    return f"u{uuid.uuid4().hex[:12]}"


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _register(client: AsyncClient) -> dict:
    r = await client.post(
        "/api/v1/auth/register",
        json={"username": _uname(), "password": "abcd1234"},
    )
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    data["token"] = (
        r.json()["data"].get("access_token")
        or (
            await client.post(
                "/api/v1/auth/login",
                json={"username": data["username"], "password": "abcd1234"},
            )
        ).json()["data"]["access_token"]
    )
    return data


@pytest.fixture
async def alice(client: AsyncClient) -> dict:
    return await _register(client)


@pytest.fixture
async def bob(client: AsyncClient) -> dict:
    return await _register(client)


def _auth(user: dict) -> dict:
    return {"Authorization": f"Bearer {user['token']}"}


async def test_single_room_is_idempotent(client: AsyncClient, alice: dict, bob: dict):
    r1 = await client.post(
        "/api/v1/rooms/single", json={"target_uid": bob["id"]}, headers=_auth(alice)
    )
    assert r1.status_code == 201, r1.text
    room_id = r1.json()["data"]["id"]

    r2 = await client.post(
        "/api/v1/rooms/single", json={"target_uid": bob["id"]}, headers=_auth(alice)
    )
    assert r2.status_code == 200
    assert r2.json()["data"]["id"] == room_id

    # 反向建也要命中同一个会话
    r3 = await client.post(
        "/api/v1/rooms/single", json={"target_uid": alice["id"]}, headers=_auth(bob)
    )
    assert r3.status_code == 200
    assert r3.json()["data"]["id"] == room_id


async def test_cannot_create_single_with_self(client: AsyncClient, alice: dict):
    r = await client.post(
        "/api/v1/rooms/single", json={"target_uid": alice["id"]}, headers=_auth(alice)
    )
    assert r.status_code == 400
    assert r.json()["code"] == 30005


async def test_single_with_missing_user(client: AsyncClient, alice: dict):
    r = await client.post(
        "/api/v1/rooms/single", json={"target_uid": "99999999"}, headers=_auth(alice)
    )
    assert r.status_code == 404


async def test_send_and_list_messages(client: AsyncClient, alice: dict, bob: dict):
    room_id = (
        await client.post(
            "/api/v1/rooms/single", json={"target_uid": bob["id"]}, headers=_auth(alice)
        )
    ).json()["data"]["id"]

    r = await client.post(
        "/api/v1/messages",
        json={"room_id": room_id, "type": 1, "content": "第一条"},
        headers=_auth(alice),
    )
    assert r.status_code == 201, r.text
    msg = r.json()["data"]
    assert msg["room_id"] == room_id
    assert msg["from_uid"] == alice["id"]
    assert msg["content"] == "第一条"

    listed = await client.get(f"/api/v1/rooms/{room_id}/messages", headers=_auth(bob))
    assert listed.status_code == 200
    body = listed.json()["data"]
    assert body["has_more"] is False
    assert [m["id"] for m in body["list"]] == [msg["id"]]


async def test_sensitive_word_is_replaced_not_rejected(client: AsyncClient, alice: dict, bob: dict):
    room_id = (
        await client.post(
            "/api/v1/rooms/single", json={"target_uid": bob["id"]}, headers=_auth(alice)
        )
    ).json()["data"]["id"]

    r = await client.post(
        "/api/v1/messages",
        json={"room_id": room_id, "type": 1, "content": "你是个傻逼"},
        headers=_auth(alice),
    )
    assert r.status_code == 201
    assert r.json()["data"]["content"] == "你是个***"


async def test_non_member_cannot_read_messages(client: AsyncClient, alice: dict, bob: dict):
    room_id = (
        await client.post(
            "/api/v1/rooms/single", json={"target_uid": bob["id"]}, headers=_auth(alice)
        )
    ).json()["data"]["id"]

    carol = await _register(client)
    r = await client.get(f"/api/v1/rooms/{room_id}/messages", headers=_auth(carol))
    assert r.status_code == 403
    assert r.json()["code"] == 30002

    r = await client.post(
        "/api/v1/messages",
        json={"room_id": room_id, "type": 1, "content": "蹭一下"},
        headers=_auth(carol),
    )
    assert r.status_code == 403

    r = await client.get(f"/api/v1/rooms/{room_id}/members", headers=_auth(carol))
    assert r.status_code == 403


async def test_cursor_pagination_walks_backwards(client: AsyncClient, alice: dict, bob: dict):
    room_id = (
        await client.post(
            "/api/v1/rooms/single", json={"target_uid": bob["id"]}, headers=_auth(alice)
        )
    ).json()["data"]["id"]

    for i in range(5):
        await client.post(
            "/api/v1/messages",
            json={"room_id": room_id, "type": 1, "content": f"msg-{i}"},
            headers=_auth(alice),
        )

    seen: list[str] = []
    cursor = None
    pages = 0
    while True:
        params = {"limit": 2}
        if cursor:
            params["cursor"] = cursor
        r = await client.get(
            f"/api/v1/rooms/{room_id}/messages", params=params, headers=_auth(alice)
        )
        assert r.status_code == 200, r.text
        body = r.json()["data"]
        seen.extend(m["content"] for m in body["list"])
        pages += 1
        assert pages < 10, "分页没收敛"
        if not body["has_more"]:
            break
        cursor = body["next_cursor"]

    # 倒序返回，翻完正好是 msg-4 .. msg-0
    assert seen == [f"msg-{i}" for i in (4, 3, 2, 1, 0)]


async def test_room_list_shows_last_message_and_unread(client: AsyncClient, alice: dict, bob: dict):
    room_id = (
        await client.post(
            "/api/v1/rooms/single", json={"target_uid": bob["id"]}, headers=_auth(alice)
        )
    ).json()["data"]["id"]
    await client.post(
        "/api/v1/messages",
        json={"room_id": room_id, "type": 1, "content": "最后一条"},
        headers=_auth(alice),
    )

    # bob 还没读过，未读 1 条
    rooms = (await client.get("/api/v1/rooms", headers=_auth(bob))).json()["data"]["list"]
    assert len(rooms) == 1
    assert rooms[0]["id"] == room_id
    assert rooms[0]["last_message"]["content"] == "最后一条"
    assert rooms[0]["unread_count"] == 1


async def test_members_list(client: AsyncClient, alice: dict, bob: dict):
    room_id = (
        await client.post(
            "/api/v1/rooms/single", json={"target_uid": bob["id"]}, headers=_auth(alice)
        )
    ).json()["data"]["id"]

    r = await client.get(f"/api/v1/rooms/{room_id}/members", headers=_auth(alice))
    assert r.status_code == 200
    members = r.json()["data"]["list"]
    assert {m["user_id"] for m in members} == {alice["id"], bob["id"]}
    assert all(m["role"] == 2 for m in members)
