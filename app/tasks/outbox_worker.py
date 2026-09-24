"""Outbox 轮询投递器（M6）

重试退避 2**retry_count 秒、上限 5 次，超了进死信；已发超 7 天的定时清理。
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from app.db import session_factory
from app.repositories.outbox_repo import OutboxRepo
from app.services.push_service import PushService

logger = structlog.get_logger()

MAX_RETRY = 5
CLEANUP_AGE_SECONDS = 7 * 86400

Dispatcher = Callable[[dict[str, Any], int], Awaitable[None]]


async def default_dispatcher(payload: dict[str, Any], outbox_id: int) -> None:
    """PushService.dispatch 内部会 mark_sent + commit，自己管理 session。"""
    await PushService.dispatch(msg_id=payload["msg_id"], outbox_id=outbox_id)


class OutboxWorker:
    """轮询 outbox 并投递。未知 topic 就地 mark_sent 丢弃，避免堆死信。"""

    def __init__(
        self,
        dispatcher: Dispatcher | None = None,
        poll_interval: float = 1.0,
    ) -> None:
        self._dispatcher = dispatcher or default_dispatcher
        self._poll_interval = poll_interval
        self._task: asyncio.Task[None] | None = None

    async def run_forever(self) -> None:
        while True:
            try:
                await self.process_once()
            except Exception:
                logger.exception("outbox worker iteration failed")
            await asyncio.sleep(self._poll_interval)

    async def process_once(self) -> int:
        """处理一轮，返回成功投递条数。"""
        dispatched = 0
        async with session_factory() as session:
            pending = await OutboxRepo.list_pending(session, limit=100)
            for record in pending:
                if record.topic != "message.new":
                    logger.warning("unknown outbox topic, dropping", topic=record.topic)
                    await OutboxRepo.mark_sent(session, record.id)
                    await session.commit()
                    continue
                try:
                    await self._dispatcher(record.payload, record.id)
                    # 成功路径显式标已发：dispatcher 自己标不标都幂等，漏标的不能赖账
                    await OutboxRepo.mark_sent(session, record.id)
                    await session.commit()
                    dispatched += 1
                except Exception as e:
                    if record.retry_count + 1 >= MAX_RETRY:
                        await OutboxRepo.mark_dead_letter(session, record.id)
                        logger.error(
                            "outbox dead-lettered",
                            outbox_id=record.id,
                            error=str(e),
                        )
                    else:
                        backoff = 2**record.retry_count
                        await OutboxRepo.mark_retry(session, record.id, backoff_seconds=backoff)
                        logger.warning(
                            "outbox retry",
                            outbox_id=record.id,
                            retry_count=record.retry_count + 1,
                            backoff=backoff,
                            error=str(e),
                        )
                    await session.commit()
        if dispatched:
            logger.info("outbox dispatched", count=dispatched)
        return dispatched

    async def cleanup_sent(self) -> int:
        """删掉 status=1 且超过 7 天的记录，返回删除条数。"""
        async with session_factory() as session:
            count = await OutboxRepo.delete_sent_older_than(session, CLEANUP_AGE_SECONDS)
            await session.commit()
            if count:
                logger.info("outbox cleanup", deleted=count)
            return count

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self.run_forever())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None


worker = OutboxWorker()
