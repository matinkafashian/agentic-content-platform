"""Persist the lightweight hybrid support knowledge index."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260905_0007"
down_revision: str | Sequence[str] | None = "20260904_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("support_knowledge") as batch_op:
        batch_op.add_column(
            sa.Column("index_chunks", sa.JSON(), nullable=False, server_default="[]")
        )
        batch_op.add_column(
            sa.Column(
                "indexed_content_hash",
                sa.String(length=64),
                nullable=False,
                server_default="",
            )
        )
        batch_op.add_column(
            sa.Column("embedding_model", sa.String(length=100), nullable=False, server_default="")
        )


def downgrade() -> None:
    with op.batch_alter_table("support_knowledge") as batch_op:
        batch_op.drop_column("embedding_model")
        batch_op.drop_column("indexed_content_hash")
        batch_op.drop_column("index_chunks")
