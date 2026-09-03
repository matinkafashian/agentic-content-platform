import httpx

from app.publishing.models import PostBundle
from app.publishing.telegram import TelegramAdapter, TelegramVoicePreparer


def _bundle(
    tmp_path, *, caption="معرفی محصول", image_enabled=True, voice=None, voice_mime=None
):
    bundle_key = "bundle-telegram-test"
    directory = tmp_path / "private" / "bundles" / bundle_key
    directory.mkdir(parents=True)
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
        voice_relative_path=(voice_path.relative_to(tmp_path).as_posix() if voice_path else None),
        voice_mime_type=voice_mime,
        voice_size_bytes=voice_path.stat().st_size if voice_path else None,
        voice_sha256="1" * 64 if voice_path else None,
        voice_duration_ms=1200 if voice_path else None,
    )


def test_send_posts_photo_and_caption_to_channel(tmp_path):
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "ok": True,
                "result": {
                    "message_id": 321,
                    "date": 0,
                    "chat": {"id": -1001, "type": "channel"},
                },
            },
        )

    adapter = TelegramAdapter(
        bot_token="123:test-token",
        upload_root=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = adapter.send(_bundle(tmp_path), "@test_channel", "delivery-1")

    assert result.ok is True
    assert result.external_message_ids == ["321"]
    assert len(requests) == 1
    assert requests[0].url.path == "/bot123:test-token/sendPhoto"
    body = requests[0].content
    assert b'form-data; name="chat_id"' in body
    assert b"@test_channel" in body
    assert "معرفی محصول".encode() in body
    assert b'form-data; name="photo"; filename="image.png"' in body


def test_text_only_bundle_uses_send_message(tmp_path):
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            request=request,
            json={"ok": True, "result": {"message_id": 401}},
        )

    adapter = TelegramAdapter(
        bot_token="123:test-token",
        upload_root=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = adapter.send(
        _bundle(tmp_path, image_enabled=False), "@test_channel", "text-only"
    )

    assert result.ok is True
    assert result.external_message_ids == ["401"]
    assert requests[0].url.path.endswith("/sendMessage")


def test_voice_only_bundle_uses_send_voice(tmp_path):
    methods = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.url.path.rsplit("/", 1)[-1])
        return httpx.Response(
            200,
            request=request,
            json={"ok": True, "result": {"message_id": 402}},
        )

    adapter = TelegramAdapter(
        bot_token="123:test-token",
        upload_root=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    bundle = _bundle(
        tmp_path,
        caption="",
        image_enabled=False,
        voice=("voice.ogg", b"OggSvoice-fixture"),
        voice_mime="audio/ogg",
    )

    result = adapter.send(bundle, "@test_channel", "voice-only")

    assert result.ok is True
    assert result.external_message_ids == ["402"]
    assert methods == ["sendVoice"]


def test_long_caption_is_sent_as_separate_message_without_truncation(tmp_path):
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        message_id = 321 if request.url.path.endswith("/sendPhoto") else 322
        return httpx.Response(
            200,
            request=request,
            json={
                "ok": True,
                "result": {
                    "message_id": message_id,
                    "date": 0,
                    "chat": {"id": -1001, "type": "channel"},
                },
            },
        )

    adapter = TelegramAdapter(
        bot_token="123:test-token",
        upload_root=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    caption = "الف" * 1057

    result = adapter.send(
        _bundle(tmp_path, caption=caption), "@test_channel", "delivery-2"
    )

    assert result.ok is True
    assert result.external_message_ids == ["321", "322"]
    assert [request.url.path.rsplit("/", 1)[-1] for request in requests] == [
        "sendPhoto",
        "sendMessage",
    ]
    assert caption.encode() not in requests[0].content
    assert httpx.QueryParams(requests[1].content.decode()).get("text") == caption


def test_long_caption_failure_after_photo_is_not_retried(tmp_path):
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/sendPhoto"):
            return httpx.Response(
                200,
                request=request,
                json={
                    "ok": True,
                    "result": {
                        "message_id": 321,
                        "date": 0,
                        "chat": {"id": -1001, "type": "channel"},
                    },
                },
            )
        return httpx.Response(
            403,
            request=request,
            json={"ok": False, "error_code": 403, "description": "Forbidden"},
        )

    adapter = TelegramAdapter(
        bot_token="123:test-token",
        upload_root=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = adapter.send(
        _bundle(tmp_path, caption="الف" * 1057),
        "@test_channel",
        "delivery-caption-partial",
    )

    assert len(requests) == 2
    assert result.ok is False
    assert result.error_code == "telegram_caption_partial"
    assert result.external_message_ids == ["321"]
    assert result.retryable is False


def test_caption_over_message_limit_fails_before_network_call(tmp_path):
    def unexpected_request(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("caption validation must happen before Telegram is called")

    adapter = TelegramAdapter(
        bot_token="123:test-token",
        upload_root=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(unexpected_request)),
    )

    result = adapter.send(
        _bundle(tmp_path, caption="الف" * 4097),
        "@test_channel",
        "delivery-too-long",
    )

    assert result.ok is False
    assert result.error_code == "telegram_caption_too_long"
    assert result.retryable is False


def test_invalid_channel_destination_fails_before_network_call(tmp_path):
    def unexpected_request(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("destination validation must happen before Telegram is called")

    adapter = TelegramAdapter(
        bot_token="123:test-token",
        upload_root=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(unexpected_request)),
    )

    result = adapter.send(_bundle(tmp_path), "کانال تست", "delivery-invalid-channel")

    assert result.ok is False
    assert result.error_code == "telegram_destination_invalid"
    assert result.retryable is False
    assert "@" in result.safe_error_message


def test_rate_limit_is_retryable(tmp_path):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            json={
                "ok": False,
                "error_code": 429,
                "description": "Too Many Requests: retry after 12",
                "parameters": {"retry_after": 12},
            },
        )

    adapter = TelegramAdapter(
        bot_token="123:test-token",
        upload_root=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = adapter.send(_bundle(tmp_path), "@test_channel", "delivery-3")

    assert result.ok is False
    assert result.error_code == "telegram_rate_limited"
    assert result.retryable is True
    assert "۱۲" in result.safe_error_message


def test_permission_error_is_not_retried(tmp_path):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={
                "ok": False,
                "error_code": 403,
                "description": "Forbidden: bot is not an administrator of the channel",
            },
        )

    adapter = TelegramAdapter(
        bot_token="123:test-token",
        upload_root=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = adapter.send(_bundle(tmp_path), "@test_channel", "delivery-4")

    assert result.ok is False
    assert result.error_code == "telegram_forbidden"
    assert result.retryable is False
    assert "دسترسی" in result.safe_error_message


def test_ogg_voice_is_sent_after_photo_with_both_message_ids(tmp_path):
    methods = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.url.path.rsplit("/", 1)[-1])
        message_id = 321 if methods[-1] == "sendPhoto" else 322
        return httpx.Response(
            200,
            json={
                "ok": True,
                "result": {
                    "message_id": message_id,
                    "date": 0,
                    "chat": {"id": -1001, "type": "channel"},
                },
            },
        )

    adapter = TelegramAdapter(
        bot_token="123:test-token",
        upload_root=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    bundle = _bundle(
        tmp_path,
        voice=("voice.ogg", b"OggSvoice-fixture"),
        voice_mime="audio/ogg",
    )

    result = adapter.send(bundle, "@test_channel", "delivery-voice")

    assert result.ok is True
    assert result.external_message_ids == ["321", "322"]
    assert methods == ["sendPhoto", "sendVoice"]


def test_webm_voice_is_remuxed_to_ogg_without_reencoding(tmp_path):
    source = tmp_path / "voice.webm"
    source.write_bytes(b"\x1aE\xdf\xa3webm-opus-fixture")
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        output = command[-1]
        output.write_bytes(b"OggSsame-opus-packets")
        return type("Result", (), {"returncode": 0})()

    preparer = TelegramVoicePreparer(ffmpeg_binary="ffmpeg-test", runner=runner)

    with preparer.prepare(source, "audio/webm") as prepared:
        assert prepared.mime_type == "audio/ogg"
        assert prepared.path.suffix == ".ogg"
        assert prepared.path.read_bytes() == b"OggSsame-opus-packets"
        assert calls[0][0] == [
            "ffmpeg-test",
            "-y",
            "-i",
            source,
            "-vn",
            "-c:a",
            "copy",
            prepared.path,
        ]
        assert calls[0][1] == {"capture_output": True, "check": False}


def test_voice_failure_after_photo_is_not_retried_or_hidden(tmp_path):
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        if request.url.path.endswith("/sendPhoto"):
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "result": {
                        "message_id": 321,
                        "date": 0,
                        "chat": {"id": -1001, "type": "channel"},
                    },
                },
            )
        return httpx.Response(
            403,
            json={"ok": False, "error_code": 403, "description": "Forbidden"},
        )

    adapter = TelegramAdapter(
        bot_token="123:test-token",
        upload_root=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    bundle = _bundle(
        tmp_path,
        voice=("voice.ogg", b"OggSvoice-fixture"),
        voice_mime="audio/ogg",
    )

    result = adapter.send(bundle, "@test_channel", "delivery-partial")

    assert request_count == 2
    assert result.ok is False
    assert result.error_code == "telegram_voice_partial"
    assert result.external_message_ids == ["321"]
    assert result.retryable is False
    assert "پست اصلی ارسال شد" in result.safe_error_message


def test_missing_ffmpeg_blocks_webm_before_photo_is_sent(tmp_path):
    def missing_runner(_command, **_kwargs):
        raise FileNotFoundError("ffmpeg")

    def unexpected_request(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("media must not be sent when voice preparation failed")

    adapter = TelegramAdapter(
        bot_token="123:test-token",
        upload_root=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(unexpected_request)),
        voice_preparer=TelegramVoicePreparer(runner=missing_runner),
    )
    bundle = _bundle(
        tmp_path,
        voice=("voice.webm", b"\x1aE\xdf\xa3webm-opus-fixture"),
        voice_mime="audio/webm",
    )

    result = adapter.send(bundle, "@test_channel", "delivery-no-ffmpeg")

    assert result.ok is False
    assert result.error_code == "telegram_voice_unavailable"
    assert result.external_message_ids == []
    assert result.retryable is False
