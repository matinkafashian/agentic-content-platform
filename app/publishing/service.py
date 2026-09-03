import shutil
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path, PurePosixPath, PureWindowsPath
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from app.content.models import DraftStatus
from app.publishing.adapters import DeliveryResult, PlatformAdapter
from app.publishing.models import (
    PostBundle,
    Publication,
    PublicationStatus,
    PublishingMode,
)
from app.publishing.repository import PublishingRepository


class BundleInputError(ValueError):
    pass


class ScheduleInputError(ValueError):
    pass


class PublishingPaused(RuntimeError):
    pass


class PublishingService:
    def __init__(
        self,
        repository: PublishingRepository,
        upload_root: Path,
        adapters: dict[str, PlatformAdapter],
        *,
        require_edited_image: bool = False,
    ) -> None:
        self.repository = repository
        self.upload_root = upload_root
        self.adapters = adapters
        self.require_edited_image = require_edited_image

    def control(self):
        control = self.repository.control()
        self.repository.commit()
        return control

    def set_mode(self, mode: PublishingMode | str):
        try:
            normalized = PublishingMode(mode)
        except ValueError as exc:
            raise ScheduleInputError("حالت انتشار معتبر نیست") from exc
        control = self.repository.control()
        control.mode = normalized.value
        self.repository.commit()
        self.repository.refresh(control)
        return control

    def create_bundle(self, draft_id: int) -> PostBundle:
        existing = self.repository.bundle_for_draft(draft_id)
        if existing is not None:
            return existing
        draft = self.repository.get_draft(draft_id)
        if draft is None:
            raise BundleInputError("نسخه محتوا پیدا نشد")
        control = self.repository.control()
        if control.mode == PublishingMode.AUTOMATIC.value:
            self._approve_automatically(draft)
        elif draft.status != DraftStatus.APPROVED.value:
            raise BundleInputError("در حالت دستی ابتدا باید این نسخه را تأیید کنید")
        if not draft.product.active:
            raise BundleInputError("محصول غیرفعال است و قابل انتشار نیست")
        caption = draft.final_caption.strip()
        if not 20 <= len(caption) <= 4000:
            raise BundleInputError("کپشن نهایی معتبر نیست")

        image_path, image_mime = self._source_image(draft)
        voice = self.repository.media_for_draft(draft.id, "voice_original")
        voice_path = self._private_asset_path(voice.relative_path) if voice else None
        if voice_path is not None and not voice_path.is_file():
            raise BundleInputError("فایل وویس ذخیره‌شده پیدا نشد")

        bundle_key = str(uuid4())
        bundle_dir = self.upload_root / "private" / "bundles" / bundle_key
        image_target = bundle_dir / f"image{image_path.suffix.lower()}"
        voice_target = bundle_dir / f"voice{voice_path.suffix.lower()}" if voice_path else None
        try:
            bundle_dir.mkdir(parents=True, exist_ok=False)
            shutil.copyfile(image_path, image_target)
            if voice_path is not None and voice_target is not None:
                shutil.copyfile(voice_path, voice_target)
            image_data = image_target.read_bytes()
            voice_data = voice_target.read_bytes() if voice_target else None
            bundle = PostBundle(
                bundle_key=bundle_key,
                content_draft_id=draft.id,
                caption_snapshot=caption,
                image_relative_path=image_target.relative_to(self.upload_root).as_posix(),
                image_mime_type=image_mime,
                image_size_bytes=len(image_data),
                image_sha256=sha256(image_data).hexdigest(),
                voice_relative_path=(
                    voice_target.relative_to(self.upload_root).as_posix()
                    if voice_target
                    else None
                ),
                voice_mime_type=voice.mime_type if voice else None,
                voice_size_bytes=len(voice_data) if voice_data is not None else None,
                voice_sha256=sha256(voice_data).hexdigest() if voice_data else None,
                voice_duration_ms=voice.duration_ms if voice else None,
            )
            self.repository.add_bundle(bundle)
            self.repository.commit()
            self.repository.refresh(bundle)
            return bundle
        except Exception:
            self.repository.rollback()
            shutil.rmtree(bundle_dir, ignore_errors=True)
            raise

    def schedule(
        self,
        bundle_id: int,
        *,
        platform: str,
        destination: str,
        scheduled_for: datetime,
    ) -> Publication:
        return self.schedule_many(
            bundle_id,
            destinations={platform: destination},
            scheduled_for=scheduled_for,
        )[0]

    def schedule_many(
        self,
        bundle_id: int,
        *,
        destinations: dict[str, str],
        scheduled_for: datetime,
    ) -> list[Publication]:
        bundle = self.repository.get_bundle(bundle_id)
        if bundle is None:
            raise ScheduleInputError("بسته نهایی پیدا نشد")
        if not destinations:
            raise ScheduleInputError("هیچ کانال فعالی برای انتشار تنظیم نشده است")
        if scheduled_for.tzinfo is None:
            raise ScheduleInputError("زمان انتشار باید دارای منطقه زمانی باشد")

        normalized_targets: list[tuple[str, str]] = []
        for platform, destination in destinations.items():
            adapter = self.adapters.get(platform)
            if adapter is None:
                raise ScheduleInputError(
                    f"اتصال پلتفرم {platform} هنوز فعال نیست"
                )
            normalized_destination = destination.strip()
            if not 2 <= len(normalized_destination) <= 200:
                raise ScheduleInputError(
                    f"مقصد پلتفرم {platform} تنظیم نشده یا معتبر نیست"
                )
            validator = getattr(adapter, "validate", None)
            if validator is not None:
                validation_error = validator(bundle, normalized_destination)
                if validation_error is not None:
                    raise ScheduleInputError(validation_error.safe_error_message)
            normalized_targets.append((platform, normalized_destination))

        publications: list[Publication] = []
        for platform, destination in normalized_targets:
            delivery_key = self._delivery_key(bundle.id, platform, destination)
            existing = self.repository.publication_by_delivery_key(delivery_key)
            if existing is not None:
                publications.append(existing)
                continue
            publication = Publication(
                bundle_id=bundle.id,
                platform=platform,
                destination=destination,
                status=PublicationStatus.SCHEDULED.value,
                scheduled_for=scheduled_for.astimezone(UTC),
                attempt_count=0,
                max_attempts=3,
                idempotency_key=str(uuid4()),
                delivery_key=delivery_key,
                external_message_ids=[],
            )
            try:
                self.repository.add_publication(publication)
                self.repository.commit()
                self.repository.refresh(publication)
            except IntegrityError:
                self.repository.rollback()
                publication = self.repository.publication_by_delivery_key(delivery_key)
                if publication is None:
                    raise
            except Exception:
                self.repository.rollback()
                raise
            publications.append(publication)
        return publications

    def run_due(self, *, now: datetime | None = None) -> list[Publication]:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        if self.repository.control().mode == PublishingMode.PAUSED.value:
            self.repository.commit()
            raise PublishingPaused("انتشار متوقف است")
        processed: list[Publication] = []
        for publication in self.repository.due(current):
            self._deliver(publication, current)
            processed.append(publication)
        return processed

    def publish_now(
        self, publication_id: int, *, now: datetime | None = None
    ) -> Publication:
        return self.publish_many_now([publication_id], now=now)[0]

    def publish_many_now(
        self, publication_ids: list[int], *, now: datetime | None = None
    ) -> list[Publication]:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        if self.repository.control().mode == PublishingMode.PAUSED.value:
            self.repository.commit()
            raise PublishingPaused("انتشار متوقف است")
        if not publication_ids:
            raise ScheduleInputError("هیچ موردی برای ارسال انتخاب نشده است")
        publications: list[Publication] = []
        for publication_id in publication_ids:
            publication = self.repository.get_publication(publication_id)
            if publication is None:
                raise ScheduleInputError("مورد ارسال پیدا نشد")
            publications.append(publication)
        for publication in publications:
            if publication.status in {
                PublicationStatus.SCHEDULED.value,
                PublicationStatus.RETRY_SCHEDULED.value,
            }:
                self._deliver(publication, current)
        return publications

    @staticmethod
    def _delivery_key(bundle_id: int, platform: str, destination: str) -> str:
        identity = f"{bundle_id}\x1f{platform}\x1f{destination}"
        return sha256(identity.encode("utf-8")).hexdigest()

    def _deliver(self, publication: Publication, current: datetime) -> None:
        if not self.repository.claim_for_delivery(publication.id):
            self.repository.refresh(publication)
            return
        self.repository.refresh(publication)
        adapter = self.adapters.get(publication.platform)
        if adapter is None:
            result = DeliveryResult.failure(
                code="adapter_unavailable",
                message="اتصال این پلتفرم در دسترس نیست",
                retryable=False,
            )
        else:
            try:
                result = adapter.send(
                    publication.bundle,
                    publication.destination,
                    publication.idempotency_key,
                )
            except Exception:
                result = DeliveryResult.failure(
                    code="adapter_exception",
                    message="ارسال با خطای موقت روبه‌رو شد",
                    retryable=True,
                )
        self._apply_result(publication, result, current)
        self.repository.commit()
        self.repository.refresh(publication)

    def _approve_automatically(self, draft) -> None:
        if draft.status == DraftStatus.APPROVED.value:
            return
        if draft.status not in {
            DraftStatus.DRAFT.value,
            DraftStatus.WAITING_APPROVAL.value,
        }:
            raise BundleInputError("این نسخه در وضعیت قابل انتشار نیست")
        current = self.repository.approved_in_series(draft.series_key)
        if current is not None and current.id != draft.id:
            current.status = DraftStatus.SUPERSEDED.value
        draft.status = DraftStatus.APPROVED.value
        draft.approved_at = datetime.now(UTC)

    def _source_image(self, draft) -> tuple[Path, str]:
        edited = self.repository.media_for_draft(draft.id, "image_edited")
        if edited is not None:
            path = self._private_asset_path(edited.relative_path)
            mime = edited.mime_type
        else:
            if self.require_edited_image:
                raise BundleInputError(
                    "ابتدا نسخه استودیویی تصویر را بسازید و بررسی کنید"
                )
            relative = draft.product.primary_image_path
            if not relative:
                raise BundleInputError("برای بسته نهایی باید تصویر محصول موجود باشد")
            path = self._product_image_path(draft.product.id, relative)
            mime = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".webp": "image/webp",
            }.get(path.suffix.lower(), "")
        if not path.is_file() or not mime:
            raise BundleInputError("فایل تصویر نهایی معتبر یا قابل دسترسی نیست")
        return path, mime

    def _private_asset_path(self, relative_path: str) -> Path:
        return self._safe_relative_path(relative_path, expected_prefix=("private",))

    def _product_image_path(self, product_id: int, relative_path: str) -> Path:
        return self._safe_relative_path(
            relative_path,
            expected_prefix=("products", str(product_id), "original"),
        )

    def _safe_relative_path(
        self, relative_path: str, *, expected_prefix: tuple[str, ...]
    ) -> Path:
        candidate = PurePosixPath(relative_path.replace("\\", "/"))
        windows = PureWindowsPath(relative_path)
        if (
            candidate.is_absolute()
            or windows.is_absolute()
            or ".." in candidate.parts
            or candidate.parts[: len(expected_prefix)] != expected_prefix
        ):
            raise BundleInputError("مسیر رسانه ذخیره‌شده معتبر نیست")
        return self.upload_root.joinpath(*candidate.parts)

    @staticmethod
    def _apply_result(
        publication: Publication, result: DeliveryResult, now: datetime
    ) -> None:
        if result.ok:
            publication.status = PublicationStatus.SUCCEEDED.value
            publication.external_message_ids = list(result.external_message_ids)
            publication.error_code = None
            publication.safe_error_message = None
            publication.published_at = now
            return
        publication.external_message_ids = list(result.external_message_ids)
        publication.error_code = result.error_code or "delivery_failed"
        publication.safe_error_message = (
            result.safe_error_message or "ارسال ناموفق بود"
        )
        if result.retryable and publication.attempt_count < publication.max_attempts:
            publication.status = PublicationStatus.RETRY_SCHEDULED.value
            delays = (timedelta(minutes=1), timedelta(minutes=5), timedelta(minutes=15))
            publication.scheduled_for = now + delays[publication.attempt_count - 1]
        else:
            publication.status = PublicationStatus.FAILED.value
