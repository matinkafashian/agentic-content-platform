from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.catalog.models import utc_now
from app.content.models import ContentDraft
from app.core.database import Base, UTCDateTime


class PublishingMode(StrEnum):
    MANUAL_APPROVAL = "manual_approval"
    AUTOMATIC = "automatic"
    PAUSED = "paused"


class PublicationStatus(StrEnum):
    SCHEDULED = "scheduled"
    PUBLISHING = "publishing"
    RETRY_SCHEDULED = "retry_scheduled"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PublishingControl(Base):
    __tablename__ = "publishing_controls"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_publishing_controls_singleton"),
        CheckConstraint(
            "mode in ('manual_approval','automatic','paused')",
            name="ck_publishing_controls_mode",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    mode: Mapped[str] = mapped_column(
        String(24), default=PublishingMode.MANUAL_APPROVAL.value
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, onupdate=utc_now
    )


class PostBundle(Base):
    __tablename__ = "post_bundles"

    id: Mapped[int] = mapped_column(primary_key=True)
    bundle_key: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    content_draft_id: Mapped[int] = mapped_column(
        ForeignKey("content_drafts.id"), unique=True, index=True
    )
    caption_snapshot: Mapped[str] = mapped_column(Text)
    image_relative_path: Mapped[str] = mapped_column(String(500))
    image_mime_type: Mapped[str] = mapped_column(String(100))
    image_size_bytes: Mapped[int] = mapped_column(Integer)
    image_sha256: Mapped[str] = mapped_column(String(64))
    voice_relative_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    voice_mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    voice_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    voice_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    voice_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)

    content_draft: Mapped[ContentDraft] = relationship()
    publications: Mapped[list["Publication"]] = relationship(
        back_populates="bundle", order_by="Publication.created_at.desc()"
    )


class Publication(Base):
    __tablename__ = "publications"
    __table_args__ = (
        CheckConstraint(
            "status in ('scheduled','publishing','retry_scheduled',"
            "'succeeded','failed','cancelled')",
            name="ck_publications_status",
        ),
        Index("ix_publications_due", "status", "scheduled_for"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    bundle_id: Mapped[int] = mapped_column(ForeignKey("post_bundles.id"), index=True)
    platform: Mapped[str] = mapped_column(String(40), index=True)
    destination: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(
        String(24), default=PublicationStatus.SCHEDULED.value, index=True
    )
    scheduled_for: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    idempotency_key: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    delivery_key: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True, nullable=True
    )
    external_message_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    safe_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, onupdate=utc_now
    )
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    bundle: Mapped[PostBundle] = relationship(back_populates="publications")
