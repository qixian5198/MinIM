from typing import Annotated, Any

from fastapi import APIRouter, Depends, UploadFile, status

from app.core.deps import get_current_user
from app.models.user import User
from app.security.rate_limit import rate_limit
from app.services import file_service

router = APIRouter(prefix="/files", tags=["files"])

CurrentUser = Annotated[User, Depends(get_current_user)]


@router.post("", status_code=status.HTTP_201_CREATED)
@rate_limit(name="file", key="user", limit=10, window=60)
async def upload(file: UploadFile, user: CurrentUser) -> dict[str, Any]:
    return await file_service.upload(user, file)
