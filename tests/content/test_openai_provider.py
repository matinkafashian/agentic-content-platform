import json

import httpx
import pytest

from app.content.openai_provider import (
    ContentProviderInvalidResponse,
    ContentProviderUnavailable,
    OpenAIContentProvider,
)
from tests.content.test_template_provider import content_request


def _response_payload(content: dict[str, object]) -> dict[str, object]:
    return {
        "id": "resp_test_123",
        "status": "completed",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(content, ensure_ascii=False),
                    }
                ],
            }
        ],
        "usage": {"input_tokens": 240, "output_tokens": 180, "total_tokens": 420},
    }


def _valid_generated_content() -> dict[str, object]:
    return {
        "headline": "ظرافت نئوکلاسیک برای یک انتخاب حرفه‌ای",
        "body": (
            "درب ممبران مدل آریا با طراحی نئوکلاسیک و خطوط عمودی، "
            "برای پروژه‌هایی با جزئیات منظم معرفی می‌شود."
        ),
        "benefits": [
            "متریال ثبت‌شده: MDF",
            "رنگ ثبت‌شده: سفید",
            "ارسال به سراسر ایران",
        ],
        "cta": "این متن نباید جای CTA ثبت‌شده برند را بگیرد.",
        "hashtags": ["درب ممبران", "نئوکلاسیک", "طراحی داخلی"],
        "used_emojis": ["✨", "✅", "🎨", "🚚"],
        "content_angle": "product_intro",
    }


def test_openai_provider_uses_responses_structured_output_and_verified_cta():
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers["authorization"]
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json=_response_payload(_valid_generated_content()))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenAIContentProvider(
        api_key="sk-test-not-a-real-secret",
        model="gpt-test-model",
        client=client,
    )

    request_with_examples = content_request().model_copy(
        update={"style_examples": ["نمونه تأییدشده قبلی با لحن حرفه‌ای."]}
    )
    generated = provider.generate(request_with_examples)

    assert provider.name == "openai:gpt-test-model"
    assert generated.headline.startswith("✨")
    assert generated.benefits[0].startswith("🪵")
    assert generated.benefits[1].startswith("🎨")
    assert generated.benefits[2].startswith("🚚")
    assert {"✨", "🪵", "🎨", "🚚"}.issubset(set(generated.used_emojis))
    assert generated.cta == content_request().brand.default_cta
    assert generated.content_angle == content_request().requested_angle
    assert captured["authorization"] == "Bearer sk-test-not-a-real-secret"
    payload = captured["payload"]
    assert payload["model"] == "gpt-test-model"
    assert payload["store"] is False
    assert payload["text"]["format"]["type"] == "json_schema"
    assert payload["text"]["format"]["strict"] is True
    assert payload["text"]["format"]["schema"]["additionalProperties"] is False
    assert set(payload["text"]["format"]["schema"]["required"]) == set(
        payload["text"]["format"]["schema"]["properties"]
    )
    assert payload["text"]["format"]["schema"]["properties"]["content_angle"][
        "enum"
    ] == ["product_intro"]
    assert "body دقیقاً یک پاراگراف کوتاه" in payload["instructions"]
    assert "CTA، شناسه پشتیبانی" in payload["instructions"]
    model_input = json.loads(payload["input"])
    assert model_input["approved_style_examples"] == [
        "نمونه تأییدشده قبلی با لحن حرفه‌ای."
    ]
    assert "کپی" in payload["instructions"]


