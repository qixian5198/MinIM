from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.error_codes import ErrorCode
from app.core.exceptions import ApiError
from app.models.enums import MemberRole, RoomType
from app.models.room import Room, RoomMember


class RoomRepo:
    @staticmethod
    async def get_by_id(session: AsyncSession, room_id: int) -> Room | None:
        return await session.get(Room, room_id)

    @staticmethod
    async def is_member(session: AsyncSession, room_id: int, user_id: int) -> bool:
        stmt = select(RoomMember.id).where(
            RoomMember.room_id == room_id, RoomMember.user_id == user_id
        )
        return (await session.execute(stmt)).scalar_one_or_none() is not None

    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        type: RoomType,
        name: str | None = None,
        owner_id: int | None = None,
        member_limit: int = 500,
    ) -> Room:
        room = Room(type=type, name=name, owner_id=owner_id, member_limit=member_limit)
        session.add(room)
        await session.flush()
        return room

    @staticmethod
    async def add_member(
        session: AsyncSession,
        *,
        room_id: int,
        user_id: int,
        role: MemberRole = MemberRole.MEMBER,
    ) -> RoomMember:
        member = RoomMember(room_id=room_id, user_id=user_id, role=role)
        session.add(member)
        await session.flush()
        return member

    @staticmethod
    async def find_single(session: AsyncSession, user_a: int, user_b: int) -> Room | None:
        """查两人之间已有的单聊（建单聊幂等的前提）"""
        a = select(RoomMember.room_id).where(RoomMember.user_id == user_a)
        b = select(RoomMember.room_id).where(RoomMember.user_id == user_b)
        stmt = select(Room).where(
            Room.type == RoomType.SINGLE,
            Room.id.in_(a),
            Room.id.in_(b),
        )
        return (await session.execute(stmt)).scalars().first()

    @staticmethod
    async def list_for_user(
        session: AsyncSession, user_id: int, limit: int = 100
    ) -> list[tuple[Room, int]]:
        """我的会话列表，按最后活跃倒序；第二项是自己的已读位点"""
        stmt = (
            select(Room, RoomMember.last_read_msg_id)
            .join(RoomMember, RoomMember.room_id == Room.id)
            .where(RoomMember.user_id == user_id)
            .order_by(Room.updated_at.desc(), Room.id.desc())
            .limit(limit)
        )
        rows = (await session.execute(stmt)).all()
        return [(row[0], row[1]) for row in rows]

    @staticmethod
    async def list_members(session: AsyncSession, room_id: int) -> list[RoomMember]:
        stmt = select(RoomMember).where(RoomMember.room_id == room_id).order_by(RoomMember.id)
        return list((await session.execute(stmt)).scalars().all())

    @staticmethod
    async def touch_last_msg(session: AsyncSession, room: Room, msg_id: int) -> None:
        # 顺带更新 last_msg_id；updated_at 由模型的 onupdate 自动推进，
        # 会话列表因此能按"最后活跃"排序
        room.last_msg_id = msg_id
        await session.flush()

    @staticmethod
    async def assert_member(session: AsyncSession, room_id: int, user_id: int) -> Room:
        room = await RoomRepo.get_by_id(session, room_id)
        if room is None:
            raise ApiError(ErrorCode.ROOM_NOT_FOUND, "会话不存在", 404)
        if not await RoomRepo.is_member(session, room_id, user_id):
            raise ApiError(ErrorCode.NOT_ROOM_MEMBER, "不是该会话成员", 403)
        return room

    @staticmethod
    async def count_members(session: AsyncSession, room_id: int) -> int:
        """群聊加人前校验成员上限用"""
        stmt = select(func.count()).select_from(RoomMember).where(RoomMember.room_id == room_id)
        return int((await session.execute(stmt)).scalar_one())

    @staticmethod
    async def assert_owner(session: AsyncSession, room_id: int, user_id: int) -> Room:
        """群主专属操作（加人/踢人/改设置）前的权限校验"""
        room = await RoomRepo.get_by_id(session, room_id)
        if room is None:
            raise ApiError(ErrorCode.ROOM_NOT_FOUND, "会话不存在", 404)
        if room.type != RoomType.GROUP:
            raise ApiError(ErrorCode.NOT_GROUP_OWNER, "不是群聊", 403)
        if room.owner_id != user_id:
            raise ApiError(ErrorCode.NOT_GROUP_OWNER, "仅群主可操作", 403)
        return room

    @staticmethod
    async def delete_member(session: AsyncSession, room_id: int, user_id: int) -> None:
        """踢人 / 退群：直接按条件删 room_member"""
        await session.execute(
            delete(RoomMember).where(RoomMember.room_id == room_id, RoomMember.user_id == user_id)
        )
