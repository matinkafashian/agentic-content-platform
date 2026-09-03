from app.content.providers import TemplateContentProvider, compose_caption
from app.content.schemas import BrandFacts, ContentGenerationRequest, ProductFacts


def content_request() -> ContentGenerationRequest:
    return ContentGenerationRequest(
        product=ProductFacts(
            name="درب ممبران مدل آریا",
            description="طراحی نئوکلاسیک با خطوط عمودی",
            availability="available",
            shipping_info="ارسال به سراسر ایران",
            attributes={"متریال": "MDF", "رنگ": "سفید"},
            tags=["درب ممبران", "نئوکلاسیک"],
        ),
        brand=BrandFacts(
            business_name="هایکا",
            tagline="تفاوت در جزئیات",
            audience="کابینت‌سازان حرفه‌ای",
            tone_guidelines="تخصصی و محترمانه",
            support_handle="@hayka_poshtibani",
            default_cta="برای مشاوره و ثبت سفارش پیام دهید.",
            approved_claims=[],
            default_hashtags=["هایکا"],
        ),
        user_brief="مدلی مناسب پروژه‌های نئوکلاسیک معرفی شود.",
        requested_angle="product_intro",
    )


def test_template_provider_adds_structure_without_unapproved_claims():
    request = content_request()
    generated = TemplateContentProvider().generate(request)
    caption = compose_caption(generated, request)

    assert generated.headline == "✨ معرفی درب ممبران مدل آریا"
    assert "✅ متریال: MDF" in generated.benefits
    assert "✅ رنگ: سفید" in generated.benefits
    assert "🚚 ارسال به سراسر ایران" in generated.benefits
    assert "۱۸ ماه" not in caption
    assert "تخفیف" not in caption
    assert "@hayka_poshtibani" in caption
    assert "#درب_ممبران" in caption
    assert "۱۲٬۵۰۰٬۰۰۰" not in caption
    assert "💰 قیمت:" not in caption
    assert "برای استعلام قیمت و ثبت سفارش، به ادمین پیام دهید" in caption


def test_template_provider_is_deterministic_for_the_same_request():
    request = content_request()
    provider = TemplateContentProvider()

    first = compose_caption(provider.generate(request), request)
    second = compose_caption(provider.generate(request), request)

    assert first == second


def test_template_provider_can_generate_without_manager_note():
    request = content_request().model_copy(update={"user_brief": ""})

    generated = TemplateContentProvider().generate(request)
    caption = compose_caption(generated, request)

    assert request.product.description in generated.body
    assert request.product.name in caption
    assert "#درب_ممبران" in caption


def test_template_provider_uses_only_manager_brief_when_no_benefit_facts_exist():
    request = content_request().model_copy(
        update={
            "product": content_request().product.model_copy(
                update={"attributes": {}, "shipping_info": ""}
            )
        }
    )

    generated = TemplateContentProvider().generate(request)

    assert generated.benefits == ["🔹 مدلی مناسب پروژه‌های نئوکلاسیک معرفی شود."]
