from decimal import Decimal

import pytest

from app.catalog.models import Product
from app.content.models import ContentDraft, DraftStatus
from app.media.voice import validate_voice
from app.media.voice_service import VoiceRepository, VoiceService


@pytest.fixture
def content_draft(db_session):
    product = Product(
        name="درب ممبران مدل آریا",
        description="طراحی نئوکلاسیک",
        price=Decimal("12500000"),
        availability="available",
        shipping_info="",
        attributes={},
        tags=[],
        active=True,
    )
    db_session.add(product)
    db_session.flush()
    draft = ContentDraft(
        product_id=product.id,
        series_key="voice-series",
        revision=1,
        user_brief="معرفی محصول برای ثبت سفارش",
        requested_angle="product_intro",
        provider_name="template",
        provider_payload={"headline": "معرفی محصول"},
        final_caption="این متن نهایی برای معرفی محصول ثبت شده است.",
        status=DraftStatus.WAITING_APPROVAL.value,
    )
    db_session.add(draft)
    db_session.commit()
    db_session.refresh(draft)
    return draft


@pytest.fixture
def voice_service(db_session, tmp_path):
    return VoiceService(VoiceRepository(db_session), tmp_path / "uploads")


def webm_voice(marker: bytes = b"first"):
    return validate_voice(
        b"\x1aE\xdf\xa3" + marker + b"\x00" * 24,
        "recording.webm",
        "audio/webm",
        duration_ms=1500,
    )


def test_attach_persists_private_metadata_and_original_bytes(
    voice_service, content_draft
):
    voice = webm_voice()

    asset = voice_service.attach_or_replace(content_draft.id, voice)
    path = voice_service.path_for(asset)

    assert asset.kind == "voice_original"
    assert asset.sha256 == voice.sha256
    assert path.read_bytes() == voice.data
    assert asset.relative_path.startswith("private/voices/")


def test_replace_commits_new_voice_before_removing_old_file(
    voice_service, content_draft
):
    first = voice_service.attach_or_replace(content_draft.id, webm_voice(b"first"))
    old_path = voice_service.path_for(first)

    second = voice_service.attach_or_replace(content_draft.id, webm_voice(b"second"))
    new_path = voice_service.path_for(second)

    assert second.id == first.id
    assert new_path.read_bytes() == webm_voice(b"second").data
    assert not old_path.exists()


def test_failed_commit_cleans_new_voice_and_preserves_database(
    voice_service, content_draft, monkeypatch
):
    def fail_commit():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(voice_service.repository, "commit", fail_commit)

    with pytest.raises(RuntimeError):
        voice_service.attach_or_replace(content_draft.id, webm_voice())

    files = list((voice_service.upload_root / "private").rglob("*.webm"))
    assert files == []
    assert voice_service.repository.for_draft(content_draft.id) is None


def test_failed_delete_keeps_original_file(
    voice_service, content_draft, monkeypatch
):
    asset = voice_service.attach_or_replace(content_draft.id, webm_voice())
    path = voice_service.path_for(asset)

    def fail_commit():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(voice_service.repository, "commit", fail_commit)
    with pytest.raises(RuntimeError):
        voice_service.delete(content_draft.id)

    assert path.exists()
    assert voice_service.repository.for_draft(content_draft.id) is not None


def test_successful_delete_removes_metadata_and_file(voice_service, content_draft):
    asset = voice_service.attach_or_replace(content_draft.id, webm_voice())
    path = voice_service.path_for(asset)

    voice_service.delete(content_draft.id)

    assert not path.exists()
    assert voice_service.repository.for_draft(content_draft.id) is None
