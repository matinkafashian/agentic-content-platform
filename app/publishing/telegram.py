import re
import subprocess
from collections.abc import Callable, Iterator
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from tempfile import TemporaryDirectory
from typing import Any

import httpx

from app.publishing.adapters import DeliveryResult
from app.publishing.models import PostBundle

TELEGRAM_CAPTION_LIMIT = 1024
TELEGRAM_MESSAGE_LIMIT = 4096
DIRECT_VOICE_MIMES = {"audio/ogg", "audio/mpeg", "audio/mp4", "audio/x-m4a"}


class TelegramVoicePreparationError(ValueError):
    pass


@dataclass(frozen=True)
class PreparedTelegramVoice:
    path: Path
    mime_type: str


class TelegramVoicePreparer:
    def __init__(
        self,
        *,
        ffmpeg_binary: str = "ffmpeg",
        runner: Callable[..., Any] = subprocess.run,
    ) -> None:
        self.ffmpeg_binary = ffmpeg_binary
        self.runner = runner

    @contextmanager
    def prepare(self, source: Path, mime_type: str) -> Iterator[PreparedTelegramVoice]:
        if mime_type in DIRECT_VOICE_MIMES:
            yield PreparedTelegramVoice(source, mime_type)
            return
        if mime_type != "audio/webm":
            raise TelegramVoicePreparationError("unsupported voice format")
        with TemporaryDirectory(prefix="telegram-voice-") as directory:
            output = Path(directory) / "voice.ogg"
            result = self.runner(
                [
                    self.ffmpeg_binary,
                    "-y",
                    "-i",
                    source,
                    "-vn",
                    "-c:a",
                    "copy",
                    output,
                ],
                capture_output=True,
                check=False,
            )
            if result.returncode != 0 or not output.is_file():
                raise TelegramVoicePreparationError("voice remux failed")
            yield PreparedTelegramVoice(output, "audio/ogg")


