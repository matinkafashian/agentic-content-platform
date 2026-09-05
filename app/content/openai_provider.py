import json
import logging
import re
from time import perf_counter
from typing import Any

import httpx
from pydantic import ValidationError

from app.content.schemas import ContentGenerationRequest, GeneratedContent

logger = logging.getLogger(__name__)

RESPONSES_URL = "https://api.openai.com/v1/responses"
CLAIM_MARKERS = (
    "تخفیف",
    "گارانتی",
    "ضمانت",
    "رایگان",
    "تضمینی",
    "مادام‌العمر",
    "بهترین",
    "ارزان‌ترین",
    "پرفروش",
    "پرطرفدار",
)
EMOJI_PREFIX = re.compile(r"^[\s]*[\u2600-\u27bf\U0001f300-\U0001faff]")

SYSTEM_INSTRUCTIONS = """
شما نویسنده حرفه‌ای محتوای تجاری فارسی برای شبکه‌های اجتماعی هستید.
فقط از داده‌های قطعی محصول و برند که در ورودی آمده استفاده کنید.
خلاصه مدیر نیز اطلاعات تأییدشده‌ای است که خود مدیر وارد کرده و منبع معتبر محتواست.
خلاصه مدیر را عیناً در خروجی تکرار نکنید؛ مفهوم آن را با اتکا به داده‌های قطعی محصول
به یک متن تازه، کامل و روان گسترش دهید.
نمونه‌های تأییدشده قبلی فقط مرجع لحن و ساختار هستند؛ متن، نام محصول، مشخصات،
ادعاها یا هشتگ‌های آن‌ها را کپی نکنید و هیچ واقعیت محصولی از آن‌ها استخراج نکنید.
قیمت یا عددی به‌عنوان قیمت در خروجی ننویسید؛ مخاطب باید برای استعلام قیمت به ادمین پیام دهد.
هیچ تخفیف، گارانتی، ضمانت، ویژگی فنی، زمان ارسال یا ادعای برتری را خارج از اطلاعات
محصول، برند یا خلاصه مدیر حدس نزنید.
مخاطب برند فقط برای انتخاب لحن است و نباید منبع ویژگی فنی یا تجاری تازه‌ای باشد.
هر مورد benefits باید بازنویسی مستقیم یک واقعیت صریح در ورودی باشد، نه برداشت تبلیغاتی شما.
در headline و body نیز کیفیت، کاربرد، مخاطب هدف یا نتیجه استفاده را از خودتان استنباط نکنید.
اگر اطلاعات کافی نیست، متن را جذاب اما محتاط و بدون ادعای تازه بنویسید.
فیلد body شامل ۲ تا ۳ جمله کوتاه و روان باشد؛ هر جمله در خطی جدا با یک خط خالی
بین جمله‌ها و یک ایموجی مرتبط و ساده در ابتدای آن بیاید. از پاراگراف بلند و پیوسته پرهیز کنید.
داخل body تکرار benefits، CTA، شناسه پشتیبانی، دعوت به پیام‌دادن یا هشتگ ننویسید.
فیلد benefits فقط ۲ تا ۴ واقعیت کوتاه و غیرتکراری داشته باشد و هر واقعیت فقط یک بار بیاید.
CTA، شناسه پشتیبانی و پیام استعلام قیمت فقط در بخش قطعی سامانه افزوده می‌شوند؛
آن‌ها را در headline، body یا benefits تکرار نکنید.
فارسی روان، محترمانه و بیزینسی بنویسید و از ایموجی محدود و مرتبط استفاده کنید.
هشتگ‌ها بدون علامت # باشند. متن کامل کپشن را نسازید؛ دقیقاً فیلدهای ساختاریافته را پر کنید.
""".strip()


class ContentProviderError(RuntimeError):
    """A safe, user-facing content provider failure."""


class ContentProviderUnavailable(ContentProviderError):
    pass


