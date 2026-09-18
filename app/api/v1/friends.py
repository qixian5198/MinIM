from typing import Any

from fastapi import APIRouter, Query

from app.core.deps import CurrentUser
from app.core.response import ok
from app.schemas.friend import (
    BlockIn,
    FriendActionIn,
    FriendRequestIn,
)
from app.services.friend_service import FriendService

router = APIRouter(prefix="/friends", tags=["friends"])


@router.post("/requests")
async def create_request(body: FriendRequestIn, user: CurrentUser) -> dict[str, Any]:
    out = await FriendService.apply(user_id=user.id, to_uid=body.to_uid_int, message=body.message)
    return ok(data=out.model_dump(mode="json"))


@router.get("/requests")
async def list_requests(
    user: CurrentUser, type: str = Query(default="received")
) -> dict[str, Any]:
    direction = "sent" if type == "sent" else "received"
    out = await FriendService.list_requests(user_id=user.id, direction=direction)
    return ok(data={"list": [o.model_dump(mode="json") for o in out]})


@router.put("/requests/{request_id}")
async def handle_request(
    request_id: int, body: FriendActionIn, user: CurrentUser
) -> dict[str, Any]:
    room_id = await FriendService.handle_request(
        user_id=user.id, request_id=request_id, action=body
    )
    return ok(data={"room_id": room_id})


@router.get("")
async def list_friends(user: CurrentUser) -> dict[str, Any]:
    out = await FriendService.list_friends(user.id)
    return ok(data={"list": [o.model_dump(mode="json") for o in out]})


@router.delete("/{friend_id}")
async def delete_friend(friend_id: int, user: CurrentUser) -> dict[str, Any]:
    await FriendService.delete_friend(user_id=user.id, friend_id=friend_id)
    return ok(data=None)


@router.post("/blocks")
async def block_user(body: BlockIn, user: CurrentUser) -> dict[str, Any]:
    await FriendService.block(user_id=user.id, blocked_id=body.uid_int)
    return ok(data=None)


@router.delete("/blocks/{uid}")
async def unblock_user(uid: int, user: CurrentUser) -> dict[str, Any]:
    await FriendService.unblock(user_id=user.id, blocked_id=uid)
    return ok(data=None)


@router.get("/blocks")
async def list_blocks(user: CurrentUser) -> dict[str, Any]:
    out = await FriendService.list_blocks(user.id)
    return ok(data={"list": [o.model_dump(mode="json") for o in out]})
