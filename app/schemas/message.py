from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from app.models.enums import MessageType

if TYPE_CHECKING:
    from app.models.message import Message

MAX_CONTENT_LEN = 4096
_ID_PATTERN = r"^\d{1,19}$"


class MessageCreate(BaseModel):
    room_id: str = Field(pattern=_ID_PATTERN)
    type: int = MessageType.TEXT
    content: str | None = Field(default=None, max_length=MAX_CONTENT_LEN)
    reply_to_id: str | None = Field(default=None, pattern=_ID_PATTERN)
    extra: dict[str, Any] | None = None

    @property
    def room_id_int(self) -> int:
        return int(self.room_id)

    @property
    def reply_to_int(self) -> int | None:
        return int(self.reply_to_id) if self.reply_to_id else None


class MessageOut(BaseModel):
    id: str
    room_id: str
    from_uid: str
    type: int
    content: str | None
    extra: dict[str, Any] | None
    reply_to: str | None
    created_at: datetime

    @classmethod
    def from_model(cls, msg: "Message") -> "MessageOut":
        return cls(
            id=str(msg.id),
            room_id=str(msg.room_id),
            from_uid=str(msg.from_uid),
            type=msg.type,
            content=msg.content,
            extra=msg.extra,
            reply_to=str(msg.reply_to_id) if msg.reply_to_id else None,
            created_at=msg.created_at,
        )
