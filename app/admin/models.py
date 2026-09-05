from datetime import datetime

from sqlalchemy import CheckConstraint, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.catalog.models import utc_now
from app.core.database import Base, UTCDateTime


class AdminCredential(Base):
    __tablename__ = "admin_credentials"
    __table_args__ = (CheckConstraint("id = 1", name="ck_admin_credentials_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    password_hash: Mapped[str] = mapped_column(String(500))
    session_version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, onupdate=utc_now
    )
