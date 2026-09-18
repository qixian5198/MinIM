from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MessageStatus, MessageType
from app.models.message import Message

MAX_PAGE_SIZE = 50
DEFAULT_PAGE_SIZE = 20


class MessageRepo:
    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        room_id: int,
        from_uid: int,
        type: MessageType = MessageType.TEXT,
        content: str | None = None,
        reply_to_id: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> Message:
        msg = Message(
            room_id=room_id,
            from_uid=from_uid,
            type=type,
            content=content,
            reply_to_id=reply_to_id,
            extra=extra,
        )
        session.add(msg)
        await session.flush()
        return msg

    @staticmethod
    async def get_by_id(session: AsyncSession, msg_id: int) -> Message | None:
        return await session.get(Message, msg_id)

    @staticmethod
    async def get_by_ids(session: AsyncSession, msg_ids: list[int]) -> dict[int, Message]:
        """批量取会话列表的最后一条消息，避免每个会话查一次"""
        if not msg_ids:
            return {}
        stmt = select(Message).where(Message.id.in_(msg_ids))
        return {m.id: m for m in (await session.execute(stmt)).scalars().all()}

    @staticmethod
    async def list_by_cursor(
        session: AsyncSession,
        room_id: int,
        cursor: int | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
    ) -> tuple[list[Message], str | None, bool]:
        """倒序游标分页：只走 id，配合 idx_msg_room_id_created 不用额外排序"""
        limit = max(1, min(limit, MAX_PAGE_SIZE))
        stmt = (
            select(Message)
            .where(Message.room_id == room_id, Message.status == MessageStatus.NORMAL)
            .order_by(Message.id.desc())
            .limit(limit + 1)  # 多查一条用来判 has_more，省一次 COUNT
        )
        if cursor is not None:
            stmt = stmt.where(Message.id < cursor)

        rows = (await session.execute(stmt)).scalars().all()
        has_more = len(rows) > limit
        items = list(rows[:limit])
        next_cursor = str(items[-1].id) if has_more and items else None
        return items, next_cursor, has_more

    @staticmethod
    async def count_after(session: AsyncSession, room_id: int, msg_id: int) -> int:
        """未读数 = 已读位点之后的消息条数"""
        stmt = select(func.count(Message.id)).where(
            Message.room_id == room_id,
            Message.id > msg_id,
            Message.status == MessageStatus.NORMAL,
        )
        return int((await session.execute(stmt)).scalar_one())
