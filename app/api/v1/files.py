import mimetypes
from typing import Annotated, Any

from fastapi import APIRouter, Depends, UploadFile, status
from fastapi.responses import StreamingResponse

from app.core.deps import get_current_user
from app.core.error_codes import ErrorCode
from app.core.exceptions import ApiError
from app.core.storage import get_object_storage
from app.db import session_factory
from app.models.user import User
from app.repositories.file_repo import FileRepo
from app.security.rate_limit import rate_limit
from app.services import file_service

router = APIRouter(prefix="/files", tags=["files"])

CurrentUser = Annotated[User, Depends(get_current_user)]


@router.post("", status_code=status.HTTP_201_CREATED)
@rate_limit(name="file", key="user", limit=10, window=60)
async def upload(file: UploadFile, user: CurrentUser) -> dict[str, Any]:
    return await file_service.upload(user, file)


@router.get("/{file_id}")
async def download(file_id: int, user: CurrentUser) -> StreamingResponse:
    """按文件 ID 取二进制。走本服务而不是 MinIO 直链：
    fake 存储下直链不存在，且直链会绕过鉴权。

    最小实现放行任意登录用户（聊天里收方要能看图）；
    更严谨的做法是校验"该文件所在房间的成员"，留作练习。
    """
    async with session_factory() as session:
        record = await FileRepo.get_by_id(session, file_id)
        if record is None:
            raise ApiError(ErrorCode.FILE_NOT_FOUND, "文件不存在", 404)

    data = await get_object_storage().get_object(record.object_key)
    media_type = record.mime_type or mimetypes.guess_type(record.object_key)[0] or "application/octet-stream"
    filename = record.object_key.rsplit("/", 1)[-1]
    return StreamingResponse(
        iter([data]),
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
