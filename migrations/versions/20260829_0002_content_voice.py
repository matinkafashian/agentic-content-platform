"""Add brand profiles, content drafts, and private media metadata."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260829_0002"
down_revision: str | Sequence[str] | None = "20260828_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "brand_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("business_name", sa.String(length=200), nullable=False),
        sa.Column("tagline", sa.String(length=500), nullable=False),
        sa.Column("audience", sa.String(length=500), nullable=False),
        sa.Column("tone_guidelines", sa.Text(), nullable=False),
        sa.Column("support_handle", sa.String(length=200), nullable=False),
        sa.Column("default_cta", sa.String(length=500), nullable=False),
        sa.Column("approved_claims", sa.JSON(), nullable=False),
        sa.Column("default_hashtags", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "content_drafts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("series_key", sa.String(length=36), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("user_brief", sa.Text(), nullable=False),
        sa.Column("requested_angle", sa.String(length=40), nullable=False),
        sa.Column("provider_name", sa.String(length=80), nullable=False),
        sa.Column("provider_payload", sa.JSON(), nullable=False),
        sa.Column("final_caption", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status in ('draft','waiting_approval','approved','rejected','superseded')",
            name="ck_content_drafts_status",
        ),
        sa.ForeignKeyConstraint(["parent_id"], ["content_drafts.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_content_drafts_product_id", "content_drafts", ["product_id"], unique=False
    )
    op.create_index(
        "ix_content_drafts_series_key", "content_drafts", ["series_key"], unique=False
    )
    op.create_index(
        "ix_content_drafts_series_revision",
        "content_drafts",
        ["series_key", "revision"],
        unique=True,
    )
    op.create_index(
        "ix_content_drafts_status", "content_drafts", ["status"], unique=False
    )
    op.create_table(
        "media_assets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("content_draft_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("relative_path", sa.String(length=500), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["content_draft_id"], ["content_drafts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "content_draft_id", "kind", name="uq_media_assets_draft_kind"
        ),
    )
    op.create_index(
        "ix_media_assets_content_draft_id",
        "media_assets",
        ["content_draft_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_media_assets_content_draft_id", table_name="media_assets")
    op.drop_table("media_assets")
    op.drop_index("ix_content_drafts_status", table_name="content_drafts")
    op.drop_index("ix_content_drafts_series_revision", table_name="content_drafts")
    op.drop_index("ix_content_drafts_series_key", table_name="content_drafts")
    op.drop_index("ix_content_drafts_product_id", table_name="content_drafts")
    op.drop_table("content_drafts")
    op.drop_table("brand_profiles")

