from datetime import datetime

from pydantic import BaseModel


class FileOut(BaseModel):
    id: str
    url: str
    mime_type: str | None
    size: int
    created_at: datetime

    @classmethod
    def from_model(cls, record, base_url: str = "") -> "FileOut":
        return cls(
            id=str(record.id),
            url=f"{base_url}/{record.object_key}",
            mime_type=record.mime_type,
            size=record.size,
            created_at=record.created_at,
        )
