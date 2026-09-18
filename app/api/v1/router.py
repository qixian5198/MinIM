from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.messages import router as messages_router
from app.api.v1.rooms import router as rooms_router
from app.api.v1.users import router as users_router
from app.core.response import ok

router = APIRouter()
router.include_router(auth_router)
router.include_router(users_router)
router.include_router(rooms_router)
router.include_router(messages_router)


@router.get("/ping")
async def ping():
    return ok(data={"pong": True})
