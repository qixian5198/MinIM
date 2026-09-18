from fastapi import APIRouter, status

from app.core.response import ok
from app.schemas.user import LoginIn, RefreshIn, RegisterIn, UserOut
from app.services.user_service import UserService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(body: RegisterIn):
    user = await UserService.register(
        username=body.username, password=body.password, nickname=body.nickname
    )
    return ok(data=UserOut.from_model(user))


@router.post("/login")
async def login(body: LoginIn):
    auth = await UserService.login(username=body.username, password=body.password)
    return ok(data=auth.model_dump())


@router.post("/refresh")
async def refresh(body: RefreshIn):
    auth = await UserService.refresh(refresh_token=body.refresh_token)
    return ok(data=auth.model_dump())
