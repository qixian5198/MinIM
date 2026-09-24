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


@pytest.fixture(autouse=True)
async def _reset_rate_limit():
    """频控计数器在 Redis 里、跨测试共享（IP 维度更是所有测试同一个 127.0.0.1）。

    不清的话前一个测试打满的额度会算到后一个头上，随机性地挂一片。
    docs/08 §5 明确要求"频控测试要能重置状态"。
    前后各清一次：前面清是防上一个测试的残留，后面清是不留给下一个。
    """
    from redis.asyncio import Redis

    from app.core.config import settings

    async def _flush() -> None:
        # 不能复用 app.core.redis 的全局 client：它跟 engine 一样绑定首次创建的
        # event loop，而 pytest-asyncio 每个测试都是新 loop，复用会 RuntimeError。
        # 这里临时建一个连接，用完立刻关。
        client: Redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            keys = await client.keys("rl:*")
            if keys:
                await client.delete(*keys)
        finally:
            await client.aclose()

    await _flush()
    yield
    await _flush()
