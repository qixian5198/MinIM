from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import OutboxStatus
from app.models.outbox import Outbox


class OutboxRepo:
    """与业务写入同事务，保证"落库即会投递"（轮询重试在 M6）"""

    @staticmethod
    async def create(session: AsyncSession, *, topic: str, payload: dict[str, Any]) -> Outbox:
        record = Outbox(topic=topic, payload=payload)
        session.add(record)
        await session.flush()
        return record

    @staticmethod
    async def list_pending(session: AsyncSession, *, limit: int = 100) -> list[Outbox]:
        now = func.now()
        result = await session.execute(
            select(Outbox)
            .where(
                Outbox.status == OutboxStatus.PENDING,
                # 首投（next_retry_at 为 NULL）或退避已到期才捞
                Outbox.next_retry_at.is_(None) | (Outbox.next_retry_at <= now),
            )
            .order_by(Outbox.id)
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def mark_sent(session: AsyncSession, outbox_id: int) -> None:
        record = await session.get(Outbox, outbox_id)
        if record is not None:
            record.status = OutboxStatus.SENT
            record.next_retry_at = None
            await session.flush()

    @staticmethod
    async def mark_retry(session: AsyncSession, outbox_id: int, *, backoff_seconds: int) -> None:
        # 原子自增，避免 read-modify-write 竞争；失败原因只进日志，表里没有 last_error 列
        # 注意：PG 里 now() + 整数是加"天"，必须用 timedelta 走 interval
        from datetime import timedelta

        await session.execute(
            update(Outbox)
            .where(
                Outbox.id == outbox_id,
                Outbox.status == OutboxStatus.PENDING,
            )
            .values(
                retry_count=Outbox.retry_count + 1,
                next_retry_at=func.now() + timedelta(seconds=backoff_seconds),
            )
        )
        await session.flush()

    @staticmethod
    async def mark_dead_letter(session: AsyncSession, outbox_id: int) -> None:
        await session.execute(
            update(Outbox)
            .where(Outbox.id == outbox_id)
            .values(
                status=OutboxStatus.DEAD, retry_count=Outbox.retry_count + 1, next_retry_at=None
            )
        )
        await session.flush()

    @staticmethod
    async def delete_sent_older_than(session: AsyncSession, seconds: int) -> int:
        from datetime import timedelta

        result = await session.execute(
            delete(Outbox)
            .where(
                Outbox.status == OutboxStatus.SENT,
                Outbox.created_at < func.now() - timedelta(seconds=seconds),
            )
            .execution_options(synchronize_session="fetch")
        )
        return result.rowcount or 0
