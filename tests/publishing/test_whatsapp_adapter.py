import json

import httpx
import pytest

from app.publishing.models import PostBundle
from app.publishing.whatsapp import WhatsAppAdapter


def _bundle(tmp_path, *, voice=None, voice_mime=None):
    bundle_key = "bundle-whatsapp-test"
    directory = tmp_path / "private" / "bundles" / bundle_key
    directory.mkdir(parents=True, exist_ok=True)
    image = directory / "image.png"
    image.write_bytes(b"valid-image-fixture")
    voice_path = None
    if voice is not None:
        voice_path = directory / voice[0]
        voice_path.write_bytes(voice[1])
    return PostBundle(
        bundle_key=bundle_key,
        content_draft_id=1,
        caption_snapshot="معرفی محصول تستی",
        image_relative_path=image.relative_to(tmp_path).as_posix(),
        image_mime_type="image/png",
        image_size_bytes=image.stat().st_size,
        image_sha256="0" * 64,
        voice_relative_path=(
            voice_path.relative_to(tmp_path).as_posix() if voice_path else None
        ),
        voice_mime_type=voice_mime,
        voice_size_bytes=voice_path.stat().st_size if voice_path else None,
        voice_sha256="1" * 64 if voice_path else None,
        voice_duration_ms=1200 if voice_path else None,
    )


def test_whatsapp_sends_bundle_to_local_bridge(tmp_path):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        payload = json.loads(request.content)
        assert payload["destination"] == "120363123456789@g.us"
        assert payload["caption"] == "معرفی محصول تستی"
        assert payload["image_path"].endswith("image.png")
        assert payload["voice_path"] is None
        assert payload["idempotency_key"] == "whatsapp-1"
        assert request.headers["authorization"] == "Bearer bridge-test-secret"
        return httpx.Response(
            200,
            request=request,
            json={"ok": True, "message_ids": ["wa-message-1"]},
        )

    adapter = WhatsAppAdapter(
        bridge_url="http://127.0.0.1:8780",
        bridge_token="bridge-test-secret",
        upload_root=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = adapter.send(
        _bundle(tmp_path), "120363123456789@g.us", "whatsapp-1"
    )

    assert result.ok is True
    assert result.external_message_ids == ["wa-message-1"]
    assert len(requests) == 1


def test_whatsapp_passes_original_voice_file_to_bridge(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["voice_path"].endswith("voice.webm")
        assert payload["voice_mime_type"] == "audio/webm"
        return httpx.Response(
            200,
            request=request,
            json={
                "ok": True,
                "message_ids": ["wa-image-1", "wa-voice-1"],
            },
        )

    adapter = WhatsAppAdapter(
        bridge_url="http://localhost:8780/",
        bridge_token="bridge-test-secret",
        upload_root=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    bundle = _bundle(
        tmp_path,
        voice=("voice.webm", b"\x1aE\xdf\xa3original-webm-opus"),
        voice_mime="audio/webm",
    )

    result = adapter.send(bundle, "120363123456789@g.us", "whatsapp-voice")

    assert result.ok is True
    assert result.external_message_ids == ["wa-image-1", "wa-voice-1"]


def test_whatsapp_rejects_invalid_destination_before_network(tmp_path):
    def unexpected_request(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("invalid destination must not reach bridge")

    adapter = WhatsAppAdapter(
        bridge_url="http://127.0.0.1:8780",
        bridge_token="bridge-test-secret",
        upload_root=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(unexpected_request)),
    )

    result = adapter.send(_bundle(tmp_path), "گروه تست", "whatsapp-invalid")

    assert result.ok is False
    assert result.error_code == "whatsapp_destination_invalid"
    assert result.retryable is False


def test_whatsapp_preserves_partial_send_and_does_not_retry(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            207,
            request=request,
            json={
                "ok": False,
                "error_code": "whatsapp_voice_partial",
                "retryable": False,
                "message_ids": ["wa-image-1"],
            },
        )

    adapter = WhatsAppAdapter(
        bridge_url="http://127.0.0.1:8780",
        bridge_token="bridge-test-secret",
        upload_root=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = adapter.send(_bundle(tmp_path), "120363123456789@g.us", "partial")

    assert result.ok is False
    assert result.external_message_ids == ["wa-image-1"]
    assert result.error_code == "whatsapp_voice_partial"
    assert result.retryable is False


def test_whatsapp_marks_unlinked_bridge_as_retryable(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            409,
            request=request,
            json={
                "ok": False,
                "error_code": "whatsapp_not_ready",
                "retryable": True,
            },
        )

    adapter = WhatsAppAdapter(
        bridge_url="http://127.0.0.1:8780",
        bridge_token="bridge-test-secret",
        upload_root=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = adapter.send(_bundle(tmp_path), "120363123456789@g.us", "not-ready")

    assert result.ok is False
    assert result.error_code == "whatsapp_not_ready"
    assert result.retryable is True


def test_whatsapp_bridge_must_be_local(tmp_path):
    with pytest.raises(ValueError, match="local HTTP"):
        WhatsAppAdapter(
            bridge_url="https://example.com",
            bridge_token="bridge-test-secret",
            upload_root=tmp_path,
        )
