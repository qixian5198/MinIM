"""friendships / friend_requests / blocks（M4）

好友关系按 docs/05 §4.2 设计成双向两条：查好友列表只查 `user_id = me`，
避免 `OR` 查询（利于索引）。UNIQUE(user_id, friend_id) 防重复。
blocks 是单向拉黑：A 拉黑 B 后 A 不再向 B 发申请，查询只用 (user_id, blocked_id)。

索引按 docs/05 §3 一次建齐；upgrade / downgrade 都验证过。
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_friends_blocks"
down_revision = "0002_rooms_messages_outbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "friendships",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("friend_id", sa.BigInteger(), nullable=False),
        sa.Column("remark", sa.String(length=50)),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("user_id", "friend_id", name="uq_friendship"),
    )
    op.create_index("idx_friend_user", "friendships", ["user_id"])

    op.create_table(
        "friend_requests",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("from_uid", sa.BigInteger(), nullable=False),
        sa.Column("to_uid", sa.BigInteger(), nullable=False),
        sa.Column("message", sa.String(length=200)),
        sa.Column("status", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    # 查"我收到的待处理申请"高频：WHERE to_uid = ? AND status = 0
    op.create_index("idx_freq_to_status", "friend_requests", ["to_uid", "status"])

    op.create_table(
        "blocks",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("blocked_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("user_id", "blocked_id", name="uq_block"),
    )
    op.create_index("idx_block_user", "blocks", ["user_id"])


def downgrade() -> None:
    op.drop_index("idx_block_user", table_name="blocks")
    op.drop_table("blocks")
    op.drop_index("idx_freq_to_status", table_name="friend_requests")
    op.drop_table("friend_requests")
    op.drop_index("idx_friend_user", table_name="friendships")
    op.drop_table("friendships")
