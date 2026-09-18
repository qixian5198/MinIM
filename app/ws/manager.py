import time
from collections import defaultdict
from typing import Any

import structlog
from fastapi import WebSocket

logger = structlog.get_logger()

# 超过这个时间没收到任何帧就认为连接已死（客户端 30s 一次 ping，留一倍余量）
HEARTBEAT_TIMEOUT = 60
WS_CLOSE_HEARTBEAT_TIMEOUT = 4003


class ConnectionManager:
    """user_id -> 该用户的所有连接。

    一个用户可能开多个标签页，所以是 set 不是单个 WebSocket。
    """

    def __init__(self) -> None:
        self._conns: dict[int, set[WebSocket]] = defaultdict(set)
        self._last_seen: dict[WebSocket, float] = {}

    async def connect(self, user_id: int, ws: WebSocket) -> None:
        await ws.accept()
        self._conns[user_id].add(ws)
        self._last_seen[ws] = time.monotonic()

    def disconnect(self, user_id: int, ws: WebSocket) -> None:
        self._conns[user_id].discard(ws)
        self._last_seen.pop(ws, None)
        if not self._conns[user_id]:
            del self._conns[user_id]

    def touch(self, ws: WebSocket) -> None:
        self._last_seen[ws] = time.monotonic()

    def is_online(self, user_id: int) -> bool:
        return bool(self._conns.get(user_id))

    async def send_to_user(self, user_id: int, payload: dict[str, Any]) -> int:
        sent = 0
        for ws in list(self._conns.get(user_id, ())):
            try:
                await ws.send_json(payload)
            except Exception:
                # 发送失败说明连接已经断了，就地清理，别让它占着槽位
                logger.warning("ws send failed, drop connection", user_id=user_id)
                self.disconnect(user_id, ws)
                continue
            sent += 1
        return sent

    async def drop_stale(self, idle_after: float = HEARTBEAT_TIMEOUT) -> int:
        """清掉心跳超时的连接，返回清理数量"""
        now = time.monotonic()
        dropped = 0
        for user_id, socks in list(self._conns.items()):
            for ws in list(socks):
                if now - self._last_seen.get(ws, now) <= idle_after:
                    continue
                try:
                    await ws.close(code=WS_CLOSE_HEARTBEAT_TIMEOUT)
                except Exception:
                    logger.warning("ws close failed", user_id=user_id)
                self.disconnect(user_id, ws)
                dropped += 1
        return dropped


manager = ConnectionManager()
