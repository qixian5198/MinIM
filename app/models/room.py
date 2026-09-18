from datetime import datetime

from sqlalchemy import BigInteger, Integer, SmallInteger, String, func
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.enums import MemberRole


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    type: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    name: Mapped[str | None] = mapped_column(String(100))
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    owner_id: Mapped[int | None] = mapped_column(BigInteger)
    last_msg_id: Mapped[int | None] = mapped_column(BigInteger)
    member_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=500)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    # 会话列表按 updated_at 倒序，所以发消息时靠 onupdate 顺带 touch，不必显式赋值
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class RoomMember(Base):
    __tablename__ = "room_members"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    room_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    role: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=MemberRole.MEMBER)
    # 已读位点放在成员上而非消息上：百人群一条消息只需存一份，而不是 100 份已读状态
    last_read_msg_id: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    joined_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
