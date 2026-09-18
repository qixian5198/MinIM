from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepo:
    """用户数据访问，方法都是 static，FastAPI 侧按需组合 session 传入。"""

    @staticmethod
    async def get_by_id(session: AsyncSession, user_id: int) -> User | None:
        return await session.get(User, user_id)

    @staticmethod
    async def get_by_username(session: AsyncSession, username: str) -> User | None:
        result = await session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        session: AsyncSession, *, username: str, password_hash: str, nickname: str | None
    ) -> User:
        user = User(
            username=username,
            password_hash=password_hash,
            nickname=nickname or username,
        )
        session.add(user)
        await session.flush()
        return user

    @staticmethod
    async def update_profile(
        session: AsyncSession,
        user: User,
        *,
        nickname: str | None = None,
        avatar_url: str | None = None,
    ) -> User:
        if nickname is not None:
            user.nickname = nickname
        if avatar_url is not None:
            user.avatar_url = avatar_url
        await session.flush()
        return user

    @staticmethod
    async def search_by_keyword(session: AsyncSession, keyword: str, limit: int = 20) -> list[User]:
        pattern = f"%{keyword}%"
        result = await session.execute(
            select(User)
            .where(User.username.ilike(pattern) | User.nickname.ilike(pattern))
            .order_by(User.id)
            .limit(limit)
        )
        return list(result.scalars().all())
