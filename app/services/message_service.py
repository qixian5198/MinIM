from datetime import UTC, datetime
from typing import Any

import structlog

from app.core.error_codes import ErrorCode
from app.core.exceptions import ApiError
from app.db import session_factory
from app.models.enums import MessageType
from app.models.message import Message
from app.repositories.message_repo import MessageRepo
from app.repositories.outbox_repo import OutboxRepo
from app.repositories.room_repo import RoomRepo
from app.schemas.message import MarkOut
from app.security.sensitive import sensitive_filter
from app.services.push_service import PushService

logger = structlog.get_logger()

# WS 推送就按这个 topic 消费 outbox（M2 埋的口子，M3 开始消费）
TOPIC_MESSAGE_NEW = "message.new"
# 撤回时限：2 分钟（docs/06 §6.4）
RECALL_WINDOW_SECONDS = 120


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

    @staticmethod
    async def recall(*, user_id: int, msg_id: int) -> None:
        """撤回自己的消息：仅发送者可操作，且限 2 分钟内；type 置 RECALL，extra 记撤回人/时间"""
        async with session_factory() as session:
            msg = await MessageRepo.get_by_id(session, msg_id)
            if msg is None:
                raise ApiError(ErrorCode.MESSAGE_NOT_FOUND, "消息不存在", 404)
            if msg.from_uid != user_id:
                raise ApiError(ErrorCode.NOT_MESSAGE_SENDER, "只能撤回自己发的消息", 403)

            age = (datetime.now(UTC) - msg.created_at).total_seconds()
            if age > RECALL_WINDOW_SECONDS:
                raise ApiError(ErrorCode.MESSAGE_RECALL_TIMEOUT, "超过撤回时限", 422)

            room_id, event_msg_id = msg.room_id, msg.id
            await MessageRepo.recall(session, msg, user_id, datetime.now(UTC))
            members = await RoomRepo.list_members(session, room_id)
            audience = [m.user_id for m in members]
            await session.commit()

        # 推送在事务外：失败不回滚已落库的撤回
        try:
            await PushService.emit_event(
                "message.recalled",
                {"room_id": str(room_id), "msg_id": str(event_msg_id)},
                audience,
            )
        except Exception:
            logger.exception("push recalled failed", msg_id=event_msg_id)

    @staticmethod
    async def mark(*, user_id: int, msg_id: int, mark_type: int) -> MarkOut:
        """点赞 / 点踩（幂等切换）：同类型重复提交 = 取消，返回该类型当前总数"""
        async with session_factory() as session:
            msg = await MessageRepo.get_by_id(session, msg_id)
            if msg is None:
                raise ApiError(ErrorCode.MESSAGE_NOT_FOUND, "消息不存在", 404)
            # 只对所在会话的消息可 mark，避免对无关消息操作
            await RoomRepo.assert_member(session, msg.room_id, user_id)

            _, count = await MessageRepo.mark_toggle(
                session, msg_id=msg_id, user_id=user_id, mark_type=mark_type
            )
            await session.commit()
        return MarkOut(msg_id=str(msg_id), mark_type=mark_type, count=count)

    @staticmethod
    async def report_read(*, user_id: int, room_id: int, last_read_msg_id: int) -> int:
        """上报已读位点（仅前进），推 message.read 给房间内其他人，返回自己的未读数"""
        async with session_factory() as session:
            await RoomRepo.assert_member(session, room_id, user_id)
            await RoomRepo.update_last_read(session, room_id, user_id, last_read_msg_id)
            # 用落库后的 GREATEST 位点算未读，避免乱序上报把已读状态算回退
            member = await RoomRepo.get_member(session, room_id, user_id)
            unread = await MessageRepo.count_after(
                session, room_id, member.last_read_msg_id if member else last_read_msg_id
            )
            members = await RoomRepo.list_members(session, room_id)
            audience = [m.user_id for m in members if m.user_id != user_id]
            await session.commit()

        try:
            await PushService.emit_event(
                "message.read",
                {
                    "room_id": str(room_id),
                    "user_id": str(user_id),
                    "last_read_msg_id": str(last_read_msg_id),
                },
                audience,
            )
        except Exception:
            logger.exception("push read failed", room_id=room_id)
        return unread
