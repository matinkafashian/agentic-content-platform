from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.catalog.models import utc_now
from app.core.database import Base, UTCDateTime


class SupportKnowledge(Base):
    __tablename__ = "support_knowledge"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_support_knowledge_singleton"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    content: Mapped[str] = mapped_column(Text, default="")
    index_chunks: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    indexed_content_hash: Mapped[str] = mapped_column(String(64), default="")
    embedding_model: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, onupdate=utc_now
    )


class SupportInteraction(Base):
    __tablename__ = "support_interactions"
    __table_args__ = (
        UniqueConstraint(
            "platform",
            "external_update_id",
            name="uq_support_interaction_platform_update",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[str] = mapped_column(String(30), index=True)
    external_update_id: Mapped[str] = mapped_column(String(100))
    external_message_id: Mapped[str] = mapped_column(String(100))
    chat_id: Mapped[str] = mapped_column(String(100))
    user_id: Mapped[str] = mapped_column(String(100))
    question: Mapped[str] = mapped_column(Text, default="")
    decision: Mapped[str] = mapped_column(String(30), default="")
    reply_text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="processing", index=True)
    needs_admin: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, onupdate=utc_now
    )
