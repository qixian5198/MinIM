import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


def _validate_password(password: str) -> str:
    if len(password) < 8 or len(password) > 32:
        raise ValueError("密码长度需 8-32 位")
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise ValueError("密码需同时包含字母和数字")
    return password


class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=20, pattern=r"^[A-Za-z0-9_]+$")
    password: str
    nickname: str | None = Field(default=None, min_length=1, max_length=50)

    @field_validator("password")
    @classmethod
    def check_strength(cls, v: str) -> str:
        return _validate_password(v)


class LoginIn(BaseModel):
    username: str
    password: str


class RefreshIn(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    id: str
    username: str
    nickname: str | None
    avatar_url: str | None

    @classmethod
    def from_model(cls, user) -> "UserOut":
        return cls(
            id=str(user.id),
            username=user.username,
            nickname=user.nickname,
            avatar_url=user.avatar_url,
        )


class MeOut(UserOut):
    created_at: datetime

    @classmethod
    def from_model(cls, user) -> "MeOut":
        return cls(
            id=str(user.id),
            username=user.username,
            nickname=user.nickname,
            avatar_url=user.avatar_url,
            created_at=user.created_at,
        )


class AuthOut(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    user: UserOut


class PatchMeIn(BaseModel):
    nickname: str | None = Field(default=None, min_length=1, max_length=50)
    avatar_url: str | None = Field(default=None, max_length=500)
