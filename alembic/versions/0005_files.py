"""files 表（M6）

文件元数据入库，对象本体存 MinIO。
"""

import sqlalchemy as sa

from alembic import op

revision = "0005_files"
down_revision = "0004_message_marks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "files",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("uploader_id", sa.BigInteger(), nullable=False),
        sa.Column("object_key", sa.String(200), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=True),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("files")
