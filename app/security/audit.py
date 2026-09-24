"""审计落点（M7 · docs/08 抵赖风险）

审计是旁路：写失败只记日志，绝不把异常抛回主流程。
"消息发出去了但审计没写成功"可以接受，"审计报错导致消息发不出去"不能接受。
"""

import structlog

from app.db import session_factory
from app.models.enums import AuditResult
from app.repositories.audit_repo import AuditRepo

logger = structlog.get_logger()


async def record(
    *,
    action: str,
    user_id: int | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    result: AuditResult = AuditResult.SUCCESS,
    detail: str | None = None,
    ip: str | None = None,
) -> None:
    try:
        async with session_factory() as session:
            await AuditRepo.create(
                session,
                action=action,
                user_id=user_id,
                target_type=target_type,
                target_id=target_id,
                result=result,
                detail=detail,
                ip=ip,
            )
            await session.commit()
    except Exception:
        logger.exception("audit write failed", action=action)
