from app.core.error_codes import ErrorCode
from app.core.exceptions import ApiError
from app.db import session_factory
from app.models.enums import MemberRole, RoomType
from app.models.room import Room
from app.repositories.message_repo import MessageRepo
from app.repositories.room_repo import RoomRepo
from app.repositories.user_repo import UserRepo
from app.schemas.message import MessageOut
from app.schemas.room import MemberOut, RoomCard


class RoomService:
    @staticmethod
    async def get_or_create_single(*, user_id: int, target_uid: int) -> tuple[Room, bool]:
        """建/取单聊，返回 (room, 是否新建)。

        幂等靠"先查后建"：并发下可能查出两个会话，M4 之前先不处理，
        真要兜底得靠 (type, 成员集合) 的唯一约束，练手阶段不值得。
        """
        if user_id == target_uid:
            raise ApiError(ErrorCode.ROOM_SELF_NOT_ALLOWED, "不能和自己创建单聊", 400)

        async with session_factory() as session:
            if await UserRepo.get_by_id(session, target_uid) is None:
                raise ApiError(ErrorCode.USER_NOT_FOUND, "用户不存在", 404)

            existed = await RoomRepo.find_single(session, user_id, target_uid)
            if existed is not None:
                return existed, False

            try:
                room = await RoomRepo.create(session, type=RoomType.SINGLE)
                # 单聊两个人对等，都是普通成员，没有群主
                await RoomRepo.add_member(
                    session, room_id=room.id, user_id=user_id, role=MemberRole.MEMBER
                )
                await RoomRepo.add_member(
                    session, room_id=room.id, user_id=target_uid, role=MemberRole.MEMBER
                )
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            return room, True

    @staticmethod
    async def list_my_rooms(user_id: int) -> list[RoomCard]:
        async with session_factory() as session:
            rows = await RoomRepo.list_for_user(session, user_id)
            last_ids = [r.last_msg_id for r, _ in rows if r.last_msg_id]
            last_msgs = await MessageRepo.get_by_ids(session, last_ids)

            cards: list[RoomCard] = []
            for room, last_read in rows:
                last_id = room.last_msg_id
                last_msg = last_msgs.get(last_id) if last_id else None
                unread = (
                    await MessageRepo.count_after(session, room.id, last_read) if last_id else 0
                )
                cards.append(
                    RoomCard(
                        id=str(room.id),
                        type=room.type,
                        name=room.name,
                        avatar_url=room.avatar_url,
                        last_message=MessageOut.from_model(last_msg) if last_msg else None,
                        unread_count=unread,
                        updated_at=room.updated_at,
                    )
                )
            return cards

    @staticmethod
    async def list_members(*, user_id: int, room_id: int) -> list[MemberOut]:
        async with session_factory() as session:
            await RoomRepo.assert_member(session, room_id, user_id)
            members = await RoomRepo.list_members(session, room_id)
            users = await UserRepo.get_by_ids(session, [m.user_id for m in members])
            return [
                MemberOut(
                    user_id=str(m.user_id),
                    nickname=users[m.user_id].nickname if m.user_id in users else None,
                    avatar_url=users[m.user_id].avatar_url if m.user_id in users else None,
                    role=m.role,
                )
                for m in members
            ]
