from app.core.error_codes import ErrorCode
from app.core.exceptions import ApiError
from app.db import session_factory
from app.models.enums import MemberRole, RoomType
from app.models.friend import FriendRequestStatus
from app.models.user import User
from app.repositories.friend_repo import FriendRepo
from app.repositories.room_repo import RoomRepo
from app.repositories.user_repo import UserRepo
from app.schemas.friend import (
    BlockOut,
    FriendActionIn,
    FriendOut,
    FriendRequestOut,
    FriendUser,
)
from app.services.push_service import PushService


def _to_friend_user(u: User | None, uid: int) -> FriendUser:
    return FriendUser(
        id=str(uid),
        nickname=u.nickname if u else None,
        avatar_url=u.avatar_url if u else None,
    )


class FriendService:
    @staticmethod
    async def apply(*, user_id: int, to_uid: int, message: str | None) -> FriendRequestOut:
        """发好友申请：校验非自己/用户存在/非好友/未拉黑/无待处理申请，建 pending，推 WS"""
        async with session_factory() as session:
            if user_id == to_uid:
                raise ApiError(ErrorCode.ROOM_SELF_NOT_ALLOWED, "不能加自己为好友", 400)
            target = await UserRepo.get_by_id(session, to_uid)
            if target is None:
                raise ApiError(ErrorCode.USER_NOT_FOUND, "用户不存在", 404)
            if await FriendRepo.is_friend(session, user_id, to_uid):
                raise ApiError(ErrorCode.ALREADY_FRIEND, "已是好友", 409)
            if await FriendRepo.is_blocked_any(session, user_id, to_uid):
                raise ApiError(ErrorCode.USER_BLOCKED, "已被拉黑，无法申请", 403)
            if await FriendRepo.pending_between(session, user_id, to_uid) is not None:
                raise ApiError(ErrorCode.REQUEST_ALREADY_PENDING, "已有待处理申请", 409)

            req = await FriendRepo.create_request(
                session, from_uid=user_id, to_uid=to_uid, message=message
            )
            await session.commit()

            me = await UserRepo.get_by_id(session, user_id)
            await PushService.emit_event(
                "friend.request.new",
                {
                    "request_id": str(req.id),
                    "from_user": _to_friend_user(me, user_id).model_dump(mode="json"),
                    "message": req.message,
                    "created_at": req.created_at.isoformat(),
                },
                [to_uid],
            )
            return FriendRequestOut(
                id=str(req.id),
                from_user=_to_friend_user(me, user_id),
                to_user=_to_friend_user(target, to_uid),
                message=req.message,
                status=req.status,
                created_at=req.created_at,
            )

    @staticmethod
    async def list_requests(*, user_id: int, direction: str) -> list[FriendRequestOut]:
        """direction=received 收件箱 / sent 发件箱"""
        async with session_factory() as session:
            if direction == "sent":
                reqs = await FriendRepo.list_sent(session, user_id)
                others = [r.to_uid for r in reqs]
            else:
                reqs = await FriendRepo.list_received(session, user_id)
                others = [r.from_uid for r in reqs]
            users = await UserRepo.get_by_ids(session, others)
            out: list[FriendRequestOut] = []
            for r in reqs:
                if direction == "sent":
                    out.append(
                        FriendRequestOut(
                            id=str(r.id),
                            from_user=_to_friend_user(None, user_id),
                            to_user=_to_friend_user(users.get(r.to_uid), r.to_uid),
                            message=r.message,
                            status=r.status,
                            created_at=r.created_at,
                        )
                    )
                else:
                    out.append(
                        FriendRequestOut(
                            id=str(r.id),
                            from_user=_to_friend_user(users.get(r.from_uid), r.from_uid),
                            to_user=_to_friend_user(None, user_id),
                            message=r.message,
                            status=r.status,
                            created_at=r.created_at,
                        )
                    )
            return out

    @staticmethod
    async def handle_request(
        *, user_id: int, request_id: int, action: FriendActionIn
    ) -> str | None:
        """处理申请：accept 双向插好友 + 建单聊 + 推 accepted；reject 只改状态。返回 room_id 或 None"""
        async with session_factory() as session:
            req = await FriendRepo.get_request(session, request_id)
            if req is None or req.status != FriendRequestStatus.PENDING:
                raise ApiError(ErrorCode.REQUEST_NOT_FOUND, "申请不存在或已处理", 403)
            if req.to_uid != user_id:
                raise ApiError(ErrorCode.REQUEST_NOT_FOUND, "只能处理发给自己的申请", 403)

            if action.action == "accept":
                req.status = FriendRequestStatus.ACCEPTED
                await FriendRepo.create_both(session, req.from_uid, req.to_uid)
                # 同一事务建单聊：复用 RoomRepo，不另开 session（docs/11 M4 示例要求事务一致）
                existed = await RoomRepo.find_single(session, req.from_uid, req.to_uid)
                if existed is None:
                    room = await RoomRepo.create(session, type=RoomType.SINGLE)
                    await RoomRepo.add_member(
                        session, room_id=room.id, user_id=req.from_uid, role=MemberRole.MEMBER
                    )
                    await RoomRepo.add_member(
                        session, room_id=room.id, user_id=req.to_uid, role=MemberRole.MEMBER
                    )
                else:
                    room = existed
                await session.commit()

                await PushService.emit_event(
                    "friend.request.accepted",
                    {"room_id": str(room.id), "friend_id": str(user_id)},
                    [req.from_uid],
                )
                return str(room.id)
            else:
                req.status = FriendRequestStatus.REJECTED
                await session.commit()
                return None

    @staticmethod
    async def list_friends(user_id: int) -> list[FriendOut]:
        async with session_factory() as session:
            ids = await FriendRepo.get_friend_ids(session, user_id)
            users = await UserRepo.get_by_ids(session, ids)
            return [
                FriendOut(
                    user_id=str(i),
                    nickname=users[i].nickname if i in users else None,
                    avatar_url=users[i].avatar_url if i in users else None,
                )
                for i in ids
            ]

    @staticmethod
    async def delete_friend(*, user_id: int, friend_id: int) -> None:
        async with session_factory() as session:
            if not await FriendRepo.is_friend(session, user_id, friend_id):
                raise ApiError(ErrorCode.NOT_FRIEND, "不是好友", 404)
            await FriendRepo.delete_both(session, user_id, friend_id)
            await session.commit()

    @staticmethod
    async def block(*, user_id: int, blocked_id: int) -> None:
        async with session_factory() as session:
            if user_id == blocked_id:
                raise ApiError(ErrorCode.ROOM_SELF_NOT_ALLOWED, "不能拉黑自己", 400)
            if await UserRepo.get_by_id(session, blocked_id) is None:
                raise ApiError(ErrorCode.USER_NOT_FOUND, "用户不存在", 404)
            # 已拉黑则幂等，不报错
            if not await FriendRepo.is_blocked(session, user_id, blocked_id):
                await FriendRepo.block(session, user_id, blocked_id)
            await session.commit()

    @staticmethod
    async def unblock(*, user_id: int, blocked_id: int) -> None:
        async with session_factory() as session:
            await FriendRepo.unblock(session, user_id, blocked_id)
            await session.commit()

    @staticmethod
    async def list_blocks(user_id: int) -> list[BlockOut]:
        async with session_factory() as session:
            ids = await FriendRepo.list_blocked_ids(session, user_id)
            users = await UserRepo.get_by_ids(session, ids)
            return [
                BlockOut(
                    user_id=str(i),
                    nickname=users[i].nickname if i in users else None,
                    avatar_url=users[i].avatar_url if i in users else None,
                )
                for i in ids
            ]