class ContentProviderInvalidResponse(ContentProviderError):
    pass


class OpenAIContentProvider:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float = 45.0,
        client: httpx.Client | None = None,
    ) -> None:
        normalized_key = api_key.strip()
        normalized_model = model.strip()
        if not normalized_key:
            raise ValueError("OpenAI API key is required")
        if not normalized_model:
            raise ValueError("OpenAI text model is required")
        self.model = normalized_model
        self.name = f"openai:{normalized_model}"
        self._authorization_header = f"Bearer {normalized_key}"
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(timeout_seconds),
            headers={
                "Content-Type": "application/json",
            },
        )

    def generate(self, request: ContentGenerationRequest) -> GeneratedContent:
        rejected_claim_markers: list[str] = []
        rewrite_manager_brief = False
        for attempt in range(2):
            started_at = perf_counter()
            try:
                response = self._client.post(
                    RESPONSES_URL,
                    json=self._payload(
                        request,
                        rejected_claim_markers=rejected_claim_markers,
                        rewrite_manager_brief=rewrite_manager_brief,
                    ),
                    headers={"Authorization": self._authorization_header},
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                elapsed_ms = round((perf_counter() - started_at) * 1000)
                logger.warning(
                    "OpenAI content request failed model=%s status=%s elapsed_ms=%s",
                    self.model,
                    exc.response.status_code,
                    elapsed_ms,
                )
                raise ContentProviderUnavailable(
                    self._safe_http_error(exc.response.status_code)
                ) from exc
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                elapsed_ms = round((perf_counter() - started_at) * 1000)
                logger.warning(
                    "OpenAI content request unavailable model=%s elapsed_ms=%s error_type=%s",
                    self.model,
                    elapsed_ms,
                    type(exc).__name__,
                )
                raise ContentProviderUnavailable(
                    "ارتباط با OpenAI برقرار نشد؛ چند لحظه بعد دوباره تلاش کنید."
                ) from exc

            elapsed_ms = round((perf_counter() - started_at) * 1000)
            payload = self._response_json(response)
            if payload.get("status") != "completed":
                logger.warning(
                    "OpenAI content response incomplete model=%s response_id=%s "
                    "status=%s elapsed_ms=%s",
                    self.model,
                    payload.get("id", "unknown"),
                    payload.get("status", "unknown"),
                    elapsed_ms,
                )
                raise ContentProviderInvalidResponse(
                    "تولید محتوا در OpenAI کامل نشد؛ لطفاً دوباره تلاش کنید."
                )

            try:
                generated = GeneratedContent.model_validate_json(
                    self._output_text(payload)
                )
            except (ValidationError, ValueError, TypeError, json.JSONDecodeError) as exc:
                logger.warning(
                    "OpenAI returned invalid structured content model=%s "
                    "response_id=%s elapsed_ms=%s",
                    self.model,
                    payload.get("id", "unknown"),
                    elapsed_ms,
                )
                raise ContentProviderInvalidResponse(
                    "OpenAI خروجی معتبر و قابل‌استفاده تولید نکرد؛ لطفاً دوباره تلاش کنید."
                ) from exc

            generated = self._with_visual_markers(generated)
            unexpected = self._unverified_claim_markers(generated, request)
            copied_manager_brief = self._copies_manager_brief(generated, request)
            if (unexpected or copied_manager_brief) and attempt == 0:
                logger.info(
                    "Retrying OpenAI content model=%s markers=%s copied_brief=%s",
                    self.model,
                    ",".join(unexpected),
                    copied_manager_brief,
                )
                rejected_claim_markers = unexpected
                rewrite_manager_brief = copied_manager_brief
                continue
            self._reject_unverified_claims(generated, request)
            if copied_manager_brief:
                raise ContentProviderInvalidResponse(
                    "خروجی توضیح کوتاه شما را عیناً تکرار کرد؛ دوباره تلاش کنید."
                )
            usage = (
                payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
            )
            logger.info(
                "OpenAI content generated model=%s response_id=%s elapsed_ms=%s "
                "input_tokens=%s output_tokens=%s total_tokens=%s",
                self.model,
                payload.get("id", "unknown"),
                elapsed_ms,
                usage.get("input_tokens", "unknown"),
                usage.get("output_tokens", "unknown"),
                usage.get("total_tokens", "unknown"),
            )
            return generated.model_copy(
                update={
                    "cta": request.brand.default_cta,
                    "content_angle": request.requested_angle,
                }
            )

        raise AssertionError("OpenAI content retry loop exited unexpectedly")

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _payload(
        self,
        request: ContentGenerationRequest,
        *,
        rejected_claim_markers: list[str] | None = None,
        rewrite_manager_brief: bool = False,
    ) -> dict[str, Any]:
        input_payload = {
            "product_facts": request.product.model_dump(mode="json"),
            "brand_facts": request.brand.model_dump(mode="json"),
            "manager_brief": request.user_brief,
            "requested_angle": request.requested_angle,
            "approved_style_examples": request.style_examples,
        }
        if rejected_claim_markers:
            input_payload["rejected_claim_markers"] = rejected_claim_markers
            input_payload["correction_instruction"] = (
                "خروجی قبلی به‌دلیل ادعاهای تأییدنشده رد شد. متن را بدون این "
                "عبارت‌ها و بدون جایگزین‌کردن آن‌ها با ادعای تازه بازنویسی کن."
            )
        if rewrite_manager_brief:
            input_payload["rewrite_manager_brief"] = True
            input_payload["brief_correction_instruction"] = (
                "خروجی قبلی خلاصه مدیر را عیناً تکرار کرد. مفهوم آن را بدون افزودن "
                "ادعای تازه، با جمله‌بندی و ساختاری کاملاً جدید گسترش بده."
            )
        return {
            "model": self.model,
            "instructions": SYSTEM_INSTRUCTIONS,
            "input": json.dumps(input_payload, ensure_ascii=False),
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "persian_product_content",
                    "strict": True,
                    "schema": self._response_schema(request.requested_angle),
                }
            },
            "max_output_tokens": 1400,
            "store": False,
        }

    @staticmethod
    def _copies_manager_brief(
        generated: GeneratedContent, request: ContentGenerationRequest
    ) -> bool:
        brief = re.sub(r"\s+", " ", request.user_brief).strip().casefold()
        if len(brief) < 20:
            return False
        generated_text = "\n".join(
            [generated.headline, generated.body, *generated.benefits]
        )
        normalized_output = re.sub(r"\s+", " ", generated_text).strip().casefold()
        return brief in normalized_output

    @staticmethod
    def _response_schema(requested_angle: str) -> dict[str, Any]:
        properties: dict[str, Any] = {
            "headline": {"type": "string", "minLength": 2, "maxLength": 300},
            "body": {"type": "string", "minLength": 2, "maxLength": 3000},
            "benefits": {
                "type": "array",
                "minItems": 1,
                "maxItems": 5,
                "items": {"type": "string", "minLength": 2, "maxLength": 500},
            },
            "cta": {"type": "string", "minLength": 2, "maxLength": 500},
            "hashtags": {
                "type": "array",
                "maxItems": 6,
                "items": {"type": "string", "minLength": 1, "maxLength": 80},
            },
            "used_emojis": {
                "type": "array",
                "maxItems": 6,
                "items": {"type": "string", "minLength": 1, "maxLength": 12},
            },
            "content_angle": {"type": "string", "enum": [requested_angle]},
        }
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": properties,
            "required": list(properties),
        }

    @staticmethod
    def _response_json(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise ContentProviderInvalidResponse(
                "پاسخ OpenAI قابل‌خواندن نبود؛ لطفاً دوباره تلاش کنید."
            ) from exc
        if not isinstance(payload, dict):
            raise ContentProviderInvalidResponse(
                "پاسخ OpenAI ساختار معتبری نداشت؛ لطفاً دوباره تلاش کنید."
            )
        return payload

    @staticmethod
    def _output_text(payload: dict[str, Any]) -> str:
        direct = payload.get("output_text")
        if isinstance(direct, str) and direct.strip():
            return direct
        parts: list[str] = []
        output = payload.get("output")
        if not isinstance(output, list):
            raise ValueError("missing output")
        for item in output:
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if (
                    isinstance(part, dict)
                    and part.get("type") == "output_text"
                    and isinstance(part.get("text"), str)
                ):
                    parts.append(part["text"])
        if not parts:
            raise ValueError("missing output text")
        return "".join(parts)

    @staticmethod
    def _safe_http_error(status_code: int) -> str:
        if status_code in {401, 403}:
            return "دسترسی OpenAI معتبر نیست؛ تنظیمات API باید توسط مدیر بررسی شود."
        if status_code == 429:
            return "سقف مصرف یا تعداد درخواست‌های OpenAI پر شده است؛ کمی بعد تلاش کنید."
        return "سرویس OpenAI موقتاً پاسخ مناسبی نداد؛ چند لحظه بعد دوباره تلاش کنید."

    @classmethod
    def _with_visual_markers(cls, generated: GeneratedContent) -> GeneratedContent:
        added_emojis: list[str] = []
        headline = generated.headline
        if not EMOJI_PREFIX.match(headline):
            headline = f"✨ {headline}"
            added_emojis.append("✨")

        benefits: list[str] = []
        for benefit in generated.benefits:
            if EMOJI_PREFIX.match(benefit):
                benefits.append(benefit)
                continue
            icon = cls._benefit_icon(benefit)
            benefits.append(f"{icon} {benefit}")
            added_emojis.append(icon)

        used_emojis = list(dict.fromkeys([*generated.used_emojis, *added_emojis]))[:6]
        return generated.model_copy(
            update={
                "headline": headline,
                "benefits": benefits,
                "used_emojis": used_emojis,
            }
        )

    @staticmethod
    def _benefit_icon(text: str) -> str:
        normalized = text.casefold()
        if any(word in normalized for word in ("ارسال", "تحویل")):
            return "🚚"
        if any(word in normalized for word in ("جنس", "متریال", "mdf", "روکش")):
            return "🪵"
        if any(
            word in normalized
            for word in ("رنگ", "طراحی", "سبک", "ظاهر", "خطوط")
        ):
            return "🎨"
        if "سفارشی" in normalized:
            return "🧩"
        return "✅"

    @staticmethod
    def _reject_unverified_claims(
        generated: GeneratedContent, request: ContentGenerationRequest
    ) -> None:
        unexpected = OpenAIContentProvider._unverified_claim_markers(
            generated, request
        )
        if unexpected:
            logger.warning(
                "OpenAI content rejected for unverified claim markers model=%s markers=%s",
                "configured",
                ",".join(unexpected),
            )
            raise ContentProviderInvalidResponse(
                "خروجی شامل ادعای تأییدنشده بود و برای حفظ دقت ذخیره نشد؛ دوباره تلاش کنید."
            )

    @staticmethod
    def _unverified_claim_markers(
        generated: GeneratedContent, request: ContentGenerationRequest
    ) -> list[str]:
        generated_text = "\n".join(
            [generated.headline, generated.body, *generated.benefits]
        )
        verified_text = "\n".join(
            [
                request.product.description,
                request.product.shipping_info,
                request.user_brief,
                *request.product.attributes.keys(),
                *request.product.attributes.values(),
                request.brand.audience,
                *request.brand.approved_claims,
            ]
        )
        return [
            marker
            for marker in CLAIM_MARKERS
            if marker in generated_text and marker not in verified_text
        ]
