from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest

from app.brand.repository import BrandRepository
from app.brand.service import BrandService
from app.catalog.models import Product
from app.catalog.repository import ProductRepository
from app.content.models import DraftStatus
from app.content.providers import TemplateContentProvider
from app.content.repository import ContentRepository
from app.content.service import ContentService
from app.media.models import MediaAsset
from app.publishing.adapters import DeliveryResult
from app.publishing.models import PublicationStatus, PublishingMode
from app.publishing.repository import PublishingRepository
from app.publishing.service import (
    BundleInputError,
    PublishingPaused,
    PublishingService,
)
from app.publishing.telegram import TelegramAdapter


class SuccessfulAdapter:
    platform = "sandbox"

    def send(self, bundle, destination, idempotency_key):
        return DeliveryResult.success([f"sandbox-{idempotency_key}"])


class TemporaryFailureAdapter:
    platform = "sandbox"

    def send(self, bundle, destination, idempotency_key):
        return DeliveryResult.failure(
            code="temporary_unavailable",
            message="سرویس آزمایشی موقتاً در دسترس نیست",
            retryable=True,
        )


class PartialFailureAdapter:
    platform = "sandbox"

    def send(self, bundle, destination, idempotency_key):
        return DeliveryResult(
            ok=False,
            external_message_ids=["telegram-photo-321"],
            error_code="telegram_voice_partial",
            safe_error_message="پست اصلی ارسال شد، اما وویس ارسال نشد",
            retryable=False,
        )


class NamedSuccessfulAdapter:
    def __init__(self, platform):
        self.platform = platform

    def send(self, bundle, destination, idempotency_key):
        return DeliveryResult.success([f"{self.platform}-{idempotency_key}"])


class NamedFailureAdapter:
    def __init__(self, platform):
        self.platform = platform

    def send(self, bundle, destination, idempotency_key):
        return DeliveryResult.failure(
            code=f"{self.platform}_unavailable",
            message=f"ارسال {self.platform} انجام نشد؛ اتصال را بررسی کنید",
            retryable=False,
        )


@pytest.fixture
def content_service(db_session):
    BrandService(BrandRepository(db_session)).get_or_create()
    return ContentService(
        ContentRepository(db_session),
        ProductRepository(db_session),
        BrandRepository(db_session),
        TemplateContentProvider(),
    )


