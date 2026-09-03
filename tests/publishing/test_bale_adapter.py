import httpx

from app.publishing.bale import BaleAdapter
from app.publishing.models import PostBundle


def _bundle(
    tmp_path, *, caption="معرفی محصول", image_enabled=True, voice=None, voice_mime=None
):
    bundle_key = "bundle-bale-test"
    directory = tmp_path / "private" / "bundles" / bundle_key
    directory.mkdir(parents=True, exist_ok=True)
    image = directory / "image.png" if image_enabled else None
    if image is not None:
        image.write_bytes(b"valid-image-fixture")
    voice_path = None
    if voice is not None:
        voice_path = directory / voice[0]
        voice_path.write_bytes(voice[1])
    return PostBundle(
        bundle_key=bundle_key,
        content_draft_id=1,
        caption_snapshot=caption,
        image_relative_path=image.relative_to(tmp_path).as_posix() if image else None,
        image_mime_type="image/png" if image else None,
        image_size_bytes=image.stat().st_size if image else None,
        image_sha256="0" * 64 if image else None,
        voice_relative_path=(
            voice_path.relative_to(tmp_path).as_posix() if voice_path else None
        ),
        voice_mime_type=voice_mime,
        voice_size_bytes=voice_path.stat().st_size if voice_path else None,
        voice_sha256="1" * 64 if voice_path else None,
        voice_duration_ms=1200 if voice_path else None,
    )


def test_bale_posts_photo_and_full_caption_to_channel(tmp_path):
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            request=request,
            json={"ok": True, "result": {"message_id": 821}},
        )

    adapter = BaleAdapter(
        bot_token="123:bale-test-token",
        upload_root=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    caption = "ا" * 2000

    result = adapter.send(_bundle(tmp_path, caption=caption), "@bale_channel", "bale-1")

    assert result.ok is True
    assert result.external_message_ids == ["821"]
    assert len(requests) == 1
    assert requests[0].url.path == "/bot123:bale-test-token/sendPhoto"
    assert requests[0].url.host == "tapi.bale.ai"
    assert caption.encode() in requests[0].content


def test_bale_sends_text_without_an_image(tmp_path):
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200, request=request, json={"ok": True, "result": {"message_id": 822}}
        )

    adapter = BaleAdapter(
        bot_token="123:bale-test-token",
        upload_root=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = adapter.send(
        _bundle(tmp_path, image_enabled=False), "@bale_channel", "bale-text"
    )

    assert result.ok is True
    assert result.external_message_ids == ["822"]
    assert requests[0].url.path.endswith("/sendMessage")


def test_bale_rejects_caption_over_4096_before_network(tmp_path):
    def unexpected_request(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("invalid Bale caption must not reach the network")

    adapter = BaleAdapter(
        bot_token="123:bale-test-token",
        upload_root=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(unexpected_request)),
    )

    result = adapter.send(
        _bundle(tmp_path, caption="الف" * 4097), "@bale_channel", "bale-long"
    )

    assert result.ok is False
    assert result.error_code == "bale_caption_too_long"
    assert result.retryable is False


def test_bale_sends_ogg_voice_after_photo(tmp_path):
    methods = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.url.path.rsplit("/", 1)[-1])
        return httpx.Response(
            200,
            request=request,
            json={"ok": True, "result": {"message_id": 820 + len(methods)}},
        )

    adapter = BaleAdapter(
        bot_token="123:bale-test-token",
        upload_root=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    bundle = _bundle(
        tmp_path,
        voice=("voice.ogg", b"OggSvoice-fixture"),
        voice_mime="audio/ogg",
    )

    result = adapter.send(bundle, "@bale_channel", "bale-voice")

    assert result.ok is True
    assert result.external_message_ids == ["821", "822"]
    assert methods == ["sendPhoto", "sendVoice"]


def test_bale_accepts_numeric_channel_and_rejects_invalid_name(tmp_path):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 821}})

    adapter = BaleAdapter(
        bot_token="123:bale-test-token",
        upload_root=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    numeric = adapter.send(_bundle(tmp_path), "-123456789", "bale-numeric")
    invalid = adapter.send(_bundle(tmp_path), "کانال تست", "bale-invalid")

    assert numeric.ok is True
    assert invalid.ok is False
    assert invalid.error_code == "bale_destination_invalid"
    assert "@" in invalid.safe_error_message


def test_bale_permission_error_is_not_retried(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            request=request,
            json={"ok": False, "error_code": 403, "description": "Forbidden"},
        )

    adapter = BaleAdapter(
        bot_token="123:bale-test-token",
        upload_root=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = adapter.send(_bundle(tmp_path), "@bale_channel", "bale-forbidden")

    assert result.ok is False
    assert result.error_code == "bale_forbidden"
    assert result.retryable is False
    assert "مدیر" in result.safe_error_message
