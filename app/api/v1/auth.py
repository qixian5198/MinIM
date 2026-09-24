from typing import Any

from fastapi import APIRouter, status

from app.core.response import ok
from app.schemas.user import LoginIn, RefreshIn, RegisterIn, UserOut
from app.security.rate_limit import rate_limit
from app.services.user_service import UserService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
@rate_limit(name="register", key="ip", limit=3, window=60)
async def register(body: RegisterIn) -> dict[str, Any]:
    user = await UserService.register(
        username=body.username, password=body.password, nickname=body.nickname
    )
    return ok(data=UserOut.from_model(user))


@router.post("/login")
@rate_limit(name="login", key="ip", limit=10, window=60)
async def login(body: LoginIn) -> dict[str, Any]:
    auth = await UserService.login(username=body.username, password=body.password)
    return ok(data=auth.model_dump())


@router.post("/refresh")
async def refresh(body: RefreshIn) -> dict[str, Any]:
    auth = await UserService.refresh(refresh_token=body.refresh_token)
    return ok(data=auth.model_dump())
