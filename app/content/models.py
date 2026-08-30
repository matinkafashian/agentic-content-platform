from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.catalog.models import Product, utc_now
from app.core.database import Base, UTCDateTime


class DraftStatus(StrEnum):
    DRAFT = "draft"
    WAITING_APPROVAL = "waiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class ContentDraft(Base):
    __tablename__ = "content_drafts"
    __table_args__ = (
        CheckConstraint(
            "status in ('draft','waiting_approval','approved','rejected','superseded')",
            name="ck_content_drafts_status",
        ),
        Index("ix_content_drafts_series_revision", "series_key", "revision", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("content_drafts.id"), nullable=True
    )
    series_key: Mapped[str] = mapped_column(String(36), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    user_brief: Mapped[str] = mapped_column(Text)
    requested_angle: Mapped[str] = mapped_column(String(40))
    provider_name: Mapped[str] = mapped_column(String(80))
    provider_payload: Mapped[dict[str, object]] = mapped_column(JSON)
    final_caption: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(24), default=DraftStatus.WAITING_APPROVAL.value, index=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, onupdate=utc_now
    )
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    product: Mapped[Product] = relationship()
    parent: Mapped["ContentDraft | None"] = relationship(remote_side=[id])

