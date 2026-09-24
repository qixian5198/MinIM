from sqlalchemy.ext.asyncio import AsyncSession

from app.models.file import File


class FileRepo:
    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        uploader_id: int,
        object_key: str,
        mime_type: str | None,
        size: int,
    ) -> File:
        record = File(
            uploader_id=uploader_id,
            object_key=object_key,
            mime_type=mime_type,
            size=size,
        )
        session.add(record)
        await session.flush()
        return record

    @staticmethod
    async def get_by_id(session: AsyncSession, file_id: int) -> File | None:
        return await session.get(File, file_id)
