import mimetypes
import uuid
from typing import Any

from fastapi import UploadFile

from app.core.config import settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import ApiError
from app.core.response import ok
from app.core.storage import get_object_storage
from app.db import session_factory
from app.models.user import User
from app.repositories.file_repo import FileRepo
from app.schemas.file import FileOut

# docs/06 §8：图片 ≤10MB（jpg/png/gif/webp），其他文件 ≤50MB，类型白名单
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MAX_IMAGE_SIZE = 10 * 1024 * 1024
MAX_FILE_SIZE = 50 * 1024 * 1024
ALLOWED_EXTS = IMAGE_EXTS | {".pdf", ".zip"}


async def upload(user: User, file: UploadFile) -> dict[str, Any]:
    data = await file.read()
    size = len(data)
    filename = file.filename or "unnamed"
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext in IMAGE_EXTS and size > MAX_IMAGE_SIZE:
        raise ApiError(ErrorCode.FILE_TOO_LARGE, "图片超过 10MB", 422)
    if ext not in IMAGE_EXTS and size > MAX_FILE_SIZE:
        raise ApiError(ErrorCode.FILE_TOO_LARGE, "文件超过 50MB", 422)
    if ext not in ALLOWED_EXTS:
        raise ApiError(ErrorCode.FILE_TYPE_NOT_ALLOWED, f"不支持的类型 {ext or '(无扩展名)'}", 422)

    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    object_key = f"uploads/{user.id}/{uuid.uuid4().hex}"
    await get_object_storage().put_object(object_key, data, mime, size)

    async with session_factory() as session:
        record = await FileRepo.create(
            session,
            uploader_id=user.id,
            object_key=object_key,
            mime_type=mime,
            size=size,
        )
        await session.commit()

    base = f"http://{settings.MINIO_ENDPOINT}/{settings.MINIO_BUCKET}"
    return ok(data=FileOut.from_model(record, base_url=base))
