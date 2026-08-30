from sqlalchemy import select
from sqlalchemy.orm import Session

from app.content.models import ContentDraft, DraftStatus


class ContentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, draft_id: int) -> ContentDraft | None:
        return self.session.get(ContentDraft, draft_id)

    def add(self, draft: ContentDraft) -> None:
        self.session.add(draft)

    def list_series(self, series_key: str) -> list[ContentDraft]:
        statement = (
            select(ContentDraft)
            .where(ContentDraft.series_key == series_key)
            .order_by(ContentDraft.revision.desc())
        )
        return list(self.session.scalars(statement))

    def latest_revision(self, series_key: str) -> ContentDraft | None:
        statement = (
            select(ContentDraft)
            .where(ContentDraft.series_key == series_key)
            .order_by(ContentDraft.revision.desc())
            .limit(1)
        )
        return self.session.scalar(statement)

    def approved_in_series(self, series_key: str) -> ContentDraft | None:
        statement = (
            select(ContentDraft)
            .where(
                ContentDraft.series_key == series_key,
                ContentDraft.status == DraftStatus.APPROVED.value,
            )
            .limit(1)
        )
        return self.session.scalar(statement)

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()

    def refresh(self, draft: ContentDraft) -> None:
        self.session.refresh(draft)

