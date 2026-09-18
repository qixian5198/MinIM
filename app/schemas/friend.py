from datetime import datetime

from pydantic import BaseModel, Field

_ID_PATTERN = r"^\d{1,19}$"


class FriendRequestIn(BaseModel):
    to_uid: str = Field(pattern=_ID_PATTERN)
    message: str | None = Field(default=None, max_length=200)

    @property
    def to_uid_int(self) -> int:
        return int(self.to_uid)


class FriendActionIn(BaseModel):
    action: str  # accept | reject


class FriendUser(BaseModel):
    id: str
    nickname: str | None = None
    avatar_url: str | None = None


class FriendRequestOut(BaseModel):
    id: str
    from_user: FriendUser
    to_user: FriendUser
    message: str | None
    status: int
    created_at: datetime


class FriendOut(BaseModel):
    user_id: str
    nickname: str | None = None
    avatar_url: str | None = None
    remark: str | None = None


class BlockOut(BaseModel):
    user_id: str
    nickname: str | None = None
    avatar_url: str | None = None
