import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router as api_v1_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.core.redis import close_redis
from app.tasks.outbox_worker import worker as outbox_worker
from app.ws.manager import manager
from app.ws.router import router as ws_router

logger = structlog.get_logger()

SWEEP_INTERVAL = 30


async def _sweep_stale_connections() -> None:
    while True:
        await asyncio.sleep(SWEEP_INTERVAL)
        try:
            dropped = await manager.drop_stale()
            if dropped:
                logger.info("ws sweep dropped stale connections", count=dropped)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("ws sweep failed")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    sweeper = asyncio.create_task(_sweep_stale_connections())
    outbox_worker.start()
    try:
        yield
    finally:
        await outbox_worker.stop()
        sweeper.cancel()
        await close_redis()


def create_app() -> FastAPI:
    app = FastAPI(
        title="MinIM",
        version="0.1.0",
        description="一个最小可用的即时通讯内核",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(api_v1_router, prefix="/api/v1")
    # WS 不挂 /api/v1：docs/06 §9 定的就是 /ws
    app.include_router(ws_router)

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok", "env": settings.APP_ENV}

    return app


app = create_app()
