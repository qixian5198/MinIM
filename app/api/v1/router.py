from fastapi import APIRouter

from app.core.response import ok

router = APIRouter()


@router.get("/ping")
async def ping():
    return ok(data={"pong": True})
