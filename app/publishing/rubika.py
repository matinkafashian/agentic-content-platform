import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any
from urllib.parse import urlparse

import httpx

from app.publishing.adapters import DeliveryResult
from app.publishing.models import PostBundle

RUBIKA_CAPTION_LIMIT = 4096
RUBIKA_IMAGE_LIMIT_BYTES = 10 * 1024 * 1024
RUBIKA_FILE_LIMIT_BYTES = 50 * 1024 * 1024
RUBIKA_IMAGE_MIMES = {"image/gif", "image/jpeg", "image/png", "image/webp"}


class RubikaAdapter:
    """Publish an immutable post bundle through Rubika's official Bot API."""

    platform = "rubika"
    service_label = "روبیکا"
    api_base_url = "https://botapi.rubika.ir"

    def __init__(
        self,
        *,
        bot_token: str,
        upload_root: Path,
        timeout_seconds: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.upload_root = upload_root
        self._base_url = f"{self.api_base_url}/v3/{bot_token}"
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def send(self, bundle: PostBundle, destination: str, idempotency_key: str) -> DeliveryResult:
        del idempotency_key
        validation_error = self.validate(bundle, destination)
        if validation_error is not None:
            return validation_error

        try:
            image_path = (
                self._bundle_path(bundle, bundle.image_relative_path)
                if bundle.image_relative_path
                else None
            )
            voice_path = (
                self._bundle_path(bundle, bundle.voice_relative_path)
                if bundle.voice_relative_path
                else None
            )
        except (OSError, ValueError):
            return DeliveryResult.failure(
                code="rubika_bundle_invalid",
                message="فایل رسانه بسته نهایی برای روبیکا معتبر یا قابل دسترسی نیست",
                retryable=False,
            )

        sent_ids: list[str] = []
        if image_path is not None:
            image_result = self._upload_and_send(
                destination=destination.strip(),
                path=image_path,
                mime_type=bundle.image_mime_type or "application/octet-stream",
                file_type="Image",
                text=bundle.caption_snapshot or None,
            )
            if not image_result.ok:
                return image_result
            sent_ids.extend(image_result.external_message_ids)
        elif bundle.caption_snapshot:
            text_result = self._send_text(destination.strip(), bundle.caption_snapshot)
            if not text_result.ok:
                return text_result
            sent_ids.extend(text_result.external_message_ids)
        if voice_path is None:
            return DeliveryResult.success(sent_ids)

        # Rubika only accepts MP3 for its native Voice type. Browser recordings
        # are WebM/Opus, so they are sent as File to preserve the original bytes.
        voice_type = "Voice" if bundle.voice_mime_type == "audio/mpeg" else "File"
        voice_result = self._upload_and_send(
            destination=destination.strip(),
            path=voice_path,
            mime_type=bundle.voice_mime_type or "application/octet-stream",
            file_type=voice_type,
        )
        if voice_result.ok:
            return DeliveryResult.success([*sent_ids, *voice_result.external_message_ids])
        if not sent_ids:
            return voice_result
        return DeliveryResult(
            ok=False,
            external_message_ids=sent_ids,
            error_code="rubika_voice_partial",
            safe_error_message=(
                "پست اصلی ارسال شد، اما وویس در روبیکا ارسال نشد؛ برای جلوگیری "
                "از تکرار، ارسال خودکار دوباره انجام نمی‌شود"
            ),
            retryable=False,
        )

    def validate(self, bundle: PostBundle, destination: str) -> DeliveryResult | None:
        if len(bundle.caption_snapshot) > RUBIKA_CAPTION_LIMIT:
            return DeliveryResult.failure(
                code="rubika_caption_too_long",
                message="متن برای روبیکا باید حداکثر ۴۰۹۶ نویسه باشد",
                retryable=False,
            )
        if (
            not destination
            or destination != destination.strip()
            or not re.fullmatch(r"[A-Za-z0-9_-]{2,200}", destination)
        ):
            return DeliveryResult.failure(
                code="rubika_destination_invalid",
                message="شناسه مقصد روبیکا معتبر نیست؛ chat_id کانال را وارد کنید",
                retryable=False,
            )
        if bundle.image_mime_type is not None and bundle.image_mime_type not in RUBIKA_IMAGE_MIMES:
            return DeliveryResult.failure(
                code="rubika_image_format_invalid",
                message="فرمت تصویر برای روبیکا باید JPG، PNG، GIF یا WebP باشد",
                retryable=False,
            )
        if (
            bundle.image_size_bytes is not None
            and bundle.image_size_bytes > RUBIKA_IMAGE_LIMIT_BYTES
        ):
            return DeliveryResult.failure(
                code="rubika_image_too_large",
                message="حجم تصویر روبیکا باید حداکثر ۱۰ مگابایت باشد",
                retryable=False,
            )
        if (
            bundle.voice_size_bytes is not None
            and bundle.voice_size_bytes > RUBIKA_FILE_LIMIT_BYTES
        ):
            return DeliveryResult.failure(
                code="rubika_voice_too_large",
                message="حجم وویس روبیکا باید حداکثر ۵۰ مگابایت باشد",
                retryable=False,
            )
        return None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _send_text(self, destination: str, text: str) -> DeliveryResult:
        response = self._post_json("sendMessage", {"chat_id": destination, "text": text})
        if isinstance(response, DeliveryResult):
            return response
        message_id = self._data(response).get("message_id")
        if not isinstance(message_id, (str, int)) or not str(message_id).strip():
            return DeliveryResult.failure(
                code="rubika_invalid_response",
                message="پاسخ روبیکا برای ارسال متن کامل نبود",
                retryable=True,
            )
        return DeliveryResult.success([str(message_id)])

    def _bundle_path(self, bundle: PostBundle, relative_path: str) -> Path:
        candidate = PurePosixPath(relative_path.replace("\\", "/"))
        windows = PureWindowsPath(relative_path)
        expected = ("private", "bundles", bundle.bundle_key)
        if (
            candidate.is_absolute()
            or windows.is_absolute()
            or ".." in candidate.parts
            or candidate.parts[:3] != expected
        ):
            raise ValueError("invalid bundle path")
        path = self.upload_root.joinpath(*candidate.parts)
        if not path.is_file():
            raise ValueError("bundle file not found")
        return path

    def _upload_and_send(
        self,
        *,
        destination: str,
        path: Path,
        mime_type: str,
        file_type: str,
        text: str | None = None,
    ) -> DeliveryResult:
        upload_request = self._post_json("requestSendFile", {"type": file_type})
        if isinstance(upload_request, DeliveryResult):
            return upload_request
        upload_url = self._data(upload_request).get("upload_url")
        if not self._safe_upload_url(upload_url):
            return DeliveryResult.failure(
                code="rubika_invalid_response",
                message="پاسخ روبیکا برای بارگذاری فایل کامل نبود",
                retryable=True,
            )
        try:
            upload_response = self._client.post(
                upload_url,
                files={"file": (path.name, path.read_bytes(), mime_type)},
            )
        except (OSError, httpx.TimeoutException, httpx.NetworkError):
            return DeliveryResult.failure(
                code="rubika_network_error",
                message="ارتباط با روبیکا موقتاً برقرار نشد",
                retryable=True,
            )
        upload_payload = self._payload(upload_response)
        if not self._is_success(upload_response, upload_payload):
            return self._api_failure(upload_response.status_code, upload_payload)
        file_id = self._data(upload_payload).get("file_id")
        if not isinstance(file_id, str) or not file_id.strip():
            return DeliveryResult.failure(
                code="rubika_invalid_response",
                message="شناسه فایل از روبیکا دریافت نشد",
                retryable=True,
            )
        payload = {"chat_id": destination, "file_id": file_id}
        if text is not None:
            payload["text"] = text
        send_response = self._post_json("sendFile", payload)
        if isinstance(send_response, DeliveryResult):
            return send_response
        message_id = self._data(send_response).get("message_id")
        if not isinstance(message_id, (str, int)) or not str(message_id).strip():
            return DeliveryResult.failure(
                code="rubika_invalid_response",
                message="پاسخ روبیکا کامل نبود؛ نتیجه ارسال دوباره بررسی می‌شود",
                retryable=True,
            )
        return DeliveryResult.success([str(message_id)])

    def _post_json(self, method: str, payload: dict[str, str]) -> dict[str, Any] | DeliveryResult:
        try:
            response = self._client.post(f"{self._base_url}/{method}", json=payload)
        except (httpx.TimeoutException, httpx.NetworkError):
            return DeliveryResult.failure(
                code="rubika_network_error",
                message="ارتباط با روبیکا موقتاً برقرار نشد",
                retryable=True,
            )
        response_payload = self._payload(response)
        if not self._is_success(response, response_payload):
            return self._api_failure(response.status_code, response_payload)
        return response_payload

    @staticmethod
    def _payload(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError:
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _data(payload: dict[str, Any]) -> dict[str, Any]:
        data = payload.get("data", payload)
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _is_success(response: httpx.Response, payload: dict[str, Any]) -> bool:
        if not 200 <= response.status_code < 300:
            return False
        status = payload.get("status")
        if isinstance(status, str):
            return status.upper() == "OK"
        if "ok" in payload:
            return payload.get("ok") is True
        return bool(payload)

    @staticmethod
    def _safe_upload_url(value: object) -> bool:
        if not isinstance(value, str):
            return False
        parsed = urlparse(value)
        return parsed.scheme == "https" and bool(parsed.hostname)

    @staticmethod
    def _api_failure(status_code: int, payload: dict[str, Any]) -> DeliveryResult:
        detail = str(
            payload.get("status_det") or payload.get("message") or payload.get("error") or ""
        ).upper()
        if status_code == 429 or "TOO_MANY" in detail:
            return DeliveryResult.failure(
                code="rubika_rate_limited",
                message="روبیکا محدودیت موقت اعمال کرد؛ ارسال دوباره تلاش می‌شود",
                retryable=True,
            )
        if status_code == 401 or "UNAUTHORIZED" in detail:
            return DeliveryResult.failure(
                code="rubika_unauthorized",
                message="توکن ربات روبیکا معتبر نیست",
                retryable=False,
            )
        if status_code == 403 or "FORBIDDEN" in detail:
            return DeliveryResult.failure(
                code="rubika_forbidden",
                message=(
                    "ربات روبیکا اجازه ارسال به این کانال را ندارد؛ دسترسی ادمین را بررسی کنید"
                ),
                retryable=False,
            )
        if status_code >= 500:
            return DeliveryResult.failure(
                code="rubika_server_error",
                message="سرویس روبیکا موقتاً در دسترس نیست",
                retryable=True,
            )
        return DeliveryResult.failure(
            code="rubika_bad_request",
            message="مقصد یا اطلاعات ارسال روبیکا معتبر نیست",
            retryable=False,
        )
