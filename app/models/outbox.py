"""本地消息表：把"写完消息"与"异步投递"绑在同一事务里，避免消息落库但推送丢失。

M2 只写不消费，M6 才会加轮询投递。
"""

from datetime import datetime

from sqlalchemy import BigInteger, Integer, SmallInteger, String, func
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.enums import OutboxStatus


class Outbox(Base):
    __tablename__ = "outbox"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    topic: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=OutboxStatus.PENDING)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
