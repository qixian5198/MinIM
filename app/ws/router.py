import json
import time
from typing import Any

import structlog
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.exceptions import ApiError
from app.core.security import decode_token
from app.db import session_factory
from app.models.user import User
from app.repositories.user_repo import UserRepo
from app.services.push_service import PushService
from app.ws.manager import manager

logger = structlog.get_logger()

router = APIRouter(tags=["ws"])

WS_CLOSE_AUTH_FAILED = 4001


async def _user_from_token(token: str) -> User | None:
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            return None
        user_id = int(payload["sub"])
    except (ApiError, KeyError, ValueError, TypeError):
        return None

    async with session_factory() as session:
        user = await UserRepo.get_by_id(session, user_id)
    if user is None or user.status != 0:
        return None
    return user


@router.websocket("/ws")
async def websocket_endpoint(
    ws: WebSocket,
    token: str = Query(...),
    last_seq: int = Query(default=0),
) -> None:
    user = await _user_from_token(token)
    if user is None:
        # 必须在 accept 之前关：一旦握手完成再关，客户端只能看到"连接被关闭"，
        # 分不清是鉴权失败还是网络问题
        await ws.close(code=WS_CLOSE_AUTH_FAILED)
        return

    await manager.connect(user.id, ws)
    logger.info("ws connected", user_id=user.id, last_seq=last_seq)
    try:
        for event in await PushService.replay(user.id, last_seq):
            await ws.send_json(event)
        await ws.send_json(_envelope("sync.done", {}))

        while True:
            manager.touch(ws)
            raw = await ws.receive_text()
            try:
                frame = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if frame.get("type") == "ping":
                await ws.send_json(_envelope("pong", {}))
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("ws loop crashed", user_id=user.id)
        raise
    finally:
        manager.disconnect(user.id, ws)
        logger.info("ws disconnected", user_id=user.id)


def _envelope(type: str, data: dict[str, Any]) -> dict[str, Any]:
    return {"type": type, "data": data, "ts": int(time.time() * 1000)}
