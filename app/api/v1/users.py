from typing import Any

from fastapi import APIRouter, Query

from app.core.deps import CurrentUser
from app.core.response import ok
from app.schemas.user import MeOut, PatchMeIn, UserOut
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me")
async def me(user: CurrentUser) -> dict[str, Any]:
    return ok(data=MeOut.from_model(user))


@router.patch("/me")
async def patch_me(body: PatchMeIn, user: CurrentUser) -> dict[str, Any]:
    updated = await UserService.update_me(user, body)
    return ok(data=MeOut.from_model(updated))


@router.get("/search")
async def search(
    user: CurrentUser, keyword: str = Query(min_length=1, max_length=50)
) -> dict[str, Any]:
    users = await UserService.search_users(keyword)
    return ok(data={"list": [UserOut.from_model(u) for u in users]})
