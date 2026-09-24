"""审计日志（M7 · docs/08 抵赖风险）

只记"谁、从哪个 IP、对什么对象、做了什么、结果如何"五件事。
不记消息正文——审计是为了追溯行为，再抄一份正文等于把隐私风险翻倍。

写审计失败绝不能影响主流程：它是旁路，主流程该成功还得成功。
"""

from datetime import datetime

from sqlalchemy import BigInteger, SmallInteger, String, func
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # 登录失败这类场景没有用户 id，所以可空
    user_id: Mapped[int | None] = mapped_column(BigInteger)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(32))
    target_id: Mapped[str | None] = mapped_column(String(64))
    result: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    detail: Mapped[str | None] = mapped_column(String(512))
    ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
