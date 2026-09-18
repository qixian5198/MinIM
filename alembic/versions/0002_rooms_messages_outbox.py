"""rooms / room_members / messages / outbox（M2）

M2 的"单聊 + 消息核心"需要这四张表：
- rooms 用一张表同时装单聊和群聊，靠 type 区分
- 已读位点放 room_members，不放 messages（docs/05 §4.1）
- outbox 与消息同事务写入，保证"落库即会投递"

索引按 docs/05 §3 一次性建好，游标分页依赖 idx_msg_room_id_created。
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

# revision id 不能超过 32 字符：alembic_version.version_num 是 VARCHAR(32)
revision = "0002_rooms_messages_outbox"
down_revision = "0001_create_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rooms",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("type", sa.SmallInteger(), nullable=False),
        sa.Column("name", sa.String(100), nullable=True),
        sa.Column("avatar_url", sa.String(500), nullable=True),
        sa.Column("owner_id", sa.BigInteger(), nullable=True),
        sa.Column("last_msg_id", sa.BigInteger(), nullable=True),
        sa.Column("member_limit", sa.Integer(), nullable=False, server_default="500"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "room_members",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("room_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.SmallInteger(), nullable=False, server_default="2"),
        sa.Column("last_read_msg_id", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "joined_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_unique_constraint("uq_room_member", "room_members", ["room_id", "user_id"])
    op.create_index("idx_member_user", "room_members", ["user_id"])
    op.create_index("idx_member_room", "room_members", ["room_id"])

    op.create_table(
        "messages",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("room_id", sa.BigInteger(), nullable=False),
        sa.Column("from_uid", sa.BigInteger(), nullable=False),
        sa.Column("type", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("reply_to_id", sa.BigInteger(), nullable=True),
        sa.Column("extra", JSONB(), nullable=True),
        sa.Column("status", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    # 游标分页主索引：id DESC 与查询的 ORDER BY 完全对齐，避免额外排序
    op.create_index("idx_msg_room_id_created", "messages", ["room_id", sa.text("id DESC")])
    op.create_index("idx_msg_from", "messages", ["from_uid"])

    op.create_table(
        "outbox",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("topic", sa.String(50), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("status", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_retry_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    # 部分索引：轮询只关心待发记录，已发/死信不进索引，省空间也省维护成本
    op.create_index(
        "idx_outbox_pending",
        "outbox",
        ["status", "next_retry_at"],
        postgresql_where=sa.text("status = 0"),
    )


def downgrade() -> None:
    op.drop_index("idx_outbox_pending", table_name="outbox")
    op.drop_table("outbox")
    op.drop_index("idx_msg_from", table_name="messages")
    op.drop_index("idx_msg_room_id_created", table_name="messages")
    op.drop_table("messages")
    op.drop_index("idx_member_room", table_name="room_members")
    op.drop_index("idx_member_user", table_name="room_members")
    op.drop_table("room_members")
    op.drop_table("rooms")
