"""Allow post bundles without an image."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260903_0005"
down_revision: str | Sequence[str] | None = "20260903_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("post_bundles") as batch_op:
        batch_op.alter_column(
            "image_relative_path", existing_type=sa.String(length=500), nullable=True
        )
        batch_op.alter_column("image_mime_type", existing_type=sa.String(length=100), nullable=True)
        batch_op.alter_column("image_size_bytes", existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column("image_sha256", existing_type=sa.String(length=64), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("post_bundles") as batch_op:
        batch_op.alter_column("image_sha256", existing_type=sa.String(length=64), nullable=False)
        batch_op.alter_column("image_size_bytes", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column(
            "image_mime_type", existing_type=sa.String(length=100), nullable=False
        )
        batch_op.alter_column(
            "image_relative_path", existing_type=sa.String(length=500), nullable=False
        )
