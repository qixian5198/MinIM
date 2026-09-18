"""message_marks 表（M5 消息可靠性 · 点赞/点踩）

已读位点 last_read_msg_id 在 M2 的 room_members 上已就绪，本迁移只补 marks 表。
切换幂等靠 uq_msg_mark(msg_id, user_id, mark_type)，计数走 idx_mark_msg。

upgrade / downgrade 都已验证。
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_message_marks"
down_revision = "0003_friends_blocks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "message_marks",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("msg_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("mark_type", sa.SmallInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("msg_id", "user_id", "mark_type", name="uq_msg_mark"),
    )
    op.create_index("idx_mark_msg", "message_marks", ["msg_id"])


def downgrade() -> None:
    op.drop_index("idx_mark_msg", table_name="message_marks")
    op.drop_table("message_marks")
