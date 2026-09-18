from typing import Any

from fastapi import APIRouter, Query

from app.core.deps import CurrentUser
from app.core.response import ok
from app.schemas.message import MarkIn, MessageCreate, MessageOut
from app.services.message_service import MessageService

router = APIRouter(tags=["messages"])


@router.post("/messages", status_code=201)
async def send_message(body: MessageCreate, user: CurrentUser) -> dict[str, Any]:
    msg = await MessageService.send(
        user_id=user.id,
        room_id=body.room_id_int,
        type=body.type,
        content=body.content,
        reply_to_id=body.reply_to_int,
        extra=body.extra,
    )
    return ok(data=MessageOut.from_model(msg).model_dump(mode="json"))


@router.get("/rooms/{room_id}/messages")
async def list_messages(
    room_id: int,
    user: CurrentUser,
    cursor: str | None = Query(default=None, pattern=r"^\d+$"),
    limit: int = Query(default=20, ge=1, le=50),
) -> dict[str, Any]:
    items, next_cursor, has_more = await MessageService.list_messages(
        user_id=user.id,
        room_id=room_id,
        cursor=int(cursor) if cursor else None,
        limit=limit,
    )
    return ok(
        data={
            "list": [MessageOut.from_model(m).model_dump(mode="json") for m in items],
            "next_cursor": next_cursor,
            "has_more": has_more,
        }
    )


@router.post("/messages/{msg_id}/recall")
async def recall_message(msg_id: int, user: CurrentUser) -> dict[str, Any]:
    await MessageService.recall(user_id=user.id, msg_id=msg_id)
    return ok(data=None)


@router.post("/messages/{msg_id}/marks")
async def mark_message(msg_id: int, body: MarkIn, user: CurrentUser) -> dict[str, Any]:
    out = await MessageService.mark(user_id=user.id, msg_id=msg_id, mark_type=body.mark_type)
    return ok(data=out.model_dump(mode="json"))
