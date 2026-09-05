"""Store incoming customer-support interactions and delivery status."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260905_0009"
down_revision: str | Sequence[str] | None = "20260905_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "support_interactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=30), nullable=False),
        sa.Column("external_update_id", sa.String(length=100), nullable=False),
        sa.Column("external_message_id", sa.String(length=100), nullable=False),
        sa.Column("chat_id", sa.String(length=100), nullable=False),
        sa.Column("user_id", sa.String(length=100), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("decision", sa.String(length=30), nullable=False),
        sa.Column("reply_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("needs_admin", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "platform",
            "external_update_id",
            name="uq_support_interaction_platform_update",
        ),
    )
    op.create_index(
        op.f("ix_support_interactions_platform"),
        "support_interactions",
        ["platform"],
        unique=False,
    )
    op.create_index(
        op.f("ix_support_interactions_status"),
        "support_interactions",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_support_interactions_needs_admin"),
        "support_interactions",
        ["needs_admin"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_support_interactions_needs_admin"),
        table_name="support_interactions",
    )
    op.drop_index(
        op.f("ix_support_interactions_status"),
        table_name="support_interactions",
    )
    op.drop_index(
        op.f("ix_support_interactions_platform"),
        table_name="support_interactions",
    )
    op.drop_table("support_interactions")
