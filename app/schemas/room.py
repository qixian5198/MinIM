from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from app.schemas.message import MessageOut

if TYPE_CHECKING:
    from app.models.room import Room

_ID_PATTERN = r"^\d{1,19}$"


class SingleRoomIn(BaseModel):
    target_uid: str = Field(pattern=_ID_PATTERN)

    @property
    def target_uid_int(self) -> int:
        return int(self.target_uid)


class RoomOut(BaseModel):
    id: str
    type: int
    name: str | None
    avatar_url: str | None

    @classmethod
    def from_model(cls, room: "Room") -> "RoomOut":
        return cls(
            id=str(room.id),
            type=room.type,
            name=room.name,
            avatar_url=room.avatar_url,
        )


class RoomCard(BaseModel):
    """会话列表一项：会话 + 最后一条消息 + 我的未读数"""

    id: str
    type: int
    name: str | None
    avatar_url: str | None
    last_message: MessageOut | None
    unread_count: int
    updated_at: datetime


class MemberOut(BaseModel):
    user_id: str
    nickname: str | None
    avatar_url: str | None
    role: int
