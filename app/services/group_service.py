from app.core.error_codes import ErrorCode
from app.core.exceptions import ApiError
from app.db import session_factory
from app.models.enums import MemberRole, MessageType, RoomType
from app.repositories.message_repo import MessageRepo
from app.repositories.room_repo import RoomRepo
from app.repositories.user_repo import UserRepo
from app.schemas.room import RoomOut
from app.services.push_service import PushService


class GroupService:
    @staticmethod
    async def create_group(
        *, user_id: int, name: str | None, member_ids: list[int], member_limit: int = 500
    ) -> RoomOut:
        """建群：room + owner member + 批量 member + 系统消息，同一事务；推 room.created"""
        async with session_factory() as session:
            owner = await UserRepo.get_by_id(session, user_id)
            if owner is None:
                raise ApiError(ErrorCode.USER_NOT_FOUND, "用户不存在", 404)

            targets = sorted(set(member_ids))
            # 建群者自动是 owner，被邀请列表里若含自己就去掉
            targets = [t for t in targets if t != user_id]

            limit = member_limit or 500
            # 成员上限 = 自己 + 被邀请的人（docs/11 M4：建群前 COUNT 校验）
            if len(targets) + 1 > limit:
                raise ApiError(ErrorCode.MEMBER_LIMIT_EXCEEDED, f"群成员上限 {limit}", 403)

            users = await UserRepo.get_by_ids(session, targets)
            if len(users) != len(targets):
                raise ApiError(ErrorCode.USER_NOT_FOUND, "有用户不存在", 404)

            room = await RoomRepo.create(
                session, type=RoomType.GROUP, name=name, owner_id=user_id, member_limit=limit
            )
            await RoomRepo.add_member(
                session, room_id=room.id, user_id=user_id, role=MemberRole.OWNER
            )
            for t in targets:
                await RoomRepo.add_member(
                    session, room_id=room.id, user_id=t, role=MemberRole.MEMBER
                )

            sys_msg = await MessageRepo.create(
                session,
                room_id=room.id,
                from_uid=user_id,
                type=MessageType.SYSTEM,
                content=f"{owner.nickname} 创建了群聊",
            )
            await RoomRepo.touch_last_msg(session, room, sys_msg.id)
            await session.commit()

            audience = [user_id] + targets
            await PushService.emit_event(
                "room.created",
                {
                    "room_id": str(room.id),
                    "name": name,
                    "owner_id": str(user_id),
                    "member_count": len(targets) + 1,
                },
                audience,
            )
            return RoomOut.from_model(room)

    @staticmethod
    async def add_members(*, user_id: int, room_id: int, user_ids: list[int]) -> bool:
        """加人：群主权限 + 成员上限校验；推 room.member.added 给全体成员"""
        async with session_factory() as session:
            room = await RoomRepo.assert_owner(session, room_id, user_id)

            targets = sorted(set(user_ids))
            users = await UserRepo.get_by_ids(session, targets)
            if len(users) != len(targets):
                raise ApiError(ErrorCode.USER_NOT_FOUND, "有用户不存在", 404)

            current = await RoomRepo.count_members(session, room_id)
            new = [t for t in targets if not await RoomRepo.is_member(session, room_id, t)]
            if current + len(new) > room.member_limit:
                raise ApiError(
                    ErrorCode.MEMBER_LIMIT_EXCEEDED,
                    f"群成员上限 {room.member_limit}",
                    403,
                )

            for t in new:
                await RoomRepo.add_member(
                    session, room_id=room_id, user_id=t, role=MemberRole.MEMBER
                )
            await session.commit()

            members = await RoomRepo.list_members(session, room_id)
            audience = [m.user_id for m in members]
            await PushService.emit_event(
                "room.member.added",
                {"room_id": str(room_id), "added": [str(t) for t in new]},
                audience,
            )
            return True

    @staticmethod
    async def leave_or_kick(*, user_id: int, room_id: int, target_uid: int) -> bool:
        """自己退群（owner 禁止）/ 群主踢人（不能踢群主）；推 room.member.removed"""
        async with session_factory() as session:
            await RoomRepo.assert_member(session, room_id, user_id)

            if target_uid == user_id:
                room = await RoomRepo.get_by_id(session, room_id)
                if room is not None and room.owner_id == user_id:
                    raise ApiError(
                        ErrorCode.GROUP_OWNER_CANNOT_LEAVE,
                        "群主不能直接退群，请先转让群主",
                        400,
                    )
                await RoomRepo.delete_member(session, room_id, user_id)
                removed = user_id
            else:
                await RoomRepo.assert_owner(session, room_id, user_id)
                if not await RoomRepo.is_member(session, room_id, target_uid):
                    raise ApiError(ErrorCode.NOT_ROOM_MEMBER, "对方不是群成员", 403)
                room = await RoomRepo.get_by_id(session, room_id)
                if room is not None and room.owner_id == target_uid:
                    raise ApiError(ErrorCode.NOT_GROUP_OWNER, "不能踢群主", 403)
                await RoomRepo.delete_member(session, room_id, target_uid)
                removed = target_uid

            await session.commit()

            members = await RoomRepo.list_members(session, room_id)
            audience = [m.user_id for m in members]
            await PushService.emit_event(
                "room.member.removed",
                {"room_id": str(room_id), "removed": str(removed)},
                audience,
            )
            return True
