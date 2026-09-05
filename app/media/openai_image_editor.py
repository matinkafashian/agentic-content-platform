import base64
import binascii
import json
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


def _required_copy(value: str, *, label: str, max_length: int) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} الزامی است")
    if len(normalized) > max_length:
        raise ValueError(f"{label} نباید بیشتر از {max_length} نویسه باشد")
    return normalized


def build_product_edit_prompt(
    *,
    mode: str,
    background_style: str = "adaptive_studio",
    overlay_text: str = "",
    topic: str = "",
    message: str = "",
) -> str:
    if mode == "studio":
        try:
            background_instruction = BACKGROUND_STYLES[background_style]
        except KeyError as exc:
            raise ValueError("سبک پس‌زمینه انتخاب‌شده معتبر نیست") from exc
        exact_copy = _required_copy(
            overlay_text, label="متن کوتاه روی تصویر", max_length=80
        )
        return f"""
Create a premium commercial product campaign image from the uploaded product photo. This is
an art-directed advertising edit, not a simple background removal.

PRODUCT IDENTITY AND COLOR:
- Use the uploaded product as the only product reference.
- Preserve its recognizable identity, silhouette, proportions, construction, panel layout,
  curves, grooves, edges, materials, hardware, wood grain, finish, and surface details.
- Preserve the product's exact colors, color combinations, finish, and texture.
  Do not recolor the product.
- Treat this uploaded image independently; never copy colors or materials from other products.
- Improve exposure, white balance, material clarity, and realistic sharpness without making the
  product look plastic, oversaturated, over-smoothed, or like a generic CGI replacement.

ART DIRECTION AND BACKGROUND:
- Remove the original workshop, wall, floor, stains, clutter, and distracting reflections.
- {background_instruction}
- Build a polished advertising set with a seamless gradient backdrop, shaped softbox light,
  subtle architectural light falloff, a refined floor, realistic contact shadow, and restrained
  premium depth. The result must feel deliberately photographed for a luxury catalog campaign.

COMPOSITION:
- You may reframe and reposition the exact product for a stronger advertisement.
- Keep the whole product clearly visible, upright, centered or slightly off-center, with realistic
  perspective and no distorted verticals.
- Make the product the visual hero, occupying roughly 60–75% of the frame.
- Create a large empty area reserved for the single headline. Choose the best top-left, top-center,
  or upper negative-space position based on the product silhouette; never place text across the
  product's important details.

SINGLE PERSIAN HEADLINE:
Render this user-provided copy EXACT, verbatim, exactly once:
{json.dumps(exact_copy, ensure_ascii=False)}

Use luxury Persian advertising typography with correct right-to-left shaping: elegant editorial
display lettering in a visibly bold, medium-to-heavy display weight, refined weight contrast,
careful kerning, balanced line breaks, generous safe margins, and excellent contrast. Make the
headline immediately noticeable and confidently weighted, while keeping its size restrained and
standard for a premium advertisement. It must feel custom art-directed, not a default plain font,
not WordArt, and not oversized. The headline must occupy no more than 15% of the image height.
Do not add any other text.

OUTPUT:
Photorealistic professional product photography, premium campaign polish, accurate materials,
realistic light and shadows, clean hierarchy, social-media-ready. No logo, no watermark, no
unrelated labels, no badges, no unrelated objects, and no decorative frame.
""".strip()
    elif mode == "cinematic":
        exact_topic = _required_copy(topic, label="موضوع اصلی", max_length=80)
        source_message = _required_copy(message, label="پیام اصلی", max_length=400)
        return f"""
Create a premium vertical cinematic advertising poster from the uploaded product photo. Redesign
the entire composition boldly so it resembles a high-end Persian furniture or architectural
product campaign, not a studio catalog photo and not a lightly edited version of the input.

HERO PRODUCT RECOMPOSITION:
- First, visually isolate the product from the uploaded scene inside this single image-edit request.
- Remove the original workshop completely, then recompose it as the hero subject in a new scene.
- You may cut out, reposition, enlarge, zoom, and slightly change the camera framing to create a
  dramatic poster, while keeping the product unmistakably the same design.
- Preserve the core silhouette, construction, panel layout, curves, grooves, materials, visible
  wood grain, finish, and exact color combination. Do not recolor the product or redesign it into
  another model. Keep believable scale, perspective, contact shadows, and material realism.

CINEMATIC ART DIRECTION:
- Use a deep black and charcoal environment with restrained dark-brown undertones, refined gold
  highlights, dramatic rim light, volumetric light beams, subtle atmospheric haze, high contrast,
  realistic textures, and a premium editorial finish.
- Place the product on a believable dark architectural plinth or crafted-material stage. Integrate
  light, shadow, depth, and reflections so it feels photographed in the scene, never pasted on.
- The mood must be bold, luxurious, crafted, cinematic, and directly related to the supplied topic
  and message. Avoid generic fantasy, random objects, excessive ornaments, and cheap glowing
  effects.

POSTER LAYOUT:
- Use a vertical 2:3 advertising canvas with strong hierarchy and generous safe margins.
- Position the product in the lower-middle 45–60% of the poster, large and visually dominant.
- Reserve the upper area for one strong Persian title.
- Arrange two or three compact editorial information blocks beside the product or in the lower
  side areas, similar to a professionally art-directed magazine advertisement.
- Use thin gold divider lines and at most small minimal geometric icons where useful. Do not create
  one large centered wall of text. Keep important copy away from the product's detailed surfaces.

PERSIAN POSTER COPY:
Render this main title EXACT, verbatim, exactly once:
{json.dumps(exact_topic, ensure_ascii=False)}

Use this message as the only source for two or three short supporting Persian callouts:
{json.dumps(source_message, ensure_ascii=False)}

The supporting callouts must be concise, relevant, natural, fluent, grammatically complete Persian
phrases derived only from that message. Silently proofread them before rendering.
Do not invent prices, discounts, guarantees, technical specifications, performance claims,
contact details, or facts absent from the message.

TYPOGRAPHY:
- Use correct right-to-left Persian shaping and a sophisticated luxury editorial hierarchy.
- Main title: large, elegant Persian display lettering in warm metallic gold, visually dominant
  but with comfortable breathing room.
- Supporting copy: smaller clean Persian type in warm white or muted gold, highly legible, aligned
  in compact blocks with consistent spacing.
- No default plain-font appearance, no WordArt, no misspelled text, no random letters, and no text
  beyond the required title and supporting callouts.

OUTPUT:
Photorealistic cinematic advertising poster, high-end campaign quality, realistic materials,
dramatic but tasteful lighting, strong depth, and deliberate graphic design. No logo, no watermark,
no unrelated badges, and no unrelated objects.
""".strip()
    else:
        raise ValueError("حالت ویرایش تصویر معتبر نیست")


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
        mode: str,
        background_style: str = "adaptive_studio",
        overlay_text: str = "",
        topic: str = "",
        message: str = "",
    ) -> ValidatedImage:
        prompt = build_product_edit_prompt(
            mode=mode,
            background_style=background_style,
            overlay_text=overlay_text,
            topic=topic,
            message=message,
        )
        prompt += (
            "\nLeave the top-right 22% corner clear for a logo and the bottom-left "
            "edge clear for a phone label added later. Do not draw a logo or phone number."
        )
        canvas_size = "1024x1536" if mode == "cinematic" else "auto"
        started_at = perf_counter()
        try:
            response = self._client.post(
                IMAGE_EDITS_URL,
                headers={"Authorization": self._authorization_header},
                data={
                    "model": self.model,
                    "prompt": prompt,
                    "quality": self.quality,
                    "size": canvas_size,
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
        from app.media.image_branding import brand_image

        return brand_image(edited)

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
