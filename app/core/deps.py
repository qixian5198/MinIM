from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.error_codes import ErrorCode
from app.core.exceptions import ApiError
from app.core.security import decode_token
from app.db import get_session
from app.models.user import User
from app.repositories.user_repo import UserRepo

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)], session: SessionDep
) -> User:
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise ApiError(ErrorCode.TOKEN_INVALID, "token 无效", 401)
    user = await UserRepo.get_by_id(session, int(payload["sub"]))
    if user is None:
        raise ApiError(ErrorCode.USER_NOT_FOUND, "用户不存在", 404)
    if user.status != 0:
        raise ApiError(ErrorCode.USER_DISABLED, "账号已禁用", 403)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
