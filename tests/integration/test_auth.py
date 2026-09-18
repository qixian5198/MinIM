import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def unique_username() -> str:
    import uuid

    return f"u{uuid.uuid4().hex[:12]}"


@pytest.mark.asyncio
async def test_register_login_refresh_me(client: AsyncClient, unique_username: str):
    r = await client.post(
        "/api/v1/auth/register",
        json={"username": unique_username, "password": "abcd1234", "nickname": "测试渔夫"},
    )
    assert r.status_code == 201, r.text
    user = r.json()["data"]
    assert user["username"] == unique_username

    r = await client.post(
        "/api/v1/auth/login",
        json={"username": unique_username, "password": "abcd1234"},
    )
    assert r.status_code == 200, r.text
    tokens = r.json()["data"]
    assert tokens["user"]["id"] == user["id"]
    assert tokens["access_token"] and tokens["refresh_token"]

    r = await client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["nickname"] == "测试渔夫"

    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["access_token"]


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, unique_username: str):
    await client.post(
        "/api/v1/auth/register",
        json={"username": unique_username, "password": "abcd1234"},
    )
    r = await client.post(
        "/api/v1/auth/login",
        json={"username": unique_username, "password": "wrong9999"},
    )
    assert r.status_code == 401
    assert r.json()["code"] == 10002


@pytest.mark.asyncio
async def test_duplicate_username_returns_409(client: AsyncClient, unique_username: str):
    r1 = await client.post(
        "/api/v1/auth/register",
        json={"username": unique_username, "password": "abcd1234"},
    )
    assert r1.status_code == 201
    r2 = await client.post(
        "/api/v1/auth/register",
        json={"username": unique_username, "password": "abcd1234"},
    )
    assert r2.status_code == 409
    assert r2.json()["code"] == 10001


@pytest.mark.asyncio
async def test_me_requires_token(client: AsyncClient):
    r = await client.get("/api/v1/users/me")
    assert r.status_code == 401
