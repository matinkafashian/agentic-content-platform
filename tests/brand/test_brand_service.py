import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.brand.models import BrandProfile
from app.brand.repository import BrandRepository
from app.brand.schemas import BrandProfileInput
from app.brand.service import BrandService


def brand_input(**overrides) -> BrandProfileInput:
    values = {
        "business_name": "هایکا",
        "tagline": "تفاوت در جزئیات",
        "audience": "کابینت‌سازان حرفه‌ای",
        "tone_guidelines": "تخصصی و محترمانه",
        "support_handle": "hayka_poshtibani",
        "default_cta": "برای ثبت سفارش پیام دهید.",
        "approved_claims": [" ارسال سراسر ایران ", "", "ارسال سراسر ایران"],
        "default_hashtags": ["#درب ممبران", "درب_ممبران", " هایکا "],
    }
    values.update(overrides)
    return BrandProfileInput(**values)


def test_brand_input_normalizes_handle_claims_and_hashtags():
    data = brand_input()

    assert data.business_name == "هایکا"
    assert data.support_handle == "@hayka_poshtibani"
    assert data.approved_claims == ["ارسال سراسر ایران"]
    assert data.default_hashtags == ["درب_ممبران", "هایکا"]


def test_brand_input_rejects_invalid_support_handle():
    with pytest.raises(ValidationError):
        brand_input(support_handle="پشتیبانی هایکا")


def test_get_or_create_uses_safe_defaults_without_sales_claims(db_session):
    service = BrandService(BrandRepository(db_session))

    profile = service.get_or_create()

    assert profile.business_name == "هایکا"
    assert profile.support_handle == "@hayka_poshtibani"
    assert profile.approved_claims == []
    assert profile.default_hashtags == ["هایکا", "درب_ممبران", "نئوکلاسیک"]


def test_get_or_create_is_idempotent(db_session):
    service = BrandService(BrandRepository(db_session))

    first = service.get_or_create()
    second = service.get_or_create()
    count = db_session.scalar(select(func.count(BrandProfile.id)))

    assert second.id == first.id
    assert count == 1


def test_update_changes_the_existing_profile_without_creating_another(db_session):
    service = BrandService(BrandRepository(db_session))
    original = service.get_or_create()

    updated = service.update(brand_input(tagline="هر قطعه چوب، یک اثر"))
    count = db_session.scalar(select(func.count(BrandProfile.id)))

    assert updated.id == original.id
    assert updated.tagline == "هر قطعه چوب، یک اثر"
    assert updated.approved_claims == ["ارسال سراسر ایران"]
    assert count == 1
