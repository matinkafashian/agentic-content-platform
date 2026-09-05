"""Store one reusable support phone on the brand profile."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260905_0008"
down_revision: str | Sequence[str] | None = "20260905_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("brand_profiles") as batch_op:
        batch_op.add_column(
            sa.Column(
                "support_phone",
                sa.String(length=32),
                nullable=False,
                server_default="",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("brand_profiles") as batch_op:
        batch_op.drop_column("support_phone")
