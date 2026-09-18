from sqlalchemy.exc import IntegrityError

from app.core.error_codes import ErrorCode
from app.core.exceptions import ApiError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db import session_factory
from app.models.user import User
from app.repositories.user_repo import UserRepo
from app.schemas.user import AuthOut, PatchMeIn, UserOut


class UserService:
    @staticmethod
    async def register(*, username: str, password: str, nickname: str | None) -> User:
        async with session_factory() as session:
            try:
                if await UserRepo.get_by_username(session, username) is not None:
                    raise ApiError(ErrorCode.USERNAME_TAKEN, "用户名已存在", 409)
                user = await UserRepo.create(
                    session,
                    username=username,
                    password_hash=hash_password(password),
                    nickname=nickname,
                )
                await session.commit()
            except IntegrityError:
                await session.rollback()
                raise ApiError(ErrorCode.USERNAME_TAKEN, "用户名已存在", 409) from None
            except ApiError:
                await session.rollback()
                raise
        return user

    @staticmethod
    async def login(*, username: str, password: str) -> AuthOut:
        async with session_factory() as session:
            user = await UserRepo.get_by_username(session, username)
            if user is None or not verify_password(password, user.password_hash):
                raise ApiError(ErrorCode.PASSWORD_WRONG, "密码错误", 401)
            if user.status != 0:
                raise ApiError(ErrorCode.USER_DISABLED, "账号已禁用", 403)
            return await UserService._auth_out(user)

    @staticmethod
    async def refresh(*, refresh_token: str) -> AuthOut:
        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh":
            raise ApiError(ErrorCode.REFRESH_TOKEN_INVALID, "refresh token 无效", 401)
        user = await UserService.get_user(int(payload["sub"]))
        if user is None:
            raise ApiError(ErrorCode.USER_NOT_FOUND, "用户不存在", 404)
        if user.status != 0:
            raise ApiError(ErrorCode.USER_DISABLED, "账号已禁用", 403)
        return await UserService._auth_out(user)

    @staticmethod
    async def get_user(user_id: int) -> User | None:
        async with session_factory() as session:
            return await UserRepo.get_by_id(session, user_id)

    @staticmethod
    async def me(user: User) -> UserOut:
        return UserOut.from_model(user)

    @staticmethod
    async def update_me(user: User, patch: PatchMeIn) -> User:
        async with session_factory() as session:
            db_user = await UserRepo.get_by_id(session, user.id)
            if db_user is None:
                raise ApiError(ErrorCode.USER_NOT_FOUND, "用户不存在", 404)
            await UserRepo.update_profile(
                session,
                db_user,
                nickname=patch.nickname,
                avatar_url=patch.avatar_url,
            )
            await session.commit()
            return db_user

    @staticmethod
    async def search_users(keyword: str) -> list[User]:
        async with session_factory() as session:
            return await UserRepo.search_by_keyword(session, keyword)

    @staticmethod
    async def _auth_out(user: User) -> AuthOut:
        from app.core.config import settings

        return AuthOut(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
            expires_in=settings.JWT_EXPIRE_DAYS * 86400,
            user=UserOut.from_model(user),
        )