@pytest.mark.parametrize("status_code", [401, 429, 500])
def test_openai_provider_returns_safe_error_for_api_failures(status_code):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            json={"error": {"message": "server echoed sk-sensitive-value"}},
            request=request,
        )

    provider = OpenAIContentProvider(
        api_key="sk-sensitive-value",
        model="gpt-test-model",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(ContentProviderUnavailable) as exc_info:
        provider.generate(content_request())

    assert "sk-sensitive-value" not in str(exc_info.value)
    assert "OpenAI" in str(exc_info.value)


def test_openai_provider_rejects_invalid_or_incomplete_output():
    invalid = _valid_generated_content()
    invalid["benefits"] = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_response_payload(invalid), request=request)

    provider = OpenAIContentProvider(
        api_key="sk-test-not-a-real-secret",
        model="gpt-test-model",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(ContentProviderInvalidResponse, match="خروجی معتبر"):
        provider.generate(content_request())


def test_openai_provider_rejects_non_completed_response():
    payload = _response_payload(_valid_generated_content())
    payload["status"] = "incomplete"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload, request=request)

    provider = OpenAIContentProvider(
        api_key="sk-test-not-a-real-secret",
        model="gpt-test-model",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(ContentProviderInvalidResponse, match="کامل نشد"):
        provider.generate(content_request())


def test_openai_provider_rejects_sensitive_claims_missing_from_admin_input():
    unsupported = _valid_generated_content()
    unsupported["body"] = "این محصول با ضمانت ویژه عرضه می‌شود."
    unsupported["benefits"] = ["تخفیف ویژه سفارش"]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_response_payload(unsupported), request=request)

    provider = OpenAIContentProvider(
        api_key="sk-test-not-a-real-secret",
        model="gpt-test-model",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(ContentProviderInvalidResponse, match="ادعای تأییدنشده"):
        provider.generate(content_request())


def test_openai_provider_allows_normal_marketing_word_suitable():
    content = _valid_generated_content()
    content["body"] = "این طراحی برای فضای سخنرانی مناسب است."

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_response_payload(content), request=request)

    provider = OpenAIContentProvider(
        api_key="sk-test-not-a-real-secret",
        model="gpt-test-model",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    generated = provider.generate(content_request())

    assert "مناسب" in generated.body


def test_openai_provider_treats_manager_brief_as_approved_information():
    content = _valid_generated_content()
    content["body"] = "این محصول با ضمانت یک‌ساله معرفی می‌شود."

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_response_payload(content), request=request)

    provider = OpenAIContentProvider(
        api_key="sk-test-not-a-real-secret",
        model="gpt-test-model",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    approved_request = content_request().model_copy(
        update={"user_brief": "محصول ضمانت یک‌ساله دارد."}
    )

    generated = provider.generate(approved_request)

    assert "ضمانت" in generated.body


def test_openai_provider_retries_once_when_first_response_has_unverified_claim():
    unsafe = _valid_generated_content()
    unsafe["body"] = "این محصول با ضمانت کیفیت معرفی می‌شود."
    safe = _valid_generated_content()
    requests: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        content = unsafe if len(requests) == 1 else safe
        return httpx.Response(200, json=_response_payload(content), request=request)

    provider = OpenAIContentProvider(
        api_key="sk-test-not-a-real-secret",
        model="gpt-test-model",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    generated = provider.generate(content_request())

    assert generated.body == safe["body"]
    assert len(requests) == 2
    correction_input = json.loads(requests[1]["input"])
    assert correction_input["rejected_claim_markers"] == ["ضمانت"]


def test_openai_provider_retries_when_output_copies_manager_brief_verbatim():
    brief = "روی فرم منحنی و نمای سفید شیاردار محصول تمرکز شود."
    copied = _valid_generated_content()
    copied["body"] = brief
    rewritten = _valid_generated_content()
    rewritten["body"] = "فرم منحنی محصول در کنار نمای سفید شیاردار آن معرفی می‌شود."
    requests: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        content = copied if len(requests) == 1 else rewritten
        return httpx.Response(200, json=_response_payload(content), request=request)

    provider = OpenAIContentProvider(
        api_key="sk-test-not-a-real-secret",
        model="gpt-test-model",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    request = content_request().model_copy(update={"user_brief": brief})

    generated = provider.generate(request)

    assert generated.body == rewritten["body"]
    assert len(requests) == 2
    correction_input = json.loads(requests[1]["input"])
    assert correction_input["rewrite_manager_brief"] is True