@pytest.fixture
def product(db_session):
    item = Product(
        name="درب ممبران مدل آریا",
        description="طراحی نئوکلاسیک با خطوط عمودی",
        availability="available",
        shipping_info="ارسال به سراسر ایران",
        attributes={"متریال": "MDF"},
        tags=["درب ممبران", "نئوکلاسیک"],
        active=True,
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    return item


@pytest.fixture
def draft(content_service, product):
    return content_service.generate(
        product.id,
        user_brief="برای ساخت بسته نهایی، معرفی حرفه‌ای و دقیق آماده شود.",
        requested_angle="product_intro",
    )


def _service(db_session, tmp_path, adapter=None, *, require_edited_image=False):
    return PublishingService(
        PublishingRepository(db_session),
        tmp_path / "uploads",
        {"sandbox": adapter or SuccessfulAdapter()},
        require_edited_image=require_edited_image,
    )


def _approved_draft(content_service, draft):
    content_service.approve(draft.id)
    return draft


def _attach_original_image(db_session, tmp_path, product, data=b"image-snapshot"):
    relative = f"products/{product.id}/original/source.png"
    path = tmp_path / "uploads" / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    product.primary_image_path = relative
    db_session.commit()
    return data


def test_bundle_snapshots_caption_image_and_optional_voice(
    db_session, tmp_path, content_service, draft, product
):
    image = _attach_original_image(db_session, tmp_path, product)
    voice = b"\x1aE\xdf\xa3voice" + b"\x00" * 24
    voice_path = tmp_path / "uploads/private/voices/1/voice.webm"
    voice_path.parent.mkdir(parents=True, exist_ok=True)
    voice_path.write_bytes(voice)
    db_session.add(
        MediaAsset(
            content_draft_id=draft.id,
            kind="voice_original",
            relative_path="private/voices/1/voice.webm",
            mime_type="audio/webm",
            size_bytes=len(voice),
            sha256=sha256(voice).hexdigest(),
            duration_ms=1200,
        )
    )
    db_session.commit()
    _approved_draft(content_service, draft)

    bundle = _service(db_session, tmp_path).create_bundle(draft.id)

    assert bundle.caption_snapshot == draft.final_caption
    assert bundle.image_sha256 == sha256(image).hexdigest()
    assert bundle.voice_sha256 == sha256(voice).hexdigest()
    assert (tmp_path / "uploads" / bundle.image_relative_path).read_bytes() == image
    assert (tmp_path / "uploads" / bundle.voice_relative_path).read_bytes() == voice
    (tmp_path / "uploads" / product.primary_image_path).write_bytes(b"changed-source")
    voice_path.write_bytes(b"changed-voice")
    assert (tmp_path / "uploads" / bundle.image_relative_path).read_bytes() == image
    assert (tmp_path / "uploads" / bundle.voice_relative_path).read_bytes() == voice


def test_bundle_creation_is_idempotent(
    db_session, tmp_path, content_service, draft, product
):
    _attach_original_image(db_session, tmp_path, product)
    _approved_draft(content_service, draft)
    service = _service(db_session, tmp_path)

    first = service.create_bundle(draft.id)
    second = service.create_bundle(draft.id)

    assert second.id == first.id
    assert second.bundle_key == first.bundle_key


def test_manual_mode_requires_approved_draft(
    db_session, tmp_path, draft, product
):
    _attach_original_image(db_session, tmp_path, product)

    with pytest.raises(BundleInputError, match="تأیید"):
        _service(db_session, tmp_path).create_bundle(draft.id)


def test_real_image_workflow_requires_edited_image_before_bundle(
    db_session, tmp_path, content_service, draft, product
):
    _attach_original_image(db_session, tmp_path, product)
    _approved_draft(content_service, draft)

    with pytest.raises(BundleInputError, match="نسخه استودیویی"):
        _service(
            db_session, tmp_path, require_edited_image=True
        ).create_bundle(draft.id)


def test_automatic_mode_approves_safe_waiting_draft(
    db_session, tmp_path, draft, product
):
    _attach_original_image(db_session, tmp_path, product)
    service = _service(db_session, tmp_path)
    service.set_mode(PublishingMode.AUTOMATIC)

    bundle = service.create_bundle(draft.id)

    assert bundle.content_draft_id == draft.id
    assert draft.status == DraftStatus.APPROVED.value


def test_pause_keeps_due_publication_scheduled(
    db_session, tmp_path, content_service, draft, product
):
    _attach_original_image(db_session, tmp_path, product)
    _approved_draft(content_service, draft)
    service = _service(db_session, tmp_path)
    bundle = service.create_bundle(draft.id)
    publication = service.schedule(
        bundle.id,
        platform="sandbox",
        destination="کانال آزمایشی",
        scheduled_for=datetime.now(UTC) - timedelta(minutes=1),
    )
    service.set_mode(PublishingMode.PAUSED)

    with pytest.raises(PublishingPaused):
        service.run_due()

    db_session.refresh(publication)
    assert publication.status == PublicationStatus.SCHEDULED.value
    assert publication.attempt_count == 0


def test_due_publication_records_success_and_external_ids(
    db_session, tmp_path, content_service, draft, product
):
    _attach_original_image(db_session, tmp_path, product)
    _approved_draft(content_service, draft)
    service = _service(db_session, tmp_path)
    bundle = service.create_bundle(draft.id)
    publication = service.schedule(
        bundle.id,
        platform="sandbox",
        destination="کانال آزمایشی",
        scheduled_for=datetime.now(UTC) - timedelta(seconds=1),
    )

    processed = service.run_due()

    assert [item.id for item in processed] == [publication.id]
    assert publication.status == PublicationStatus.SUCCEEDED.value
    assert publication.attempt_count == 1
    assert publication.external_message_ids == [
        f"sandbox-{publication.idempotency_key}"
    ]
    assert publication.published_at is not None


def test_publish_now_processes_only_the_selected_publication(
    db_session, tmp_path, content_service, draft, product
):
    _attach_original_image(db_session, tmp_path, product)
    _approved_draft(content_service, draft)
    service = _service(db_session, tmp_path)
    bundle = service.create_bundle(draft.id)
    selected = service.schedule(
        bundle.id,
        platform="sandbox",
        destination="کانال اول",
        scheduled_for=datetime.now(UTC),
    )
    other = service.schedule(
        bundle.id,
        platform="sandbox",
        destination="کانال دوم",
        scheduled_for=datetime.now(UTC),
    )

    published = service.publish_now(selected.id)

    assert published.id == selected.id
    assert selected.status == PublicationStatus.SUCCEEDED.value
    assert selected.attempt_count == 1
    assert other.status == PublicationStatus.SCHEDULED.value
    assert other.attempt_count == 0


def test_multi_platform_publish_keeps_each_result_independent(
    db_session, tmp_path, content_service, draft, product
):
    _attach_original_image(db_session, tmp_path, product)
    _approved_draft(content_service, draft)
    service = PublishingService(
        PublishingRepository(db_session),
        tmp_path / "uploads",
        {
            "telegram": NamedSuccessfulAdapter("telegram"),
            "bale": NamedFailureAdapter("bale"),
        },
    )
    bundle = service.create_bundle(draft.id)

    publications = service.schedule_many(
        bundle.id,
        destinations={
            "telegram": "@telegram_channel",
            "bale": "@bale_channel",
        },
        scheduled_for=datetime.now(UTC),
    )
    results = service.publish_many_now([item.id for item in publications])

    assert [item.platform for item in results] == ["telegram", "bale"]
    assert results[0].status == PublicationStatus.SUCCEEDED.value
    assert results[1].status == PublicationStatus.FAILED.value
    assert results[1].safe_error_message == (
        "ارسال bale انجام نشد؛ اتصال را بررسی کنید"
    )
    assert all(item.attempt_count == 1 for item in results)


def test_retryable_failure_is_rescheduled_with_safe_error(
    db_session, tmp_path, content_service, draft, product
):
    _attach_original_image(db_session, tmp_path, product)
    _approved_draft(content_service, draft)
    service = _service(db_session, tmp_path, TemporaryFailureAdapter())
    bundle = service.create_bundle(draft.id)
    publication = service.schedule(
        bundle.id,
        platform="sandbox",
        destination="کانال آزمایشی",
        scheduled_for=datetime.now(UTC) - timedelta(seconds=1),
    )

    service.run_due(now=datetime.now(UTC))

    assert publication.status == PublicationStatus.RETRY_SCHEDULED.value
    assert publication.attempt_count == 1
    assert publication.error_code == "temporary_unavailable"
    assert publication.safe_error_message == "سرویس آزمایشی موقتاً در دسترس نیست"
    assert publication.scheduled_for > datetime.now(UTC)

    service.run_due(now=publication.scheduled_for)
    service.run_due(now=publication.scheduled_for)

    assert publication.status == PublicationStatus.FAILED.value
    assert publication.attempt_count == 3


def test_publication_can_be_claimed_for_delivery_only_once(
    db_session, tmp_path, content_service, draft, product
):
    _attach_original_image(db_session, tmp_path, product)
    _approved_draft(content_service, draft)
    service = _service(db_session, tmp_path, SuccessfulAdapter())
    bundle = service.create_bundle(draft.id)
    publication = service.schedule(
        bundle.id,
        platform="sandbox",
        destination="کانال آزمایشی",
        scheduled_for=datetime.now(UTC),
    )
    repository = PublishingRepository(db_session)

    first_claim = repository.claim_for_delivery(publication.id)
    second_claim = repository.claim_for_delivery(publication.id)
    repository.refresh(publication)

    assert first_claim is True
    assert second_claim is False
    assert publication.status == PublicationStatus.PUBLISHING.value
    assert publication.attempt_count == 1


def test_partial_failure_preserves_sent_message_ids_without_retry(
    db_session, tmp_path, content_service, draft, product
):
    _attach_original_image(db_session, tmp_path, product)
    _approved_draft(content_service, draft)
    service = _service(db_session, tmp_path, PartialFailureAdapter())
    bundle = service.create_bundle(draft.id)
    publication = service.schedule(
        bundle.id,
        platform="sandbox",
        destination="@test_channel",
        scheduled_for=datetime.now(UTC) - timedelta(seconds=1),
    )

    service.run_due(now=datetime.now(UTC))

    assert publication.status == PublicationStatus.FAILED.value
    assert publication.attempt_count == 1
    assert publication.external_message_ids == ["telegram-photo-321"]
    assert publication.error_code == "telegram_voice_partial"


def test_telegram_allows_caption_longer_than_photo_caption_limit(
    db_session, tmp_path, content_service, draft, product
):
    _attach_original_image(db_session, tmp_path, product)
    draft.final_caption = "الف" * 1057
    db_session.commit()
    _approved_draft(content_service, draft)
    adapter = TelegramAdapter(
        bot_token="123:test-token",
        upload_root=tmp_path / "uploads",
    )
    service = PublishingService(
        PublishingRepository(db_session),
        tmp_path / "uploads",
        {"telegram": adapter},
    )
    bundle = service.create_bundle(draft.id)

    publication = service.schedule(
        bundle.id,
        platform="telegram",
        destination="@test_channel",
        scheduled_for=datetime.now(UTC),
    )

    assert publication.platform == "telegram"
    assert publication.status == PublicationStatus.SCHEDULED.value

    adapter.close()
