from typing import Any

import structlog

from app.db import session_factory
from app.models.enums import MessageType
from app.models.message import Message
from app.repositories.message_repo import MessageRepo
from app.repositories.outbox_repo import OutboxRepo
from app.repositories.room_repo import RoomRepo
from app.security.sensitive import sensitive_filter
from app.services.push_service import PushService

logger = structlog.get_logger()

# WS 推送就按这个 topic 消费 outbox（M2 埋的口子，M3 开始消费）
TOPIC_MESSAGE_NEW = "message.new"


class MessageService:
    @staticmethod
    async def send(
        *,
        user_id: int,
        room_id: int,
        type: int = MessageType.TEXT,
        content: str | None = None,
        reply_to_id: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> Message:
        async with session_factory() as session:
            room = await RoomRepo.assert_member(session, room_id, user_id)
            # 敏感词命中不报错，替换后照常入库（docs/06 §6）
            if content:
                content = sensitive_filter.filter(content)

            try:
                msg = await MessageRepo.create(
                    session,
                    room_id=room_id,
                    from_uid=user_id,
                    type=MessageType(type),
                    content=content,
                    reply_to_id=reply_to_id,
                    extra=extra,
                )
                outbox = await OutboxRepo.create(
                    session,
                    topic=TOPIC_MESSAGE_NEW,
                    payload={"msg_id": msg.id, "room_id": room_id},
                )
                await RoomRepo.touch_last_msg(session, room, msg.id)
                # 三件事同一事务：消息落库了就一定会有推送任务，也一定会更新会话最后一条
                await session.commit()
            except Exception:
                await session.rollback()
                raise

        # 推送在事务外：推失败不能回滚已入库的消息，outbox 留着待发，M6 会重试
        try:
            await PushService.dispatch(msg_id=msg.id, outbox_id=outbox.id)
        except Exception:
            logger.exception("push failed, outbox stays pending", msg_id=msg.id)
        return msg

    @staticmethod
    async def list_messages(
        *, user_id: int, room_id: int, cursor: int | None, limit: int
    ) -> tuple[list[Message], str | None, bool]:
        async with session_factory() as session:
            await RoomRepo.assert_member(session, room_id, user_id)
            return await MessageRepo.list_by_cursor(session, room_id, cursor, limit)
