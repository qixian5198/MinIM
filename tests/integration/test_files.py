import io
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import create_access_token
from app.core.storage import FakeObjectStorage
from app.main import app
from app.services.user_service import UserService


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def token():
    user = await UserService.register(
        username=f"f{uuid.uuid4().hex[:10]}", password="abcd1234", nickname=None
    )
    return create_access_token(user.id)


@pytest.mark.asyncio
async def test_upload_valid_png(client: AsyncClient, token: str, monkeypatch):
    fake = FakeObjectStorage()
    monkeypatch.setattr("app.core.storage._storage", fake)
    monkeypatch.setattr("app.services.file_service.get_object_storage", lambda: fake)

    files = {"file": ("a.png", io.BytesIO(b"\x89PNG fake"), "image/png")}
    r = await client.post(
        "/api/v1/files", files=files, headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 201, r.text
    body = r.json()["data"]
    assert body["mime_type"] == "image/png"
    assert body["size"] == 9
    assert body["url"].endswith(".png") or "uploads/" in body["url"]


@pytest.mark.asyncio
async def test_upload_rejects_bad_type(client: AsyncClient, token: str):
    files = {"file": ("evil.exe", io.BytesIO(b"MZ"), "application/octet-stream")}
    r = await client.post(
        "/api/v1/files", files=files, headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 422
    assert r.json()["code"] == 60002


@pytest.mark.asyncio
async def test_upload_requires_token(client: AsyncClient):
    files = {"file": ("a.png", io.BytesIO(b"xx"), "image/png")}
    r = await client.post("/api/v1/files", files=files)
    assert r.status_code == 401
