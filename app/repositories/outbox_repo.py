from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.outbox import Outbox


class OutboxRepo:
    """与业务写入同事务，保证"落库即会投递"（真正投递在 M6）"""

    @staticmethod
    async def create(session: AsyncSession, *, topic: str, payload: dict[str, Any]) -> Outbox:
        record = Outbox(topic=topic, payload=payload)
        session.add(record)
        await session.flush()
        return record
