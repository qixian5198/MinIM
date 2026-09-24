import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, status
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse, Response


class ApiError(Exception):
    def __init__(
        self,
        code: int,
        message: str,
        http_status: int = status.HTTP_400_BAD_REQUEST,
        headers: dict[str, str] | None = None,
    ):
        self.code = code
        self.message = message
        self.http_status = http_status
        self.headers = headers
        super().__init__(message)


def _error_response(
    code: int,
    message: str,
    http_status: int,
    request_id: str | None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=http_status,
        content={"code": code, "message": message, "data": None, "request_id": request_id},
        headers=headers,
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        return _error_response(
            exc.code, exc.message, exc.http_status, request_id, exc.headers
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        return _error_response(
            code=int(exc.status_code),
            message=str(exc.detail),
            http_status=exc.status_code,
            request_id=request_id,
        )

    @app.middleware("http")
    async def request_id_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.request_id = uuid.uuid4().hex
        return await call_next(request)