class TelegramAdapter:
    platform = "telegram"
    service_label = "تلگرام"
    api_base_url = "https://api.telegram.org"
    caption_limit = TELEGRAM_CAPTION_LIMIT
    message_limit = TELEGRAM_MESSAGE_LIMIT

    def __init__(
        self,
        *,
        bot_token: str,
        upload_root: Path,
        message_thread_id: int | None = None,
        timeout_seconds: float = 30.0,
        client: httpx.Client | None = None,
        voice_preparer: TelegramVoicePreparer | None = None,
    ) -> None:
        self.upload_root = upload_root
        self.message_thread_id = message_thread_id
        self._base_url = f"{self.api_base_url}/bot{bot_token}"
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=timeout_seconds)
        self._voice_preparer = voice_preparer or TelegramVoicePreparer()

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
                code=self._code("bundle_invalid"),
                message=(
                    f"فایل رسانه بسته نهایی برای {self.service_label} معتبر یا قابل دسترسی نیست"
                ),
                retryable=False,
            )
        voice_context = (
            self._voice_preparer.prepare(voice_path, bundle.voice_mime_type or "")
            if voice_path is not None
            else nullcontext(None)
        )
        try:
            with voice_context as prepared_voice:
                caption = bundle.caption_snapshot
                sent_ids: list[str] = []
                if image_path is not None:
                    photo_caption = caption if len(caption) <= self.caption_limit else None
                    photo_result = self._send_media(
                        method="sendPhoto",
                        field_name="photo",
                        path=image_path,
                        mime_type=bundle.image_mime_type or "application/octet-stream",
                        destination=destination,
                        caption=photo_caption,
                    )
                    if not photo_result.ok:
                        return photo_result
                    sent_ids.extend(photo_result.external_message_ids)
                    caption_needs_separate_message = bool(caption) and photo_caption is None
                else:
                    caption_needs_separate_message = bool(caption)
                if caption_needs_separate_message:
                    text_result = self._send_text(destination, caption)
                    if not text_result.ok:
                        if not sent_ids:
                            return text_result
                        return DeliveryResult(
                            ok=False,
                            external_message_ids=sent_ids,
                            error_code=self._code("caption_partial"),
                            safe_error_message=(
                                "عکس ارسال شد، اما متن کامل در "
                                f"{self.service_label} ارسال نشد؛ برای جلوگیری از تکرار "
                                "عکس، ارسال خودکار دوباره انجام نمی‌شود"
                            ),
                            retryable=False,
                        )
                    sent_ids.extend(text_result.external_message_ids)
                if prepared_voice is None:
                    return DeliveryResult.success(sent_ids)
                voice_result = self._send_media(
                    method="sendVoice",
                    field_name="voice",
                    path=prepared_voice.path,
                    mime_type=prepared_voice.mime_type,
                    destination=destination,
                )
        except (OSError, TelegramVoicePreparationError):
            return DeliveryResult.failure(
                code=self._code("voice_unavailable"),
                message=(
                    f"وویس برای ارسال {self.service_label} آماده نشد؛ تنظیمات FFmpeg را بررسی کنید"
                ),
                retryable=False,
            )
        if voice_result.ok:
            return DeliveryResult.success([*sent_ids, *voice_result.external_message_ids])
        if not sent_ids:
            return voice_result
        return DeliveryResult(
            ok=False,
            external_message_ids=sent_ids,
            error_code=self._code("voice_partial"),
            safe_error_message=(
                f"پست اصلی ارسال شد، اما وویس در {self.service_label} ارسال نشد؛ "
                "برای جلوگیری از تکرار، ارسال خودکار دوباره انجام نمی‌شود"
            ),
            retryable=False,
        )

    def validate(self, bundle: PostBundle, destination: str) -> DeliveryResult | None:
        if len(bundle.caption_snapshot) > self.message_limit:
            return DeliveryResult.failure(
                code=self._code("caption_too_long"),
                message=(
                    f"متن برای {self.service_label} باید حداکثر "
                    f"{self._persian_number(self.message_limit)} نویسه باشد"
                ),
                retryable=False,
            )
        normalized = destination.strip()
        if not (
            re.fullmatch(r"@[A-Za-z0-9_]{5,32}", normalized)
            or re.fullmatch(r"-100\d{6,16}", normalized)
        ):
            return DeliveryResult.failure(
                code=self._code("destination_invalid"),
                message=(f"مقصد {self.service_label} باید نام کانال با @ یا شناسه عددی -100 باشد"),
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

    def _send_media(
        self,
        *,
        method: str,
        field_name: str,
        path: Path,
        mime_type: str,
        destination: str,
        caption: str | None = None,
    ) -> DeliveryResult:
        data = self._message_data(destination)
        if caption is not None:
            data["caption"] = caption
        try:
            response = self._client.post(
                f"{self._base_url}/{method}",
                data=data,
                files={field_name: (path.name, path.read_bytes(), mime_type)},
            )
        except (httpx.TimeoutException, httpx.NetworkError):
            return DeliveryResult.failure(
                code=self._code("network_error"),
                message=f"ارتباط با {self.service_label} موقتاً برقرار نشد",
                retryable=True,
            )
        payload = self._payload(response)
        if not payload.get("ok"):
            return self._api_failure(response.status_code, payload)
        message_id = payload.get("result", {}).get("message_id")
        if not isinstance(message_id, int):
            return DeliveryResult.failure(
                code=self._code("invalid_response"),
                message=f"پاسخ {self.service_label} کامل نبود؛ ارسال دوباره بررسی می‌شود",
                retryable=True,
            )
        return DeliveryResult.success([str(message_id)])

    def _send_text(self, destination: str, text: str) -> DeliveryResult:
        try:
            response = self._client.post(
                f"{self._base_url}/sendMessage",
                data={**self._message_data(destination), "text": text},
            )
        except (httpx.TimeoutException, httpx.NetworkError):
            return DeliveryResult.failure(
                code=self._code("network_error"),
                message=f"ارتباط با {self.service_label} موقتاً برقرار نشد",
                retryable=True,
            )
        payload = self._payload(response)
        if not payload.get("ok"):
            return self._api_failure(response.status_code, payload)
        message_id = payload.get("result", {}).get("message_id")
        if not isinstance(message_id, int):
            return DeliveryResult.failure(
                code=self._code("invalid_response"),
                message=f"پاسخ {self.service_label} کامل نبود؛ ارسال دوباره بررسی می‌شود",
                retryable=True,
            )
        return DeliveryResult.success([str(message_id)])

    @staticmethod
    def _payload(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _api_failure(self, status_code: int, payload: dict[str, Any]) -> DeliveryResult:
        error_code = payload.get("error_code", status_code)
        if error_code == 429:
            retry_after = payload.get("parameters", {}).get("retry_after", 1)
            persian_delay = self._persian_number(retry_after)
            return DeliveryResult.failure(
                code=self._code("rate_limited"),
                message=(
                    f"{self.service_label} محدودیت موقت اعمال کرد؛ تلاش بعدی پس از "
                    f"{persian_delay} ثانیه"
                ),
                retryable=True,
            )
        if error_code == 403:
            return DeliveryResult.failure(
                code=self._code("forbidden"),
                message=(
                    f"ربات {self.service_label} اجازه ارسال به این کانال را ندارد؛ "
                    "دسترسی مدیر را بررسی کنید"
                ),
                retryable=False,
            )
        if error_code == 401:
            return DeliveryResult.failure(
                code=self._code("unauthorized"),
                message=f"توکن ربات {self.service_label} معتبر نیست",
                retryable=False,
            )
        if status_code >= 500:
            return DeliveryResult.failure(
                code=self._code("server_error"),
                message=f"سرویس {self.service_label} موقتاً در دسترس نیست",
                retryable=True,
            )
        return DeliveryResult.failure(
            code=self._code("bad_request"),
            message=f"مقصد یا اطلاعات ارسال {self.service_label} معتبر نیست",
            retryable=False,
        )

    def _code(self, suffix: str) -> str:
        return f"{self.platform}_{suffix}"

    def _message_data(self, destination: str) -> dict[str, str | int]:
        data: dict[str, str | int] = {"chat_id": destination}
        if self.message_thread_id is not None:
            data["message_thread_id"] = self.message_thread_id
        return data

    @staticmethod
    def _persian_number(value: object) -> str:
        return str(value).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
