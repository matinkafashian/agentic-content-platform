from sqlalchemy import select
from sqlalchemy.orm import Session

from app.brand.models import BrandProfile


class BrandRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self) -> BrandProfile | None:
        statement = select(BrandProfile).order_by(BrandProfile.id).limit(1)
        return self.session.scalar(statement)

    def add(self, profile: BrandProfile) -> None:
        self.session.add(profile)

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()

    def refresh(self, profile: BrandProfile) -> None:
        self.session.refresh(profile)

