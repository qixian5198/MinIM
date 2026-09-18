from datetime import datetime

from sqlalchemy import BigInteger, SmallInteger, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class MessageMark(Base):
    """消息点赞/点踩（marks）。

    按 docs/11 M5：同 (msg_id, user_id, mark_type) 唯一，重复提交同类型 = 取消（幂等切换）。
    """

    __tablename__ = "message_marks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    msg_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mark_type: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        # 一人对一条消息的同一种 mark 只能有一条；切换靠"删旧插新"
        UniqueConstraint("msg_id", "user_id", "mark_type", name="uq_msg_mark"),
    )
