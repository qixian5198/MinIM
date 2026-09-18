from redis.asyncio import Redis

from app.core.config import settings

# decode_responses=True：事件流里存的是 JSON 字符串，取出来直接 json.loads
redis_client: Redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)


async def close_redis() -> None:
    await redis_client.aclose()


# redis-py 5.x 的异步方法签名是 `Awaitable[T] | T`（同一套代码要兼容同步客户端），
# mypy 会报 "Incompatible types in await"。把 type: ignore 收在这四个包装里，
# 业务侧就不用到处写 ignore 了。
async def incr(key: str) -> int:
    return int(await redis_client.incr(key))


async def lpush(key: str, value: str) -> None:
    await redis_client.lpush(key, value)  # type: ignore[misc]


async def ltrim(key: str, start: int, end: int) -> None:
    await redis_client.ltrim(key, start, end)  # type: ignore[misc]


async def lrange(key: str, start: int, end: int) -> list[str]:
    result: list[str] = await redis_client.lrange(key, start, end)  # type: ignore[misc]
    return result
