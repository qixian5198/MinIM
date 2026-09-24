from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from app.core.deps import CurrentUser
from app.core.response import ok
from app.services.group_service import GroupService


class GroupCreateIn(BaseModel):
    name: str | None = None
    member_ids: list[int] = Field(min_length=1)
    member_limit: int | None = None


class MemberAddIn(BaseModel):
    user_ids: list[int] = Field(min_length=1)


router = APIRouter(prefix="/rooms", tags=["groups"])


@router.post("/group")
async def create_group(body: GroupCreateIn, user: CurrentUser) -> JSONResponse:
    room = await GroupService.create_group(
        user_id=user.id,
        name=body.name,
        member_ids=body.member_ids,
        member_limit=body.member_limit,
    )
    return JSONResponse(status_code=201, content=ok(data=room.model_dump(mode="json")))


@router.post("/{room_id}/members")
async def add_members(room_id: int, body: MemberAddIn, user: CurrentUser) -> dict[str, Any]:
    await GroupService.add_members(user_id=user.id, room_id=room_id, user_ids=body.user_ids)
    return ok(data=None)


@router.delete("/{room_id}/members/{target_uid}")
async def leave_or_kick(room_id: int, target_uid: int, user: CurrentUser) -> dict[str, Any]:
    await GroupService.leave_or_kick(user_id=user.id, room_id=room_id, target_uid=target_uid)
    return ok(data=None)
