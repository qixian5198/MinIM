"""对象存储：MinIO 适配 + Protocol 接口，无 MinIO 环境用内存 fake。

设计取舍：
- 惰性连接 —— import 时不碰网络，MinIO 挂了 app 也能起；上传时才炸，炸得可见
- 连不上就报错，**不静默降级 fake**（静默丢数据比报错难发现得多）
- 显式降级只有一个口子：MINIO_ACCESS_KEY 不配 → fake（开发/测试），启动时打 warning
"""

import io
from typing import Protocol

import structlog

from app.core.config import settings

logger = structlog.get_logger()


class ObjectStorage(Protocol):
    """对象存储最小接口。"""

    async def put_object(
        self, object_key: str, data: bytes, content_type: str, size: int
    ) -> None: ...

    async def get_object(self, object_key: str) -> bytes: ...


class MinioStorage:
    """MinIO 适配：sync client 丢进 to_thread，不堵 event loop。"""

    def __init__(self) -> None:
        from minio import Minio

        self._minio = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=False,
        )
        self._bucket_ready = False

    def _ensure_bucket(self) -> None:
        if not self._bucket_ready:
            if not self._minio.bucket_exists(settings.MINIO_BUCKET):
                self._minio.make_bucket(settings.MINIO_BUCKET)
                logger.info("minio bucket created", bucket=settings.MINIO_BUCKET)
            self._bucket_ready = True

    async def put_object(
        self, object_key: str, data: bytes, content_type: str, size: int
    ) -> None:
        import asyncio

        await asyncio.to_thread(self._ensure_bucket)
        await asyncio.to_thread(
            self._minio.put_object,
            settings.MINIO_BUCKET,
            object_key,
            io.BytesIO(data),
            length=size,
            content_type=content_type,
        )

    async def get_object(self, object_key: str) -> bytes:
        import asyncio

        def _read() -> bytes:
            resp = self._minio.get_object(settings.MINIO_BUCKET, object_key)
            try:
                return resp.read()
            finally:
                resp.close()
                resp.release_conn()

        await asyncio.to_thread(self._ensure_bucket)
        return await asyncio.to_thread(_read)


class FakeObjectStorage:
    """内存版，进程内有效。无 MinIO 时的开发/测试替身。"""

    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}

    async def put_object(
        self, object_key: str, data: bytes, content_type: str, size: int
    ) -> None:
        self._objects[object_key] = data

    async def get_object(self, object_key: str) -> bytes:
        if object_key not in self._objects:
            raise FileNotFoundError(object_key)
        return self._objects[object_key]


_storage: ObjectStorage | None = None


def get_object_storage() -> ObjectStorage:
    """单例。MINIO_ACCESS_KEY 为空 → fake；配了就上真 MinIO（惰性连接）。"""
    global _storage
    if _storage is None:
        if not settings.MINIO_ACCESS_KEY:
            logger.warning("MINIO_ACCESS_KEY unset, using FakeObjectStorage (不持久化)")
            _storage = FakeObjectStorage()
        else:
            _storage = MinioStorage()
    return _storage


def set_object_storage(impl: ObjectStorage) -> None:
    """测试/开发用：强制换实现（比如换回 fake）。"""
    global _storage
    _storage = impl
