import json

import httpx

from app.publishing.models import PostBundle
from app.publishing.rubika import RubikaAdapter


def _bundle(tmp_path, *, caption="معرفی محصول", voice=None, voice_mime=None):
    bundle_key = "bundle-rubika-test"
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
        caption_snapshot=caption,
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


def _success(data):
    return {"status": "OK", "data": data}


def test_rubika_uploads_image_then_sends_caption_to_channel(tmp_path):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        method = request.url.path.rsplit("/", 1)[-1]
        if method == "requestSendFile":
            assert json.loads(request.content) == {"type": "Image"}
            return httpx.Response(
                200,
                request=request,
                json=_success({"upload_url": "https://upload.rubika.ir/file"}),
            )
        if request.url.host == "upload.rubika.ir":
            assert b"valid-image-fixture" in request.content
            return httpx.Response(
                200, request=request, json=_success({"file_id": "image-file-id"})
            )
        assert method == "sendFile"
        assert json.loads(request.content) == {
            "chat_id": "channel-chat-id",
            "file_id": "image-file-id",
            "text": "معرفی محصول",
        }
        return httpx.Response(
            200, request=request, json=_success({"message_id": "message-101"})
        )

    adapter = RubikaAdapter(
        bot_token="rubika-test-token",
        upload_root=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = adapter.send(_bundle(tmp_path), "channel-chat-id", "rubika-1")

    assert result.ok is True
    assert result.external_message_ids == ["message-101"]
    assert len(requests) == 3
    assert requests[0].url.path == "/v3/rubika-test-token/requestSendFile"
    assert requests[2].url.path == "/v3/rubika-test-token/sendFile"


def test_rubika_preserves_webm_voice_as_file_after_main_post(tmp_path):
    requested_types: list[str] = []
    sent_payloads: list[dict[str, str]] = []
    uploaded_bodies: list[bytes] = []
    upload_number = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal upload_number
        method = request.url.path.rsplit("/", 1)[-1]
        if method == "requestSendFile":
            file_type = json.loads(request.content)["type"]
            requested_types.append(file_type)
            upload_number += 1
            return httpx.Response(
                200,
                request=request,
                json=_success(
                    {"upload_url": f"https://upload.rubika.ir/file-{upload_number}"}
                ),
            )
        if request.url.host == "upload.rubika.ir":
            uploaded_bodies.append(request.content)
            return httpx.Response(
                200,
                request=request,
                json=_success({"file_id": f"uploaded-{len(uploaded_bodies)}"}),
            )
        payload = json.loads(request.content)
        sent_payloads.append(payload)
        return httpx.Response(
            200,
            request=request,
            json=_success({"message_id": f"message-{len(sent_payloads)}"}),
        )

    adapter = RubikaAdapter(
        bot_token="rubika-test-token",
        upload_root=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    bundle = _bundle(
        tmp_path,
        voice=("voice.webm", b"\x1aE\xdf\xa3original-webm-opus"),
        voice_mime="audio/webm",
    )

    result = adapter.send(bundle, "channel-chat-id", "rubika-voice")

    assert result.ok is True
    assert result.external_message_ids == ["message-1", "message-2"]
    assert requested_types == ["Image", "File"]
    assert b"\x1aE\xdf\xa3original-webm-opus" in uploaded_bodies[1]
    assert sent_payloads[1] == {
        "chat_id": "channel-chat-id",
        "file_id": "uploaded-2",
    }


def test_rubika_rejects_invalid_destination_before_network(tmp_path):
    def unexpected_request(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("invalid destination must not reach Rubika")

    adapter = RubikaAdapter(
        bot_token="rubika-test-token",
        upload_root=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(unexpected_request)),
    )

    result = adapter.send(_bundle(tmp_path), "شناسه کانال", "rubika-invalid")

    assert result.ok is False
    assert result.error_code == "rubika_destination_invalid"
    assert result.retryable is False


def test_rubika_permission_error_is_not_retried(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            request=request,
            json={"status": "ERROR", "status_det": "FORBIDDEN"},
        )

    adapter = RubikaAdapter(
        bot_token="rubika-test-token",
        upload_root=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = adapter.send(_bundle(tmp_path), "channel-chat-id", "rubika-forbidden")

    assert result.ok is False
    assert result.error_code == "rubika_forbidden"
    assert result.retryable is False
    assert "ادمین" in result.safe_error_message


def test_rubika_marks_voice_failure_as_partial_without_retry(tmp_path):
    upload_count = 0
    send_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal upload_count, send_count
        method = request.url.path.rsplit("/", 1)[-1]
        if method == "requestSendFile":
            upload_count += 1
            return httpx.Response(
                200,
                request=request,
                json=_success(
                    {"upload_url": f"https://upload.rubika.ir/{upload_count}"}
                ),
            )
        if request.url.host == "upload.rubika.ir":
            return httpx.Response(
                200,
                request=request,
                json=_success({"file_id": f"file-{upload_count}"}),
            )
        send_count += 1
        if send_count == 1:
            return httpx.Response(
                200, request=request, json=_success({"message_id": "main-message"})
            )
        return httpx.Response(
            400,
            request=request,
            json={"status": "ERROR", "status_det": "INVALID_FILE"},
        )

    adapter = RubikaAdapter(
        bot_token="rubika-test-token",
        upload_root=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    bundle = _bundle(
        tmp_path,
        voice=("voice.webm", b"\x1aE\xdf\xa3voice"),
        voice_mime="audio/webm",
    )

    result = adapter.send(bundle, "channel-chat-id", "rubika-partial")

    assert result.ok is False
    assert result.external_message_ids == ["main-message"]
    assert result.error_code == "rubika_voice_partial"
    assert result.retryable is False
