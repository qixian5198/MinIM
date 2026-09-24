from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.friend import Block, FriendRequest, FriendRequestStatus, Friendship


class FriendRepo:
    """好友 / 申请 / 拉黑的数据访问，方法都是 static，按需组合 session 传入。"""

    # ---- 好友关系 ----
    @staticmethod
    async def is_friend(session: AsyncSession, a: int, b: int) -> bool:
        stmt = select(Friendship.id).where(Friendship.user_id == a, Friendship.friend_id == b)
        return (await session.execute(stmt)).scalar_one_or_none() is not None

    @staticmethod
    async def get_friend_ids(session: AsyncSession, user_id: int) -> list[int]:
        stmt = select(Friendship.friend_id).where(Friendship.user_id == user_id)
        return list((await session.execute(stmt)).scalars().all())

    @staticmethod
    async def create_both(session: AsyncSession, a: int, b: int) -> None:
        # 双向两条：查列表只查 user_id=me，避免 OR 查询（docs/05 §4.2）
        session.add(Friendship(user_id=a, friend_id=b))
        session.add(Friendship(user_id=b, friend_id=a))
        await session.flush()

    @staticmethod
    async def delete_both(session: AsyncSession, a: int, b: int) -> None:
        # 双向两条记录一起删
        await session.execute(
            delete(Friendship).where(Friendship.user_id == a, Friendship.friend_id == b)
        )
        await session.execute(
            delete(Friendship).where(Friendship.user_id == b, Friendship.friend_id == a)
        )

    # ---- 好友申请 ----
    @staticmethod
    async def create_request(
        session: AsyncSession, *, from_uid: int, to_uid: int, message: str | None
    ) -> FriendRequest:
        req = FriendRequest(
            from_uid=from_uid, to_uid=to_uid, message=message, status=FriendRequestStatus.PENDING
        )
        session.add(req)
        await session.flush()
        return req

    @staticmethod
    async def get_request(session: AsyncSession, request_id: int) -> FriendRequest | None:
        return await session.get(FriendRequest, request_id)

    @staticmethod
    async def pending_between(session: AsyncSession, a: int, b: int) -> FriendRequest | None:
        """两人之间是否有任一方发起的待处理申请"""
        stmt = select(FriendRequest).where(
            FriendRequest.status == FriendRequestStatus.PENDING,
            or_(
                and_(FriendRequest.from_uid == a, FriendRequest.to_uid == b),
                and_(FriendRequest.from_uid == b, FriendRequest.to_uid == a),
            ),
        )
        return (await session.execute(stmt)).scalars().first()

    @staticmethod
    async def list_received(
        session: AsyncSession,
        user_id: int,
        status: FriendRequestStatus = FriendRequestStatus.PENDING,
    ) -> list[FriendRequest]:
        stmt = (
            select(FriendRequest)
            .where(FriendRequest.to_uid == user_id, FriendRequest.status == status)
            .order_by(FriendRequest.id.desc())
        )
        return list((await session.execute(stmt)).scalars().all())

    @staticmethod
    async def list_sent(session: AsyncSession, user_id: int) -> list[FriendRequest]:
        stmt = (
            select(FriendRequest)
            .where(FriendRequest.from_uid == user_id)
            .order_by(FriendRequest.id.desc())
        )
        return list((await session.execute(stmt)).scalars().all())

    # ---- 拉黑（单向） ----
    @staticmethod
    async def is_blocked(session: AsyncSession, a: int, b: int) -> bool:
        """a 是否拉黑了 b"""
        stmt = select(Block.id).where(Block.user_id == a, Block.blocked_id == b)
        return (await session.execute(stmt)).scalar_one_or_none() is not None

    @staticmethod
    async def is_blocked_any(session: AsyncSession, a: int, b: int) -> bool:
        """任一方向被拉黑都算（申请/建群时用于拦截）"""
        stmt = select(Block.id).where(
            or_(
                and_(Block.user_id == a, Block.blocked_id == b),
                and_(Block.user_id == b, Block.blocked_id == a),
            )
        )
        return (await session.execute(stmt)).scalar_one_or_none() is not None

    @staticmethod
    async def block(session: AsyncSession, a: int, b: int) -> None:
        session.add(Block(user_id=a, blocked_id=b))
        await session.flush()

    @staticmethod
    async def unblock(session: AsyncSession, a: int, b: int) -> None:
        await session.execute(delete(Block).where(Block.user_id == a, Block.blocked_id == b))

    @staticmethod
    async def list_blocked_ids(session: AsyncSession, user_id: int) -> list[int]:
        stmt = select(Block.blocked_id).where(Block.user_id == user_id)
        return list((await session.execute(stmt)).scalars().all())
