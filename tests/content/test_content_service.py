from decimal import Decimal

import pytest

from app.brand.repository import BrandRepository
from app.brand.service import BrandService
from app.catalog.models import Product
from app.catalog.repository import ProductRepository
from app.content.models import DraftStatus
from app.content.providers import TemplateContentProvider
from app.content.repository import ContentRepository
from app.content.service import (
    ContentInputError,
    ContentNotFound,
    ContentService,
    ContentStateError,
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
        price=Decimal("12500000"),
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
        user_brief="روی طراحی نئوکلاسیک و مشخصات ثبت‌شده تمرکز شود.",
        requested_angle="product_intro",
    )


def test_generate_persists_provider_snapshot_and_does_not_change_product(
    content_service, product
):
    original_description = product.description

    draft = content_service.generate(
        product.id,
        user_brief="روی طراحی نئوکلاسیک و مشخصات ثبت‌شده تمرکز شود.",
        requested_angle="product_intro",
    )

    assert draft.status == DraftStatus.WAITING_APPROVAL.value
    assert draft.revision == 1
    assert draft.provider_name == "template"
    assert draft.provider_payload["headline"]
    assert "#درب_ممبران" in draft.final_caption
    assert product.description == original_description


def test_regenerate_creates_revision_without_overwriting_previous(
    content_service, draft
):
    first_payload = dict(draft.provider_payload)

    second = content_service.regenerate(draft.id)

    assert second.id != draft.id
    assert second.series_key == draft.series_key
    assert second.parent_id == draft.id
    assert second.revision == 2
    assert content_service.get(draft.id).provider_payload == first_payload
    assert [item.revision for item in content_service.history(draft.id)] == [2, 1]


def test_approving_new_revision_supersedes_old_approved_atomically(
    content_service, draft
):
    content_service.approve(draft.id)
    second = content_service.regenerate(draft.id)

    approved = content_service.approve(second.id)

    assert content_service.get(draft.id).status == DraftStatus.SUPERSEDED.value
    assert approved.status == DraftStatus.APPROVED.value
    assert approved.approved_at is not None


def test_edit_caption_does_not_change_provider_snapshot(content_service, draft):
    original_payload = dict(draft.provider_payload)

    updated = content_service.edit_caption(
        draft.id, "این یک کپشن ویرایش‌شده و معتبر برای انتشار آزمایشی است."
    )

    assert updated.final_caption.startswith("این یک کپشن ویرایش‌شده")
    assert updated.provider_payload == original_payload


@pytest.mark.parametrize("status", [DraftStatus.APPROVED, DraftStatus.SUPERSEDED])
def test_edit_rejects_locked_revision(content_service, draft, status):
    draft.status = status.value
    content_service.repository.commit()

    with pytest.raises(ContentStateError):
        content_service.edit_caption(
            draft.id, "این کپشن به اندازه کافی بلند است اما نباید ذخیره شود."
        )


def test_rejected_revision_cannot_be_approved(content_service, draft):
    content_service.reject(draft.id)

    with pytest.raises(ContentStateError):
        content_service.approve(draft.id)


def test_generate_rejects_inactive_or_missing_product(content_service, product):
    product.active = False
    content_service.product_repository.commit()

    with pytest.raises(ContentInputError):
        content_service.generate(
            product.id,
            user_brief="این توضیح برای تست محصول غیرفعال کافی و معتبر است.",
            requested_angle="product_intro",
        )
    with pytest.raises(ContentInputError):
        content_service.generate(
            99999,
            user_brief="این توضیح برای تست محصول ناموجود کافی و معتبر است.",
            requested_angle="product_intro",
        )


def test_generate_rejects_blank_brief(content_service, product):
    with pytest.raises(ContentInputError):
        content_service.generate(
            product.id, user_brief="  ", requested_angle="product_intro"
        )


def test_unknown_draft_raises_content_not_found(content_service):
    with pytest.raises(ContentNotFound):
        content_service.get(99999)


def test_failed_approval_rolls_back_previous_approved_state(
    content_service, draft, monkeypatch
):
    content_service.approve(draft.id)
    second = content_service.regenerate(draft.id)

    def fail_commit():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(content_service.repository, "commit", fail_commit)
    with pytest.raises(RuntimeError):
        content_service.approve(second.id)

    content_service.repository.session.expire_all()
    assert content_service.get(draft.id).status == DraftStatus.APPROVED.value
    assert content_service.get(second.id).status == DraftStatus.WAITING_APPROVAL.value
