from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.enums import AuditResult


class AuditRepo:
    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        action: str,
        user_id: int | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        result: AuditResult = AuditResult.SUCCESS,
        detail: str | None = None,
        ip: str | None = None,
    ) -> AuditLog:
        log = AuditLog(
            user_id=user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            result=int(result),
            detail=detail,
            ip=ip,
        )
        session.add(log)
        await session.flush()
        return log

    @staticmethod
    async def list_recent(
        session: AsyncSession,
        *,
        user_id: int | None = None,
        action: str | None = None,
        limit: int = 50,
    ) -> list[AuditLog]:
        stmt = select(AuditLog)
        if user_id is not None:
            stmt = stmt.where(AuditLog.user_id == user_id)
        if action is not None:
            stmt = stmt.where(AuditLog.action == action)
        stmt = stmt.order_by(AuditLog.id.desc()).limit(limit)
        return list((await session.execute(stmt)).scalars().all())
