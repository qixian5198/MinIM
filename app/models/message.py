from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, SmallInteger, Text, func
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.enums import MessageStatus, MessageType


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    room_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    from_uid: Mapped[int] = mapped_column(BigInteger, nullable=False)
    type: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=MessageType.TEXT)
    # TEXT 而非 VARCHAR：长度上限由 Pydantic 入参校验（4096），数据库不重复限制
    content: Mapped[str | None] = mapped_column(Text)
    reply_to_id: Mapped[int | None] = mapped_column(BigInteger)
    # 不同类型消息的扩展字段不同（图片尺寸/撤回人），用 JSONB 避免频繁加列
    extra: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=MessageStatus.NORMAL)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
