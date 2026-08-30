from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.content.schemas import (
    BrandFacts,
    ContentGenerationRequest,
    GeneratedContent,
    ProductFacts,
)


def valid_request(**overrides) -> ContentGenerationRequest:
    values = {
        "product": ProductFacts(
            name="درب ممبران مدل آریا",
            description="طراحی نئوکلاسیک",
            price=Decimal("12500000"),
            availability="available",
            shipping_info="ارسال به سراسر ایران",
            attributes={"متریال": "MDF"},
            tags=["#درب ممبران", "درب_ممبران", "نئوکلاسیک"],
        ),
        "brand": BrandFacts(
            business_name="هایکا",
            tagline="تفاوت در جزئیات",
            audience="کابینت‌سازان حرفه‌ای",
            tone_guidelines="تخصصی و محترمانه",
            support_handle="@hayka_poshtibani",
            default_cta="برای مشاوره و ثبت سفارش پیام دهید.",
            approved_claims=[],
            default_hashtags=["هایکا"],
        ),
        "user_brief": "این مدل برای پروژه‌های نئوکلاسیک معرفی شود.",
        "requested_angle": "product_intro",
    }
    values.update(overrides)
    return ContentGenerationRequest(**values)


def test_product_facts_normalize_duplicate_hashtags():
    request = valid_request()

    assert request.product.tags == ["درب_ممبران", "نئوکلاسیک"]


def test_request_rejects_unknown_content_angle():
    with pytest.raises(ValidationError):
        valid_request(requested_angle="made_up_angle")


def test_generated_content_rejects_empty_benefits():
    with pytest.raises(ValidationError):
        GeneratedContent(
            headline="معرفی محصول",
            body="توضیحات معتبر محصول",
            benefits=[],
            cta="پیام دهید.",
            hashtags=["هایکا"],
            used_emojis=["✨"],
            content_angle="product_intro",
        )


def test_generated_content_forbids_unknown_json_fields():
    with pytest.raises(ValidationError):
        GeneratedContent(
            headline="معرفی محصول",
            body="توضیحات معتبر محصول",
            benefits=["✅ متریال: MDF"],
            cta="پیام دهید.",
            hashtags=["هایکا"],
            used_emojis=["✨"],
            content_angle="product_intro",
            unsupported_claim="تخفیف ویژه",
        )


def test_generated_content_keeps_at_most_six_hashtags():
    with pytest.raises(ValidationError):
        GeneratedContent(
            headline="معرفی محصول",
            body="توضیحات معتبر محصول",
            benefits=["✅ متریال: MDF"],
            cta="پیام دهید.",
            hashtags=[f"tag_{index}" for index in range(7)],
            used_emojis=["✨"],
            content_angle="product_intro",
        )

