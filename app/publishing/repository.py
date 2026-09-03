from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.content.models import ContentDraft, DraftStatus
from app.media.models import MediaAsset
from app.publishing.models import (
    PostBundle,
    Publication,
    PublicationStatus,
    PublishingControl,
    PublishingMode,
)


class PublishingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def control(self) -> PublishingControl:
        control = self.session.get(PublishingControl, 1)
        if control is None:
            control = PublishingControl(id=1, mode=PublishingMode.MANUAL_APPROVAL.value)
            self.session.add(control)
            self.session.flush()
        return control

    def get_draft(self, draft_id: int) -> ContentDraft | None:
        return self.session.get(ContentDraft, draft_id)

    def approved_in_series(self, series_key: str) -> ContentDraft | None:
        return self.session.scalar(
            select(ContentDraft).where(
                ContentDraft.series_key == series_key,
                ContentDraft.status == DraftStatus.APPROVED.value,
            )
        )

    def media_for_draft(self, draft_id: int, kind: str) -> MediaAsset | None:
        return self.session.scalar(
            select(MediaAsset).where(
                MediaAsset.content_draft_id == draft_id,
                MediaAsset.kind == kind,
            )
        )

    def bundle_for_draft(self, draft_id: int) -> PostBundle | None:
        return self.session.scalar(
            select(PostBundle).where(PostBundle.content_draft_id == draft_id)
        )

    def get_bundle(self, bundle_id: int) -> PostBundle | None:
        return self.session.get(PostBundle, bundle_id)

    def add_bundle(self, bundle: PostBundle) -> None:
        self.session.add(bundle)

    def add_publication(self, publication: Publication) -> None:
        self.session.add(publication)

    def get_publication(self, publication_id: int) -> Publication | None:
        return self.session.get(Publication, publication_id)

    def claim_for_delivery(self, publication_id: int) -> bool:
        statement = (
            update(Publication)
            .where(
                Publication.id == publication_id,
                Publication.status.in_(
                    [
                        PublicationStatus.SCHEDULED.value,
                        PublicationStatus.RETRY_SCHEDULED.value,
                    ]
                ),
            )
            .values(
                status=PublicationStatus.PUBLISHING.value,
                attempt_count=Publication.attempt_count + 1,
            )
            .execution_options(synchronize_session=False)
        )
        result = self.session.execute(statement)
        self.session.commit()
        return result.rowcount == 1

    def list_publications(self, *, limit: int = 100) -> list[Publication]:
        statement = (
            select(Publication)
            .options(selectinload(Publication.bundle).selectinload(PostBundle.content_draft))
            .order_by(Publication.created_at.desc())
            .limit(limit)
        )
        return list(self.session.scalars(statement))

    def due(self, now: datetime, *, limit: int = 20) -> list[Publication]:
        statement = (
            select(Publication)
            .options(selectinload(Publication.bundle))
            .where(
                Publication.status.in_(
                    [
                        PublicationStatus.SCHEDULED.value,
                        PublicationStatus.RETRY_SCHEDULED.value,
                    ]
                ),
                Publication.scheduled_for <= now,
            )
            .order_by(Publication.scheduled_for.asc(), Publication.id.asc())
            .limit(limit)
        )
        return list(self.session.scalars(statement))

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()

    def refresh(self, value: object) -> None:
        self.session.refresh(value)
