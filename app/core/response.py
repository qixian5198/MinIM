from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = 0
    message: str = "ok"
    data: T | None = None
    request_id: str | None = None


def ok(data: Any = None, request_id: str | None = None) -> dict:
    return ApiResponse(code=0, data=data, request_id=request_id).model_dump()
