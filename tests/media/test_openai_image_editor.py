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


def test_prompt_preserves_each_products_actual_colors_and_excludes_text():
    prompt = build_product_edit_prompt("adaptive_studio")

    assert "Do not recolor the product" in prompt
    assert "Treat this uploaded image independently" in prompt
    assert "exact colors, color combinations" in prompt
    assert "choose a background tone that creates clear contrast" in prompt
    assert "No text, no logo, no watermark" in prompt
    assert "white and brown" not in prompt.casefold()


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
        background_style="adaptive_studio",
    )

    assert edited.data == output
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
            background_style="adaptive_studio",
        )
