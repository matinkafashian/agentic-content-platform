import re
from pathlib import Path

import httpx

from app.publishing.adapters import DeliveryResult
from app.publishing.models import PostBundle
from app.publishing.telegram import TelegramAdapter, TelegramVoicePreparer

BALE_MESSAGE_LIMIT = 4096
BALE_PHOTO_UPLOAD_LIMIT = 10 * 1024 * 1024
BALE_FILE_UPLOAD_LIMIT = 50 * 1024 * 1024


class BaleAdapter(TelegramAdapter):
    """Official Bale Bot API adapter for channel publishing."""

    platform = "bale"
    service_label = "بله"
    api_base_url = "https://tapi.bale.ai"
    caption_limit = BALE_MESSAGE_LIMIT
    message_limit = BALE_MESSAGE_LIMIT

    def __init__(
        self,
        *,
        bot_token: str,
        upload_root: Path,
        timeout_seconds: float = 30.0,
        client: httpx.Client | None = None,
        voice_preparer: TelegramVoicePreparer | None = None,
    ) -> None:
        super().__init__(
            bot_token=bot_token,
            upload_root=upload_root,
            timeout_seconds=timeout_seconds,
            client=client,
            voice_preparer=voice_preparer,
        )

    def validate(self, bundle: PostBundle, destination: str) -> DeliveryResult | None:
        if len(bundle.caption_snapshot) > self.message_limit:
            return DeliveryResult.failure(
                code=self._code("caption_too_long"),
                message="متن برای بله باید حداکثر ۴۰۹۶ نویسه باشد",
                retryable=False,
            )
        if (
            bundle.image_size_bytes is not None
            and bundle.image_size_bytes > BALE_PHOTO_UPLOAD_LIMIT
        ):
            return DeliveryResult.failure(
                code=self._code("image_too_large"),
                message="حجم تصویر برای ارسال مستقیم در بله باید حداکثر ۱۰ مگابایت باشد",
                retryable=False,
            )
        if bundle.voice_size_bytes is not None and bundle.voice_size_bytes > BALE_FILE_UPLOAD_LIMIT:
            return DeliveryResult.failure(
                code=self._code("voice_too_large"),
                message="حجم وویس برای بله باید حداکثر ۵۰ مگابایت باشد",
                retryable=False,
            )
        normalized = destination.strip()
        if not (
            re.fullmatch(r"@[A-Za-z0-9_]{5,64}", normalized)
            or re.fullmatch(r"-?\d{5,20}", normalized)
        ):
            return DeliveryResult.failure(
                code=self._code("destination_invalid"),
                message="مقصد بله باید نام کانال با @ یا شناسه عددی کانال باشد",
                retryable=False,
            )
        return None
