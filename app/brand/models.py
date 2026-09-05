from datetime import datetime

from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.catalog.models import utc_now
from app.core.database import Base, UTCDateTime


class BrandProfile(Base):
    __tablename__ = "brand_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_name: Mapped[str] = mapped_column(String(200))
    tagline: Mapped[str] = mapped_column(String(500), default="")
    audience: Mapped[str] = mapped_column(String(500), default="")
    tone_guidelines: Mapped[str] = mapped_column(Text, default="")
    support_handle: Mapped[str] = mapped_column(String(200), default="")
    support_phone: Mapped[str] = mapped_column(String(32), default="")
    default_cta: Mapped[str] = mapped_column(String(500), default="")
    approved_claims: Mapped[list[str]] = mapped_column(JSON, default=list)
    default_hashtags: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, onupdate=utc_now
    )
