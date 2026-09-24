"""audit_logs 表（M7 · docs/08 抵赖风险）

审计留痕：谁、从哪个 IP、对什么对象、做了什么、结果如何。
按 user_id 与 action 各建一个索引——排查时只有这两种查法。
"""

import sqlalchemy as sa

from alembic import op

revision = "0006_audit_logs"
down_revision = "0005_files"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=True),
        sa.Column("target_id", sa.String(64), nullable=True),
        sa.Column("result", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("detail", sa.String(512), nullable=True),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("idx_audit_user", "audit_logs", ["user_id", "created_at"])
    op.create_index("idx_audit_action", "audit_logs", ["action", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_audit_action", table_name="audit_logs")
    op.drop_index("idx_audit_user", table_name="audit_logs")
    op.drop_table("audit_logs")
