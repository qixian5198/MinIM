import json
import time
from typing import Any

import structlog

from app.core.redis import incr, lpush, lrange, ltrim
from app.db import session_factory
from app.repositories.message_repo import MessageRepo
from app.repositories.outbox_repo import OutboxRepo
from app.repositories.room_repo import RoomRepo
from app.schemas.message import MessageOut
from app.ws.manager import manager

logger = structlog.get_logger()

SEQ_KEY = "minim:seq"
EVENT_KEY = "minim:events"
# 断线补偿只保留最近这么多条（docs/06 §9.5）
MAX_EVENTS = 1000


class PushService:
    @staticmethod
    async def dispatch(msg_id: int, outbox_id: int) -> None:
        """把一条新消息推给会话里所有在线的人（包括发送者自己的其他标签页）"""
        async with session_factory() as session:
            msg = await MessageRepo.get_by_id(session, msg_id)
            if msg is None:
                await OutboxRepo.mark_sent(session, outbox_id)
                await session.commit()
                return

            members = await RoomRepo.list_members(session, msg.room_id)
            audience = [m.user_id for m in members]
            event = await PushService._emit(
                type="message.new",
                # mode="json"：默认 model_dump() 会保留 datetime 对象，json.dumps 会直接炸
                data=MessageOut.from_model(msg).model_dump(mode="json"),
                audience=audience,
            )
            for uid in audience:
                await manager.send_to_user(uid, event)

            await OutboxRepo.mark_sent(session, outbox_id)
            await session.commit()

    @staticmethod
    async def emit_event(event_type: str, data: dict[str, Any], audience: list[int]) -> None:
        """通用的"写事件 + 实时推给在线 audience"入口：好友/群聊等非消息事件复用。

        与 dispatch 的区别：dispatch 从已落库消息反查 audience，这里 audience 直接给。
        """
        event = await PushService._emit(type=event_type, data=data, audience=audience)
        for uid in audience:
            await manager.send_to_user(uid, event)

    @staticmethod
    async def replay(user_id: int, last_seq: int) -> list[dict[str, Any]]:
        """补发 last_seq 之后、且属于该用户的事件"""
        raw = await lrange(EVENT_KEY, 0, MAX_EVENTS - 1)
        events: list[dict[str, Any]] = []
        for item in raw:  # lpush 存，最新在前
            event = json.loads(item)
            if event["seq"] <= last_seq:
                break  # seq 递减，后面都是旧的
            if user_id in event["to"]:
                events.append({k: v for k, v in event.items() if k != "to"})
        events.reverse()
        return events

    @staticmethod
    async def _emit(type: str, data: dict[str, Any], audience: list[int]) -> dict[str, Any]:
        # seq 全局递增，客户端靠它判断"我漏了哪些"
        seq = await incr(SEQ_KEY)
        event = {
            "type": type,
            "seq": seq,
            "data": data,
            "ts": int(time.time() * 1000),
            "to": audience,
        }
        await lpush(EVENT_KEY, json.dumps(event))
        await ltrim(EVENT_KEY, 0, MAX_EVENTS - 1)
        # to 只是服务端用来过滤补发范围的，不下发给客户端
        return {k: v for k, v in event.items() if k != "to"}
