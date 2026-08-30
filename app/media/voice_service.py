from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.content.models import ContentDraft
from app.media.models import MediaAsset
from app.media.voice import (
    ValidatedVoice,
    resolve_private_voice_path,
    save_voice,
)


class VoiceDraftNotFound(LookupError):
    def __init__(self, draft_id: int) -> None:
        super().__init__(f"Content draft {draft_id} was not found")
        self.draft_id = draft_id


class VoiceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_draft(self, draft_id: int) -> ContentDraft | None:
        return self.session.get(ContentDraft, draft_id)

    def for_draft(self, draft_id: int) -> MediaAsset | None:
        statement = select(MediaAsset).where(
            MediaAsset.content_draft_id == draft_id,
            MediaAsset.kind == "voice_original",
        )
        return self.session.scalar(statement)

    def add(self, asset: MediaAsset) -> None:
        self.session.add(asset)

    def delete(self, asset: MediaAsset) -> None:
        self.session.delete(asset)

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()

    def refresh(self, asset: MediaAsset) -> None:
        self.session.refresh(asset)


class VoiceService:
    def __init__(self, repository: VoiceRepository, upload_root: Path) -> None:
        self.repository = repository
        self.upload_root = upload_root

    def attach_or_replace(
        self, draft_id: int, voice: ValidatedVoice
    ) -> MediaAsset:
        if self.repository.get_draft(draft_id) is None:
            raise VoiceDraftNotFound(draft_id)
        existing = self.repository.for_draft(draft_id)
        old_path = self.path_for(existing) if existing is not None else None
        new_path = save_voice(self.upload_root, draft_id, voice)
        relative_path = new_path.relative_to(self.upload_root).as_posix()
        try:
            if existing is None:
                asset = MediaAsset(
                    content_draft_id=draft_id,
                    kind="voice_original",
                    relative_path=relative_path,
                    mime_type=voice.mime_type,
                    size_bytes=len(voice.data),
                    sha256=voice.sha256,
                    duration_ms=voice.duration_ms,
                )
                self.repository.add(asset)
            else:
                asset = existing
                asset.relative_path = relative_path
                asset.mime_type = voice.mime_type
                asset.size_bytes = len(voice.data)
                asset.sha256 = voice.sha256
                asset.duration_ms = voice.duration_ms
            self.repository.commit()
            self.repository.refresh(asset)
        except Exception:
            self.repository.rollback()
            new_path.unlink(missing_ok=True)
            raise
        if old_path is not None and old_path != new_path:
            old_path.unlink(missing_ok=True)
        return asset

    def delete(self, draft_id: int) -> None:
        asset = self.repository.for_draft(draft_id)
        if asset is None:
            return
        old_path = self.path_for(asset)
        try:
            self.repository.delete(asset)
            self.repository.commit()
        except Exception:
            self.repository.rollback()
            raise
        old_path.unlink(missing_ok=True)

    def path_for(self, asset: MediaAsset) -> Path:
        return resolve_private_voice_path(self.upload_root, asset.relative_path)
