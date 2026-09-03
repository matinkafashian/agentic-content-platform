import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any
from urllib.parse import urlparse

import httpx

from app.publishing.adapters import DeliveryResult
from app.publishing.models import PostBundle

WHATSAPP_DESTINATION_PATTERN = re.compile(r"^[0-9]+@(g\.us|newsletter)$")
WHATSAPP_IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp"}


class WhatsAppAdapter:
    """Publish immutable bundles through the local WhatsApp Web bridge."""

    platform = "whatsapp"
    service_label = "واتساپ"

    def __init__(
        self,
        *,
        bridge_url: str,
        bridge_token: str,
        upload_root: Path,
        timeout_seconds: float = 60.0,
        client: httpx.Client | None = None,
    ) -> None:
        normalized_url = bridge_url.rstrip("/")
        parsed = urlparse(normalized_url)
        if parsed.scheme != "http" or parsed.hostname not in {
            "127.0.0.1",
            "localhost",
            "::1",
        }:
            raise ValueError("WhatsApp bridge must use a local HTTP address")
        self.upload_root = upload_root
        self._base_url = normalized_url
        self._bridge_token = bridge_token
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def send(
        self, bundle: PostBundle, destination: str, idempotency_key: str
    ) -> DeliveryResult:
        validation_error = self.validate(bundle, destination)
        if validation_error is not None:
            return validation_error
        try:
            image_path = self._bundle_path(bundle, bundle.image_relative_path)
            voice_path = (
                self._bundle_path(bundle, bundle.voice_relative_path)
                if bundle.voice_relative_path
                else None
            )
        except (OSError, ValueError):
            return DeliveryResult.failure(
                code="whatsapp_bundle_invalid",
                message="فایل رسانه بسته نهایی برای واتساپ معتبر یا قابل دسترسی نیست",
                retryable=False,
            )

        payload = {
            "destination": destination.strip(),
            "caption": bundle.caption_snapshot,
            "image_path": str(image_path.resolve()),
            "image_mime_type": bundle.image_mime_type,
            "voice_path": str(voice_path.resolve()) if voice_path else None,
            "voice_mime_type": bundle.voice_mime_type,
            "idempotency_key": idempotency_key,
        }
        try:
            response = self._client.post(
                f"{self._base_url}/send",
                json=payload,
                headers={"Authorization": f"Bearer {self._bridge_token}"},
            )
        except (httpx.TimeoutException, httpx.NetworkError):
            return DeliveryResult.failure(
                code="whatsapp_bridge_unavailable",
                message=(
                    "اتصال محلی واتساپ در دسترس نیست؛ سرویس واتساپ را بررسی کنید"
                ),
                retryable=True,
            )

        response_payload = self._payload(response)
        message_ids = self._message_ids(response_payload)
        if response.is_success and response_payload.get("ok") is True:
            if not message_ids:
                return DeliveryResult.failure(
                    code="whatsapp_invalid_response",
                    message="نتیجه ارسال واتساپ قابل تأیید نبود",
                    retryable=False,
                )
            return DeliveryResult.success(message_ids)
        return self._failure(response.status_code, response_payload, message_ids)

    def validate(
        self, bundle: PostBundle, destination: str
    ) -> DeliveryResult | None:
        if (
            not destination
            or destination != destination.strip()
            or WHATSAPP_DESTINATION_PATTERN.fullmatch(destination) is None
        ):
            return DeliveryResult.failure(
                code="whatsapp_destination_invalid",
                message=(
                    "شناسه مقصد واتساپ معتبر نیست؛ شناسه گروه با @g.us یا کانال "
                    "با @newsletter را وارد کنید"
                ),
                retryable=False,
            )
        if bundle.image_mime_type not in WHATSAPP_IMAGE_MIMES:
            return DeliveryResult.failure(
                code="whatsapp_image_format_invalid",
                message="فرمت تصویر واتساپ باید JPG، PNG یا WebP باشد",
                retryable=False,
            )
        return None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

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

    @staticmethod
    def _payload(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError:
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _message_ids(payload: dict[str, Any]) -> list[str]:
        values = payload.get("message_ids", [])
        if not isinstance(values, list):
            return []
        return [str(value) for value in values if str(value).strip()]

    @staticmethod
    def _failure(
        status_code: int,
        payload: dict[str, Any],
        message_ids: list[str],
    ) -> DeliveryResult:
        code = str(payload.get("error_code") or "")
        retryable = bool(payload.get("retryable"))
        allowed = {
            "whatsapp_not_ready": (
                "واتساپ هنوز متصل نیست؛ QR اتصال را اسکن کنید",
                True,
            ),
            "whatsapp_destination_invalid": (
                "گروه یا کانال مقصد واتساپ معتبر نیست یا در دسترس این حساب نیست",
                False,
            ),
            "whatsapp_media_invalid": (
                "فایل رسانه برای واتساپ معتبر یا قابل دسترسی نیست",
                False,
            ),
            "whatsapp_send_forbidden": (
                "حساب واتساپ اجازه ارسال به این گروه یا کانال را ندارد",
                False,
            ),
            "whatsapp_delivery_unverified": (
                "واتساپ دریافت پیام را تأیید نکرد؛ برای جلوگیری از تکرار، "
                "ارسال خودکار دوباره انجام نمی‌شود",
                False,
            ),
            "whatsapp_voice_partial": (
                "پست اصلی در واتساپ ارسال شد، اما وویس ارسال نشد؛ ارسال خودکار تکرار نمی‌شود",
                False,
            ),
            "whatsapp_bridge_error": (
                "سرویس محلی واتساپ با خطا روبه‌رو شد",
                True,
            ),
        }
        if status_code == 401:
            code = "whatsapp_bridge_unauthorized"
            message = "کلید اتصال محلی واتساپ معتبر نیست"
            retryable = False
        elif code in allowed:
            message, default_retryable = allowed[code]
            retryable = retryable and default_retryable
        elif status_code == 409:
            code = "whatsapp_not_ready"
            message = "واتساپ هنوز متصل نیست؛ QR اتصال را اسکن کنید"
            retryable = True
        elif status_code >= 500:
            code = "whatsapp_bridge_error"
            message = "سرویس محلی واتساپ موقتاً در دسترس نیست"
            retryable = True
        else:
            code = "whatsapp_bad_request"
            message = "مقصد یا اطلاعات ارسال واتساپ معتبر نیست"
            retryable = False
        return DeliveryResult(
            ok=False,
            external_message_ids=message_ids,
            error_code=code,
            safe_error_message=message,
            retryable=retryable,
        )
