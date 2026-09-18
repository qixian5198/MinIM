from fastapi import APIRouter, Query

from app.core.deps import CurrentUser
from app.core.response import ok
from app.schemas.message import MessageCreate, MessageOut
from app.services.message_service import MessageService

router = APIRouter(tags=["messages"])


@router.post("/messages", status_code=201)
async def send_message(body: MessageCreate, user: CurrentUser) -> dict:
    msg = await MessageService.send(
        user_id=user.id,
        room_id=body.room_id_int,
        type=body.type,
        content=body.content,
        reply_to_id=body.reply_to_int,
        extra=body.extra,
    )
    return ok(data=MessageOut.from_model(msg).model_dump())


@router.get("/rooms/{room_id}/messages")
async def list_messages(
    room_id: int,
    user: CurrentUser,
    cursor: str | None = Query(default=None, pattern=r"^\d+$"),
    limit: int = Query(default=20, ge=1, le=50),
):
    items, next_cursor, has_more = await MessageService.list_messages(
        user_id=user.id,
        room_id=room_id,
        cursor=int(cursor) if cursor else None,
        limit=limit,
    )
    return ok(
        data={
            "list": [MessageOut.from_model(m).model_dump() for m in items],
            "next_cursor": next_cursor,
            "has_more": has_more,
        }
    )
