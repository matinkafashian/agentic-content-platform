"""Add immutable post bundles, publishing mode, and publication attempts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260831_0003"
down_revision: str | Sequence[str] | None = "20260829_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "publishing_controls",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(length=24), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_publishing_controls_singleton"),
        sa.CheckConstraint(
            "mode in ('manual_approval','automatic','paused')",
            name="ck_publishing_controls_mode",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "post_bundles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bundle_key", sa.String(length=36), nullable=False),
        sa.Column("content_draft_id", sa.Integer(), nullable=False),
        sa.Column("caption_snapshot", sa.Text(), nullable=False),
        sa.Column("image_relative_path", sa.String(length=500), nullable=False),
        sa.Column("image_mime_type", sa.String(length=100), nullable=False),
        sa.Column("image_size_bytes", sa.Integer(), nullable=False),
        sa.Column("image_sha256", sa.String(length=64), nullable=False),
        sa.Column("voice_relative_path", sa.String(length=500), nullable=True),
        sa.Column("voice_mime_type", sa.String(length=100), nullable=True),
        sa.Column("voice_size_bytes", sa.Integer(), nullable=True),
        sa.Column("voice_sha256", sa.String(length=64), nullable=True),
        sa.Column("voice_duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["content_draft_id"], ["content_drafts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_post_bundles_bundle_key", "post_bundles", ["bundle_key"], unique=True
    )
    op.create_index(
        "ix_post_bundles_content_draft_id",
        "post_bundles",
        ["content_draft_id"],
        unique=True,
    )
    op.create_table(
        "publications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bundle_id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=40), nullable=False),
        sa.Column("destination", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=36), nullable=False),
        sa.Column("external_message_ids", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("safe_error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status in ('scheduled','publishing','retry_scheduled','succeeded','failed','cancelled')",
            name="ck_publications_status",
        ),
        sa.ForeignKeyConstraint(["bundle_id"], ["post_bundles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_publications_bundle_id", "publications", ["bundle_id"])
    op.create_index(
        "ix_publications_idempotency_key",
        "publications",
        ["idempotency_key"],
        unique=True,
    )
    op.create_index("ix_publications_platform", "publications", ["platform"])
    op.create_index("ix_publications_scheduled_for", "publications", ["scheduled_for"])
    op.create_index("ix_publications_status", "publications", ["status"])
    op.create_index(
        "ix_publications_due", "publications", ["status", "scheduled_for"]
    )


def downgrade() -> None:
    op.drop_index("ix_publications_due", table_name="publications")
    op.drop_index("ix_publications_status", table_name="publications")
    op.drop_index("ix_publications_scheduled_for", table_name="publications")
    op.drop_index("ix_publications_platform", table_name="publications")
    op.drop_index("ix_publications_idempotency_key", table_name="publications")
    op.drop_index("ix_publications_bundle_id", table_name="publications")
    op.drop_table("publications")
    op.drop_index("ix_post_bundles_content_draft_id", table_name="post_bundles")
    op.drop_index("ix_post_bundles_bundle_key", table_name="post_bundles")
    op.drop_table("post_bundles")
    op.drop_table("publishing_controls")

