"""Create the initial products table."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260828_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("price", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("availability", sa.String(length=40), nullable=False),
        sa.Column("shipping_info", sa.Text(), nullable=False),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("primary_image_path", sa.String(length=500), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_products_active"), "products", ["active"], unique=False)
    op.create_index(op.f("ix_products_name"), "products", ["name"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_products_name"), table_name="products")
    op.drop_index(op.f("ix_products_active"), table_name="products")
    op.drop_table("products")
