import uuid

from fastapi import FastAPI, Request, status
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, code: int, message: str, http_status: int = status.HTTP_400_BAD_REQUEST):
        self.code = code
        self.message = message
        self.http_status = http_status
        super().__init__(message)


def _error_response(code: int, message: str, http_status: int, request_id: str | None) -> JSONResponse:
    return JSONResponse(
        status_code=http_status,
        content={"code": code, "message": message, "data": None, "request_id": request_id},
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        return _error_response(exc.code, exc.message, exc.http_status, request_id)

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
    async def request_id_middleware(request: Request, call_next):
        request.state.request_id = uuid.uuid4().hex
        return await call_next(request)
