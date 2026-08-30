from pathlib import Path, PurePosixPath, PureWindowsPath
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.content.models import ContentDraft
from app.media.images import ValidatedImage
from app.media.models import MediaAsset


class ImageDraftNotFound(LookupError):
    def __init__(self, draft_id: int) -> None:
        super().__init__(f"Content draft {draft_id} was not found")
        self.draft_id = draft_id


class InvalidStoredImagePath(ValueError):
    pass


class EditedImageRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_draft(self, draft_id: int) -> ContentDraft | None:
        return self.session.get(ContentDraft, draft_id)

    def for_draft(self, draft_id: int) -> MediaAsset | None:
        statement = select(MediaAsset).where(
            MediaAsset.content_draft_id == draft_id,
            MediaAsset.kind == "image_edited",
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


class EditedImageService:
    def __init__(self, repository: EditedImageRepository, upload_root: Path) -> None:
        self.repository = repository
        self.upload_root = upload_root

    def attach_or_replace(
        self, draft_id: int, image: ValidatedImage
    ) -> MediaAsset:
        if self.repository.get_draft(draft_id) is None:
            raise ImageDraftNotFound(draft_id)
        existing = self.repository.for_draft(draft_id)
        old_path = self.path_for(existing) if existing is not None else None
        new_path = self._save(draft_id, image)
        relative_path = new_path.relative_to(self.upload_root).as_posix()
        try:
            if existing is None:
                asset = MediaAsset(
                    content_draft_id=draft_id,
                    kind="image_edited",
                    relative_path=relative_path,
                    mime_type="image/png",
                    size_bytes=len(image.data),
                    sha256=image.sha256,
                    duration_ms=None,
                )
                self.repository.add(asset)
            else:
                asset = existing
                asset.relative_path = relative_path
                asset.mime_type = "image/png"
                asset.size_bytes = len(image.data)
                asset.sha256 = image.sha256
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
        candidate = PurePosixPath(asset.relative_path.replace("\\", "/"))
        windows_candidate = PureWindowsPath(asset.relative_path)
        expected_prefix = ("private", "edited_images", str(asset.content_draft_id))
        if (
            candidate.is_absolute()
            or windows_candidate.is_absolute()
            or ".." in candidate.parts
            or candidate.parts[:3] != expected_prefix
        ):
            raise InvalidStoredImagePath("edited image path is outside private storage")
        return self.upload_root.joinpath(*candidate.parts)

    def _save(self, draft_id: int, image: ValidatedImage) -> Path:
        directory = self.upload_root / "private" / "edited_images" / str(draft_id)
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{uuid4().hex}.png"
        target.write_bytes(image.data)
        return target


def resolve_product_original_path(
    upload_root: Path, product_id: int, relative_path: str
) -> Path:
    candidate = PurePosixPath(relative_path.replace("\\", "/"))
    windows_candidate = PureWindowsPath(relative_path)
    expected_prefix = ("products", str(product_id), "original")
    if (
        candidate.is_absolute()
        or windows_candidate.is_absolute()
        or ".." in candidate.parts
        or candidate.parts[:3] != expected_prefix
    ):
        raise InvalidStoredImagePath("product image path is outside original storage")
    return upload_root.joinpath(*candidate.parts)
