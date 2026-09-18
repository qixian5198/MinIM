from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = 0
    message: str = "ok"
    data: T | None = None
    request_id: str | None = None


def ok(data: Any = None, request_id: str | None = None) -> dict[str, Any]:
    # mode="json"：契约要求时间是 ISO 8601 UTC 带 Z（docs/06 §1.1）。
    # 默认 python 模式会保留 datetime 对象，各层各自序列化就会一会儿 "Z" 一会儿 "+00:00"
    return ApiResponse(code=0, data=data, request_id=request_id).model_dump(mode="json")
