import base64
import binascii
import logging
from time import perf_counter

import httpx

from app.media.images import InvalidImage, ValidatedImage, validate_image

logger = logging.getLogger(__name__)

IMAGE_EDITS_URL = "https://api.openai.com/v1/images/edits"

BACKGROUND_STYLES = {
    "adaptive_studio": (
        "Use a clean premium seamless studio background. Inspect only this product's "
        "visible colors and choose a background tone that creates clear contrast without "
        "casting color onto the product. Prefer a refined neutral charcoal, warm gray, or "
        "soft off-white tone as appropriate for this individual image."
    ),
    "dark_studio": (
        "Use a premium charcoal-to-black seamless studio background with a subtle matte "
        "floor and gentle vignette. Maintain clear separation between the product edges "
        "and the background."
    ),
    "light_studio": (
        "Use a premium warm off-white to light-gray seamless studio background with a "
        "subtle matte floor. Maintain clear separation between the product edges and the "
        "background."
    ),
}


def build_product_edit_prompt(background_style: str) -> str:
    try:
        background_instruction = BACKGROUND_STYLES[background_style]
    except KeyError as exc:
        raise ValueError("سبک پس‌زمینه انتخاب‌شده معتبر نیست") from exc

    return f"""
Edit the provided product photo into a premium, photorealistic studio product image.

SUBJECT PRESERVATION — HIGHEST PRIORITY:
Preserve the exact identity, geometry, proportions, silhouette, dimensions, construction,
panel layout, curves, grooves, edges, materials, hardware, surface details, and all visible
features of the original product. The output must depict the exact same physical product,
not a similar or newly designed product. Do not redesign, reshape, replace, simplify,
duplicate, add, remove, crop, or obscure any part of the product.

COLOR AND MATERIAL ACCURACY — CRITICAL:
Preserve the product's exact colors, color combinations, finish, texture, material
appearance, wood grain, and surface details as shown in the input image. Do not recolor the product.
Do not transfer colors or materials from previous images or products. Do not assume
that different products share the same color palette. Treat this uploaded image independently
and use only its visible product colors as the reference. Lighting and color correction may
improve clarity and attractiveness, but must not change the product's actual color identity.
Maintain a neutral and accurate white balance.

BACKGROUND:
Remove the original workshop, wall, floor, and background distractions completely.
{background_instruction}
Use a subtle neutral floor and a physically realistic contact shadow. Keep the scene elegant,
minimal, and uncluttered. Leave useful clean negative space in the upper area for a future
Persian headline and logo, but do not render them now. Do not add props unless explicitly
requested.

IMAGE ENHANCEMENT:
Improve exposure, white balance, natural sharpness, local contrast, material clarity, and
color richness. Use soft professional studio lighting, realistic reflections, realistic
shadows, and true-to-life materials. Remove dust, stains, wall defects, distracting
reflections, and unwanted color casts. Do not over-smooth, over-sharpen, over-saturate, or
create an artificial CGI or plastic appearance.

COMPOSITION:
Keep the entire product fully visible with safe margins on every side. Center and level the
product. Preserve a natural camera perspective and do not distort vertical lines. Produce a
high-quality commercial product photograph suitable for social media.

No text, no logo, no watermark, no labels, no badges, no people, and no additional objects.
""".strip()


class ImageEditorError(RuntimeError):
    """A safe, user-facing image editing failure."""


class ImageEditorUnavailable(ImageEditorError):
    pass


class ImageEditorInvalidResponse(ImageEditorError):
    pass


class OpenAIImageEditor:
    def __init__(
        self,
        *,
        api_key: str,
        model: str = "gpt-image-2",
        quality: str = "high",
        timeout_seconds: float = 180.0,
        client: httpx.Client | None = None,
    ) -> None:
        normalized_key = api_key.strip()
        normalized_model = model.strip()
        if not normalized_key:
            raise ValueError("OpenAI API key is required")
        if not normalized_model:
            raise ValueError("OpenAI image model is required")
        if quality not in {"low", "medium", "high"}:
            raise ValueError("OpenAI image quality must be low, medium, or high")
        self.model = normalized_model
        self.quality = quality
        self.name = f"openai:{normalized_model}"
        self._authorization_header = f"Bearer {normalized_key}"
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=httpx.Timeout(timeout_seconds))

    def edit(
        self,
        *,
        source: bytes,
        filename: str,
        mime_type: str,
        background_style: str,
    ) -> ValidatedImage:
        prompt = build_product_edit_prompt(background_style)
        started_at = perf_counter()
        try:
            response = self._client.post(
                IMAGE_EDITS_URL,
                headers={"Authorization": self._authorization_header},
                data={
                    "model": self.model,
                    "prompt": prompt,
                    "quality": self.quality,
                    "size": "auto",
                },
                files=[("image[]", (filename, bytes(source), mime_type))],
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "OpenAI image edit failed model=%s status=%s elapsed_ms=%s request_id=%s",
                self.model,
                exc.response.status_code,
                round((perf_counter() - started_at) * 1000),
                exc.response.headers.get("x-request-id", "unknown"),
            )
            raise ImageEditorUnavailable(
                self._safe_http_error(exc.response.status_code)
            ) from exc
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            logger.warning(
                "OpenAI image edit unavailable model=%s elapsed_ms=%s error_type=%s",
                self.model,
                round((perf_counter() - started_at) * 1000),
                type(exc).__name__,
            )
            raise ImageEditorUnavailable(
                "ارتباط با سرویس ویرایش تصویر برقرار نشد؛ کمی بعد دوباره تلاش کنید."
            ) from exc

        image_bytes = self._decode_image(response)
        try:
            edited = validate_image(image_bytes, "edited.png", "image/png")
        except InvalidImage as exc:
            raise ImageEditorInvalidResponse(
                "OpenAI تصویر معتبری برنگرداند؛ لطفاً دوباره تلاش کنید."
            ) from exc
        logger.info(
            "OpenAI image edited model=%s quality=%s request_id=%s elapsed_ms=%s "
            "output_bytes=%s output_width=%s output_height=%s",
            self.model,
            self.quality,
            response.headers.get("x-request-id", "unknown"),
            round((perf_counter() - started_at) * 1000),
            len(edited.data),
            edited.width,
            edited.height,
        )
        return edited

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    @staticmethod
    def _decode_image(response: httpx.Response) -> bytes:
        try:
            payload = response.json()
            encoded = payload["data"][0]["b64_json"]
            if not isinstance(encoded, str) or not encoded:
                raise ValueError("missing image data")
            return base64.b64decode(encoded, validate=True)
        except (ValueError, KeyError, IndexError, TypeError, binascii.Error) as exc:
            raise ImageEditorInvalidResponse(
                "OpenAI تصویر معتبری برنگرداند؛ لطفاً دوباره تلاش کنید."
            ) from exc

    @staticmethod
    def _safe_http_error(status_code: int) -> str:
        if status_code in {401, 403}:
            return "دسترسی OpenAI معتبر نیست؛ تنظیمات API باید توسط مدیر بررسی شود."
        if status_code == 429:
            return "سقف مصرف یا تعداد درخواست‌های تصویر OpenAI پر شده است."
        return "سرویس ویرایش تصویر موقتاً پاسخ مناسبی نداد؛ دوباره تلاش کنید."
