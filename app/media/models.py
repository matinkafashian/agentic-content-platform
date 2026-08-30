from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.catalog.models import utc_now
from app.content.models import ContentDraft
from app.core.database import Base, UTCDateTime


class MediaAsset(Base):
    __tablename__ = "media_assets"
    __table_args__ = (
        UniqueConstraint(
            "content_draft_id", "kind", name="uq_media_assets_draft_kind"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    content_draft_id: Mapped[int] = mapped_column(
        ForeignKey("content_drafts.id"), index=True
    )
    kind: Mapped[str] = mapped_column(String(40))
    relative_path: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)

    content_draft: Mapped[ContentDraft] = relationship()

