from sqlalchemy import case, select
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

    def recent_approved_captions(
        self,
        product_id: int,
        *,
        exclude_series_key: str | None = None,
        limit: int = 3,
    ) -> list[str]:
        statement = select(ContentDraft.final_caption).where(
            ContentDraft.status == DraftStatus.APPROVED.value,
            ContentDraft.final_caption != "",
        )
        if exclude_series_key is not None:
            statement = statement.where(ContentDraft.series_key != exclude_series_key)
        statement = statement.order_by(
            case((ContentDraft.product_id == product_id, 0), else_=1),
            ContentDraft.approved_at.desc(),
            ContentDraft.created_at.desc(),
        ).limit(limit)
        return list(self.session.scalars(statement))

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()

    def refresh(self, draft: ContentDraft) -> None:
        self.session.refresh(draft)
