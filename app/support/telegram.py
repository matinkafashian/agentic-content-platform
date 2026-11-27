import asyncio
import logging
from typing import Any, Protocol

import httpx
from sqlalchemy.orm import Session, sessionmaker

from app.support.engine import (
    IncomingSupportMessage,
    SupportChatType,
    SupportContentType,
    SupportContext,
    SupportDecision,
    SupportEngine,
    SupportReply,
    SupportReplyProvider,
)
from app.support.models import SupportInteraction
from app.support.openai_provider import SupportProviderError
from app.support.repository import SupportInteractionRepository, SupportKnowledgeRepository
from app.support.service import (
    KnowledgeEmbeddingProvider,
    SupportKnowledgeService,
    build_support_context,
)

logger = logging.getLogger(__name__)


class TelegramSupportError(RuntimeError):
    """A safe Telegram support-bot transport failure."""


class TelegramSupportProvider(SupportReplyProvider, KnowledgeEmbeddingProvider, Protocol):
    """The shared support provider capabilities needed by the Telegram worker."""


class TelegramSupportBot:
    platform = "telegram"
    api_base_url = "https://api.telegram.org"

    def __init__(
        self,
        *,
        bot_token: str,
        session_factory: sessionmaker[Session],
        provider: TelegramSupportProvider,
        poll_timeout_seconds: int = 20,
        retry_seconds: float = 3.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.provider = provider
        self.poll_timeout_seconds = poll_timeout_seconds
        self.retry_seconds = retry_seconds
        self._base_url = self._build_base_url(bot_token)
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(float(poll_timeout_seconds) + 10.0)
        )
        self._offset: int | None = None

    def poll_once(self) -> int:
        updates = self._get_updates()
        for update in updates:
            update_id = update.get("update_id")
            if not isinstance(update_id, int):
                continue
            self._handle_update(update, update_id=update_id)
            self._offset = update_id + 1
        return len(updates)

    async def run_forever(self) -> None:
        while True:
            try:
                await asyncio.to_thread(self.poll_once)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("telegram support polling iteration failed")
                await asyncio.sleep(self.retry_seconds)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _get_updates(self) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "timeout": self.poll_timeout_seconds,
            "allowed_updates": ["message"],
        }
        if self._offset is not None:
            payload["offset"] = self._offset
        try:
            response = self._client.post(f"{self._base_url}/getUpdates", json=payload)
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise TelegramSupportError("دریافت پیام از تلگرام موقتاً انجام نشد.") from exc
        if not isinstance(body, dict) or body.get("ok") is not True:
            raise TelegramSupportError("پاسخ دریافت پیام تلگرام معتبر نبود.")
        result = body.get("result")
        if not isinstance(result, list):
            raise TelegramSupportError("فهرست پیام‌های تلگرام معتبر نبود.")
        return [item for item in result if isinstance(item, dict)]

    def _handle_update(self, update: dict[str, Any], *, update_id: int | str) -> None:
        message = update.get("message")
        if not isinstance(message, dict):
            return
        chat = message.get("chat")
        sender = message.get("from")
        message_id = message.get("message_id")
        if (
            not isinstance(chat, dict)
            or not isinstance(message_id, (int, str))
            or not str(message_id).strip()
        ):
            return

        chat_type = self._chat_type(chat.get("type"))
        if chat_type is not SupportChatType.PRIVATE:
            return
        chat_id = str(chat.get("id", ""))
        user_id = str(sender.get("id", "")) if isinstance(sender, dict) else ""
        external_update_id = str(update_id)
        external_message_id = str(message_id)

        with self.session_factory() as db:
            interactions = SupportInteractionRepository(db)
            if interactions.get_by_external_update(self.platform, external_update_id):
                return
            incoming = self._incoming_message(
                message,
                chat_id=chat_id,
                user_id=user_id,
                external_message_id=external_message_id,
            )
            interaction = SupportInteraction(
                platform=self.platform,
                external_update_id=external_update_id,
                external_message_id=external_message_id,
                chat_id=chat_id,
                user_id=user_id,
                question=incoming.text,
            )
            interactions.add(interaction)
            interactions.commit()

            knowledge_service = SupportKnowledgeService(SupportKnowledgeRepository(db))
            knowledge = knowledge_service.get_or_create()
            context = build_support_context(db, knowledge, knowledge_service)
            try:
                if self._is_start_command(incoming):
                    reply = self._welcome_reply(context)
                elif incoming.content_type is SupportContentType.TEXT:
                    knowledge = knowledge_service.ensure_index(knowledge, self.provider)
                    context = build_support_context(db, knowledge, knowledge_service)
                    reply = SupportEngine(self.provider).respond(incoming, context)
                else:
                    reply = SupportEngine(self.provider).respond(incoming, context)
            except (SupportProviderError, ValueError):
                logger.exception("telegram support provider failed")
                reply = self._provider_fallback(context)

            try:
                if reply.text:
                    self._send_text(chat_id, reply.text, external_update_id)
                interaction.decision = reply.decision.value
                interaction.reply_text = reply.text or ""
                interaction.needs_admin = reply.needs_admin
                interaction.status = "answered"
                interactions.commit()
            except TelegramSupportError:
                interaction.decision = reply.decision.value
                interaction.reply_text = reply.text or ""
                interaction.needs_admin = True
                interaction.status = "failed"
                interactions.commit()
                raise

    def _send_text(self, chat_id: str, text: str, idempotency_key: str) -> None:
        del idempotency_key
        try:
            response = self._client.post(
                f"{self._base_url}/sendMessage",
                json={"chat_id": chat_id, "text": text},
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise TelegramSupportError("ارسال پاسخ تلگرام موقتاً انجام نشد.") from exc
        if not isinstance(body, dict) or body.get("ok") is not True:
            raise TelegramSupportError("تلگرام پاسخ ربات را نپذیرفت.")

    @classmethod
    def _build_base_url(cls, bot_token: str) -> str:
        return f"{cls.api_base_url}/bot{bot_token}"

    @staticmethod
    def _is_start_command(message: IncomingSupportMessage) -> bool:
        if message.content_type is not SupportContentType.TEXT:
            return False
        command = message.text.strip().split(maxsplit=1)[0].split("@", maxsplit=1)[0]
        return command == "/start"

    @staticmethod
    def _welcome_reply(context: SupportContext) -> SupportReply:
        return SupportReply(
            SupportDecision.GENERAL_GUIDANCE,
            (
                f"سلام، خیلی خوش اومدید به {context.business_name} 🌿\n"
                "من دستیار پاسخ‌گوی شما هستم و خوشحال می‌شم راهنمایی‌تون کنم. "
                "هر سؤالی درباره محصولات، خدمات یا ثبت سفارش دارید، "
                "به‌صورت پیام متنی همین‌جا برام بنویسید 😊"
            ),
        )

    @staticmethod
    def _chat_type(value: object) -> SupportChatType:
        if value == "private":
            return SupportChatType.PRIVATE
        if value == "channel":
            return SupportChatType.CHANNEL
        return SupportChatType.GROUP

    def _incoming_message(
        self,
        message: dict[str, Any],
        *,
        chat_id: str,
        user_id: str,
        external_message_id: str,
    ) -> IncomingSupportMessage:
        text = message.get("text")
        if isinstance(text, str):
            content_type = SupportContentType.TEXT
            clean_text = text
        elif "voice" in message:
            content_type = SupportContentType.VOICE
            clean_text = ""
        elif "photo" in message:
            content_type = SupportContentType.IMAGE
            clean_text = ""
        else:
            content_type = SupportContentType.FILE
            clean_text = ""
        return IncomingSupportMessage(
            platform=self.platform,
            chat_id=chat_id,
            user_id=user_id,
            message_id=external_message_id,
            chat_type=SupportChatType.PRIVATE,
            content_type=content_type,
            text=clean_text,
        )

    @staticmethod
    def _provider_fallback(context: SupportContext) -> SupportReply:
        contacts = [
            value for value in (context.support_handle, context.support_phone) if value
        ]
        contact = f" از طریق {' یا '.join(contacts)}" if contacts else ""
        return SupportReply(
            SupportDecision.HANDOFF,
            (
                "در حال حاضر بررسی هوشمند موقتاً در دسترس نیست. "
                f"لطفاً با پشتیبانی{contact} در ارتباط باشید."
            ),
            needs_admin=True,
        )
