from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.users import router as users_router
from app.core.response import ok

router = APIRouter()
router.include_router(auth_router)
router.include_router(users_router)


@router.get("/ping")
async def ping():
    return ok(data={"pong": True})
