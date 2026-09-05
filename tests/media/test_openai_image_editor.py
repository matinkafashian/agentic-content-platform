import base64
from io import BytesIO

import httpx
import pytest
from PIL import Image

from app.media.openai_image_editor import (
    ImageEditorInvalidResponse,
    OpenAIImageEditor,
    build_product_edit_prompt,
)


def png_bytes(color: str = "navy") -> bytes:
    output = BytesIO()
    Image.new("RGB", (48, 32), color).save(output, format="PNG")
    return output.getvalue()


def test_studio_prompt_preserves_product_identity_but_allows_ad_reframing():
    prompt = build_product_edit_prompt(
        mode="studio",
        background_style="adaptive_studio",
        overlay_text="معرفی محصول",
    )

    assert "Do not recolor the product" in prompt
    assert "Treat this uploaded image independently" in prompt
    assert "exact colors, color combinations" in prompt
    assert "choose a background tone that creates clear contrast" in prompt
    assert "premium commercial product campaign" in prompt
    assert "reframe and reposition" in prompt
    assert "large empty area reserved for the single headline" in prompt
    assert "No logo, no watermark" in prompt
    assert "white and brown" not in prompt.casefold()


def test_studio_prompt_renders_only_the_exact_short_persian_copy():
    prompt = build_product_edit_prompt(
        mode="studio",
        background_style="adaptive_studio",
        overlay_text="زیبایی در جزئیات است",
    )

    assert "زیبایی در جزئیات است" in prompt
    assert "EXACT, verbatim" in prompt
    assert "exactly once" in prompt
    assert "Do not add any other text" in prompt
    assert "luxury Persian advertising typography" in prompt
    assert "not a default plain font" in prompt
    assert "headline must occupy no more than 15%" in prompt
    assert "visibly bold" in prompt
    assert "medium-to-heavy display weight" in prompt
    assert "Do not recolor the product" in prompt


def test_cinematic_prompt_uses_topic_and_message_without_inventing_claims():
    prompt = build_product_edit_prompt(
        mode="cinematic",
        topic="خم واقعی",
        message="از دل چوب متولد می‌شود",
    )

    assert "خم واقعی" in prompt
    assert "از دل چوب متولد می‌شود" in prompt
    assert "premium vertical cinematic advertising poster" in prompt
    assert "visually isolate the product from the uploaded scene" in prompt
    assert "recompose it as the hero subject" in prompt
    assert "lower-middle 45–60%" in prompt
    assert "compact editorial information blocks" in prompt
    assert "two or three short supporting Persian callouts" in prompt
    assert "natural, fluent, grammatically complete Persian" in prompt
    assert "Do not invent prices" in prompt
    assert "Do not recolor the product" in prompt


def test_cinematic_editor_requests_vertical_poster_canvas():
    output = png_bytes("gold")

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read()
        assert b'name="size"' in body
        assert b"1024x1536" in body
        assert b"recompose it as the hero subject" in body
        return httpx.Response(
            200,
            request=request,
            json={"data": [{"b64_json": base64.b64encode(output).decode("ascii")}]},
        )

    editor = OpenAIImageEditor(
        api_key="test-key",
        model="gpt-image-2",
        quality="high",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    edited = editor.edit(
        source=png_bytes(),
        filename="source.png",
        mime_type="image/png",
        mode="cinematic",
        topic="خم واقعی",
        message="از دل چوب متولد می‌شود",
    )

    assert edited.data != output  # Branding is applied to the generated pixels.
    assert Image.open(BytesIO(edited.data)).size == Image.open(BytesIO(output)).size


def test_openai_editor_posts_multipart_and_validates_returned_image():
    output = png_bytes("teal")

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read()
        assert request.url.path == "/v1/images/edits"
        assert request.headers["authorization"] == "Bearer test-key"
        assert b'gpt-image-2' in body
        assert b'name="image[]"' in body
        assert b'name="quality"' in body and b'high' in body
        assert b'Do not recolor the product' in body
        return httpx.Response(
            200,
            request=request,
            json={
                "data": [{"b64_json": base64.b64encode(output).decode("ascii")}],
            },
            headers={"x-request-id": "req_image_test"},
        )

    editor = OpenAIImageEditor(
        api_key="test-key",
        model="gpt-image-2",
        quality="high",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    edited = editor.edit(
        source=png_bytes(),
        filename="source.png",
        mime_type="image/png",
        mode="studio",
        background_style="adaptive_studio",
        overlay_text="زیبایی در جزئیات است",
    )

    assert edited.data != output  # Studio outputs receive the same branding.
    assert Image.open(BytesIO(edited.data)).size == Image.open(BytesIO(output)).size
    assert edited.width == 48
    assert edited.height == 32
    assert edited.suffix == ".png"


def test_openai_editor_rejects_missing_or_invalid_image_payload():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request, json={"data": []})

    editor = OpenAIImageEditor(
        api_key="test-key",
        model="gpt-image-2",
        quality="high",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(ImageEditorInvalidResponse, match="تصویر معتبری"):
        editor.edit(
            source=png_bytes(),
            filename="source.png",
            mime_type="image/png",
            mode="studio",
            background_style="adaptive_studio",
            overlay_text="زیبایی در جزئیات است",
        )
