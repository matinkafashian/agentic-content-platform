"""Store a replaceable admin password and session version."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260905_0010"
down_revision: str | Sequence[str] | None = "20260905_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admin_credentials",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("password_hash", sa.String(length=500), nullable=False),
        sa.Column("session_version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_admin_credentials_singleton"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("admin_credentials")
