import os

import pytest

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://minim:minim_dev@localhost:5432/minim")
os.environ.setdefault("JWT_SECRET", "test-secret")


@pytest.fixture(autouse=True)
async def _dispose_engine():
    # 每个测试独立 event loop，模块级 engine 的连接池绑定旧 loop，测试间必须释放
    from app.db import engine

    yield
    await engine.dispose()
