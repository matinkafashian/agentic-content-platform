from app.catalog.models import Product
from app.content.models import ContentDraft, DraftStatus


def test_content_revision_keeps_provider_payload_separate_from_final_caption(db_session):
    product = Product(
        name="میز کانتر",
        description="نمای شیاردار",
        availability="available",
        shipping_info="ارسال سراسر ایران",
        attributes={"متریال": "MDF"},
        tags=["دکوراسیون"],
        active=True,
    )
    db_session.add(product)
    db_session.flush()
    draft = ContentDraft(
        product_id=product.id,
        series_key="series-1",
        revision=1,
        user_brief="برای کابینت‌سازان حرفه‌ای",
        requested_angle="product_intro",
        provider_name="template",
        provider_payload={"headline": "عنوان اولیه"},
        final_caption="نسخه قابل ویرایش",
        status=DraftStatus.WAITING_APPROVAL.value,
    )
    db_session.add(draft)
    db_session.commit()
    db_session.refresh(draft)

    assert draft.provider_payload == {"headline": "عنوان اولیه"}
    assert draft.final_caption == "نسخه قابل ویرایش"
    assert draft.product.name == "میز کانتر"
    assert draft.created_at.tzinfo is not None
