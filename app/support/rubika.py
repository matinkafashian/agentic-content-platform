import asyncio
from typing import Any

import httpx

from app.support.telegram import TelegramSupportBot, TelegramSupportError


class RubikaSupportBot(TelegramSupportBot):
    """Receive private customer messages through Rubika's official Bot API."""

    platform = "rubika"
    api_base_url = "https://botapi.rubika.ir"

    def __init__(self, *args, poll_interval_seconds: float = 5.0, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.poll_interval_seconds = poll_interval_seconds
        self._offset_id: str | None = None

    @classmethod
    def _build_base_url(cls, bot_token: str) -> str:
        return f"{cls.api_base_url}/v3/{bot_token}"

    def poll_once(self) -> int:
        updates, next_offset_id = self._get_rubika_updates()
        for update in updates:
            normalized = self._normalize_update(update, next_offset_id=next_offset_id)
            if normalized is None:
                continue
            payload, update_key = normalized
            self._handle_update(payload, update_id=update_key)
        if next_offset_id:
            self._offset_id = next_offset_id
        return len(updates)

    async def run_forever(self) -> None:
        while True:
            try:
                await asyncio.to_thread(self.poll_once)
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(self.retry_seconds)
            else:
                await asyncio.sleep(self.poll_interval_seconds)

    def _get_rubika_updates(self) -> tuple[list[dict[str, Any]], str | None]:
        payload: dict[str, Any] = {"limit": 100}
        if self._offset_id:
            payload["offset_id"] = self._offset_id
        body = self._post("getUpdates", payload)
        data = self._data(body)
        updates = data.get("updates", [])
        next_offset_id = data.get("next_offset_id")
        if not isinstance(updates, list):
            raise TelegramSupportError("فهرست پیام‌های روبیکا معتبر نبود.")
        return (
            [item for item in updates if isinstance(item, dict)],
            str(next_offset_id) if next_offset_id else None,
        )

    def _normalize_update(
        self,
        update: dict[str, Any],
        *,
        next_offset_id: str | None,
    ) -> tuple[dict[str, Any], str] | None:
        update_type = update.get("type")
        chat_id = str(update.get("chat_id", "")).strip()
        if not chat_id or update_type not in {"NewMessage", "StartedBot"}:
            return None
        chat_type = self._rubika_chat_type(chat_id)
        if update_type == "StartedBot":
            message_id = f"started:{next_offset_id or chat_id}"
            message = {"message_id": message_id, "text": "/start"}
            sender_id = chat_id
        else:
            message = update.get("new_message")
            if not isinstance(message, dict):
                return None
            message_id = str(message.get("message_id", "")).strip()
            sender_id = str(message.get("sender_id", "")).strip()
            if not message_id:
                return None
        normalized_message: dict[str, Any] = {
            "message_id": message_id,
            "chat": {"id": chat_id, "type": chat_type},
            "from": {"id": sender_id},
        }
        text = message.get("text")
        if isinstance(text, str) and text.strip():
            normalized_message["text"] = text
        elif message.get("file"):
            normalized_message["document"] = message["file"]
        else:
            normalized_message["document"] = {}
        return (
            {"message": normalized_message},
            f"{chat_id}:{message_id}",
        )

    def _rubika_chat_type(self, chat_id: str) -> str:
        body = self._post("getChat", {"chat_id": chat_id})
        chat = self._data(body).get("chat", self._data(body))
        chat_type = chat.get("chat_type") if isinstance(chat, dict) else None
        return {
            "User": "private",
            "Channel": "channel",
            "Group": "group",
        }.get(str(chat_type), "group")

    def _send_text(self, chat_id: str, text: str, idempotency_key: str) -> None:
        del idempotency_key
        self._post("sendMessage", {"chat_id": chat_id, "text": text})

    def _post(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.post(f"{self._base_url}/{method}", json=payload)
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise TelegramSupportError("ارتباط ربات پاسخ‌گوی روبیکا برقرار نشد.") from exc
        if not isinstance(body, dict) or not self._is_success(body):
            raise TelegramSupportError("روبیکا درخواست ربات پاسخ‌گو را نپذیرفت.")
        return body

    @staticmethod
    def _data(body: dict[str, Any]) -> dict[str, Any]:
        data = body.get("data", body)
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _is_success(body: dict[str, Any]) -> bool:
        status = body.get("status")
        if isinstance(status, str):
            return status.upper() == "OK"
        if "ok" in body:
            return body.get("ok") is True
        return bool(body)
