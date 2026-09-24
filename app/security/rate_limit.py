"""频控（docs/08 §5 阈值表 / docs/11 M7）

滑动窗口用 Redis ZSET：成员是"时间戳:随机"，分数是时间戳。
每次请求先塞入、再删掉窗口外的，剩下的个数就是窗口内的请求数。

用法（docs/11 M7 给的装饰器形式）：

    @router.post("/messages")
    @rate_limit(name="msg", key="user", limit=20, window=60)
    async def send_message(...): ...

装饰器会给被包装函数注入一个 request 参数拿 IP（FastAPI 靠 __signature__ 识别），
原函数不需要声明它；拿不到 Request 时放行——不能因为频控把接口打挂。
"""

from __future__ import annotations

import functools
import inspect
import math
import time
import uuid
from collections.abc import Callable
from typing import Any

import structlog
from fastapi import Request

from app.core import redis
from app.core.error_codes import ErrorCode
from app.core.exceptions import ApiError
from app.models.enums import AuditResult
from app.models.user import User
from app.security import audit

logger = structlog.get_logger()

KEY_PREFIX = "rl"

# 频控依赖 Redis：Redis 挂了要放行还是拦？放行——宁可放过不可误杀，
# 频控是抗滥用不是鉴权，误杀等于自己把自己 DDoS 了。
FAIL_OPEN = True


async def _hit(redis_key: str, limit: int, window: int) -> int:
    """记一次请求。返回 0 放行，>0 表示建议多少秒后重试。"""
    now = time.time()
    await redis.zadd(redis_key, f"{now}:{uuid.uuid4().hex}", now)
    await redis.zremrangebyscore(redis_key, 0.0, now - window)
    count = await redis.zcard(redis_key)
    await redis.expire(redis_key, window)
    if count <= limit:
        return 0
    # 超限时算真实剩余时间：窗口里最早那次请求还要多久过期
    oldest = await redis.zrange_withscores(redis_key, 0, 0)
    if not oldest:
        return window
    return max(1, math.ceil(window - (now - oldest[0][1])))


def _identity(request: Request | None, kwargs: dict[str, Any], dimension: str) -> str:
    if dimension == "ip":
        return request.client.host if request is not None and request.client else "unknown"
    user = kwargs.get("user")
    if isinstance(user, User):
        return str(user.id)
    return "anonymous"


async def enforce(
    *, name: str, dimension: str, identity: str, limit: int, window: int
) -> None:
    """底层打点：超限直接抛 429（带 Retry-After）。非装饰器场景（如 WS）直接用这个。"""
    redis_key = f"{KEY_PREFIX}:{name}:{dimension}:{identity}"
    try:
        retry_after = await _hit(redis_key, limit, window)
    except Exception:
        logger.exception("rate limit check failed", redis_key=redis_key)
        if FAIL_OPEN:
            return None
        raise
    if retry_after:
        # 频控拦截是安全事件，留痕（IP 维度才有 ip 可记）
        await audit.record(
            action="rate.blocked",
            result=AuditResult.DENIED,
            detail=f"{name}:{dimension}",
            ip=identity if dimension == "ip" else None,
        )
        raise ApiError(
            ErrorCode.RATE_LIMITED,
            f"请求过于频繁，请 {retry_after} 秒后重试",
            429,
            {"Retry-After": str(retry_after)},
        )
    return None


def rate_limit(*, name: str, key: str, limit: int, window: int) -> Callable[..., Any]:
    """端点频控装饰器。key="user" 按用户 id，key="ip" 按客户端 IP。"""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        sig = inspect.signature(func)
        injected = "request" not in sig.parameters
        if injected:
            params = list(sig.parameters.values())
            params.append(
                inspect.Parameter(
                    "request",
                    inspect.Parameter.KEYWORD_ONLY,
                    annotation=Request,
                )
            )
            sig = sig.replace(parameters=params)

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            request: Request | None = kwargs.get("request")
            await enforce(
                name=name,
                dimension=key,
                identity=_identity(request, kwargs, key),
                limit=limit,
                window=window,
            )
            if injected:
                kwargs.pop("request", None)
            return await func(*args, **kwargs)

        wrapper.__signature__ = sig  # type: ignore[attr-defined]
        return wrapper

    return decorator
