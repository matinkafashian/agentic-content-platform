from typing import Protocol

from app.content.schemas import (
    ContentGenerationRequest,
    GeneratedContent,
)


class ContentProvider(Protocol):
    name: str

    def generate(self, request: ContentGenerationRequest) -> GeneratedContent: ...


HEADLINES = {
    "product_intro": "✨ معرفی {name}",
    "educational": "📚 نکته‌ای درباره {name}",
    "faq": "❓ درباره {name} بیشتر بدانید",
    "problem_solution": "🛠️ بررسی کاربرد {name}",
    "trust": "🤝 جزئیات مهم {name}",
    "order_guide": "📝 راهنمای سفارش {name}",
}


class TemplateContentProvider:
    name = "template"

    def generate(self, request: ContentGenerationRequest) -> GeneratedContent:
        product = request.product
        brand = request.brand
        body_parts = [request.user_brief]
        if product.description and product.description not in body_parts:
            body_parts.append(product.description)

        benefits = [
            f"✅ {key}: {value}" for key, value in product.attributes.items()
        ]
        if product.shipping_info:
            benefits.append(f"🚚 {product.shipping_info}")
        benefits.extend(f"⭐ {claim}" for claim in brand.approved_claims)
        if not benefits:
            benefits.append(f"🔹 {request.user_brief}")

        hashtags = list(
            dict.fromkeys([*product.tags, *brand.default_hashtags])
        )[:6]
        used_emojis = ["✨", "✅"]
        if product.shipping_info:
            used_emojis.append("🚚")
        if brand.approved_claims:
            used_emojis.append("⭐")

        return GeneratedContent(
            headline=HEADLINES[request.requested_angle].format(name=product.name),
            body="\n\n".join(body_parts),
            benefits=benefits[:5],
            cta=brand.default_cta,
            hashtags=hashtags,
            used_emojis=used_emojis,
            content_angle=request.requested_angle,
        )


def _format_price_fa(value: object) -> str:
    western = f"{value:,.0f}"
    return western.translate(str.maketrans("0123456789,", "۰۱۲۳۴۵۶۷۸۹٬"))


def compose_caption(
    generated: GeneratedContent, request: ContentGenerationRequest
) -> str:
    price_line = f"💰 قیمت: {_format_price_fa(request.product.price)} تومان"
    hashtag_line = " ".join(f"#{tag}" for tag in generated.hashtags)
    sections = [
        generated.headline,
        generated.body,
        "\n".join(generated.benefits),
        price_line,
        generated.cta,
        request.brand.support_handle,
        hashtag_line,
    ]
    return "\n\n".join(section for section in sections if section)
