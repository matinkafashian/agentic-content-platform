from app.catalog.models import Product
from app.content.models import ContentDraft, DraftStatus
from app.media.models import MediaAsset


def test_media_asset_keeps_private_relative_path_and_voice_metadata(db_session):
    product = Product(
        name="میز کانتر",
        description="نمای شیاردار",
        availability="available",
        shipping_info="",
        attributes={},
        tags=[],
        active=True,
    )
    db_session.add(product)
    db_session.flush()
    content_draft = ContentDraft(
        product_id=product.id,
        series_key="series-voice",
        revision=1,
        user_brief="معرفی محصول",
        requested_angle="product_intro",
        provider_name="template",
        provider_payload={"headline": "معرفی محصول"},
        final_caption="متن نهایی معرفی محصول",
        status=DraftStatus.WAITING_APPROVAL.value,
    )
    db_session.add(content_draft)
    db_session.flush()

    asset = MediaAsset(
        content_draft_id=content_draft.id,
        kind="voice_original",
        relative_path=f"private/voices/{content_draft.id}/abc.webm",
        mime_type="audio/webm",
        size_bytes=4,
        sha256="0" * 64,
        duration_ms=1500,
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)

    assert asset.relative_path.startswith("private/voices/")
    assert asset.kind == "voice_original"
    assert asset.duration_ms == 1500
    assert asset.created_at.tzinfo is not None
