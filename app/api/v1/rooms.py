from typing import Any

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from app.core.deps import CurrentUser
from app.core.response import ok
from app.schemas.message import ReadReceiptIn
from app.schemas.room import RoomOut, SingleRoomIn
from app.services.message_service import MessageService
from app.services.room_service import RoomService

router = APIRouter(prefix="/rooms", tags=["rooms"])


@router.get("")
async def list_rooms(user: CurrentUser) -> dict[str, Any]:
    cards = await RoomService.list_my_rooms(user.id)
    return ok(data={"list": [c.model_dump(mode="json") for c in cards]})


@router.post("/single")
async def create_single(body: SingleRoomIn, user: CurrentUser, request: Request) -> JSONResponse:
    room, created = await RoomService.get_or_create_single(
        user_id=user.id, target_uid=body.target_uid_int
    )
    # 幂等接口：新建返回 201，命中已有会话返回 200（docs/06 §5）
    body_data = ok(
        data=RoomOut.from_model(room).model_dump(mode="json"),
        request_id=getattr(request.state, "request_id", None),
    )
    return JSONResponse(status_code=201 if created else 200, content=body_data)


@router.get("/{room_id}/members")
async def list_members(room_id: int, user: CurrentUser) -> dict[str, Any]:
    members = await RoomService.list_members(user_id=user.id, room_id=room_id)
    return ok(data={"list": [m.model_dump(mode="json") for m in members]})


@router.post("/{room_id}/read")
async def report_read(room_id: int, body: ReadReceiptIn, user: CurrentUser) -> dict[str, Any]:
    unread = await MessageService.report_read(
        user_id=user.id, room_id=room_id, last_read_msg_id=body.last_read_msg_id_int
    )
    return ok(data={"unread_count": unread})
