from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class SupportChatType(StrEnum):
    PRIVATE = "private"
    GROUP = "group"
    CHANNEL = "channel"


class SupportContentType(StrEnum):
    TEXT = "text"
    IMAGE = "image"
    VOICE = "voice"
    FILE = "file"


class SupportDecision(StrEnum):
    GROUNDED = "grounded"
    GENERAL_GUIDANCE = "general_guidance"
    CLARIFICATION = "clarification"
    HANDOFF = "handoff"
    IRRELEVANT = "irrelevant"
    UNSUPPORTED = "unsupported"
    IGNORED = "ignored"


@dataclass(frozen=True, slots=True)
class IncomingSupportMessage:
    platform: str
    chat_id: str
    user_id: str
    message_id: str
    chat_type: SupportChatType
    content_type: SupportContentType
    text: str = ""


@dataclass(frozen=True, slots=True)
class SupportContext:
    business_name: str
    knowledge_text: str
    tone_guidelines: str = ""
    support_handle: str = ""
    support_phone: str = ""
    product_facts: tuple[str, ...] = ()
    knowledge_chunks: tuple["IndexedKnowledgeChunk", ...] = ()


@dataclass(frozen=True, slots=True)
class IndexedKnowledgeChunk:
    source_ref: str
    text: str
    embedding: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class SupportReply:
    decision: SupportDecision
    text: str | None
    source_refs: tuple[str, ...] = ()
    needs_admin: bool = False
    confidence: float = 1.0


class SupportReplyProvider(Protocol):
    def answer(self, question: str, context: SupportContext) -> SupportReply: ...


class SupportEngine:
    def __init__(self, provider: SupportReplyProvider, *, max_reply_chars: int = 2_000) -> None:
        self.provider = provider
        self.max_reply_chars = max_reply_chars

    def respond(
        self,
        message: IncomingSupportMessage,
        context: SupportContext,
    ) -> SupportReply:
        if message.chat_type is not SupportChatType.PRIVATE:
            return SupportReply(SupportDecision.IGNORED, None)

        question = message.text.strip()
        if message.content_type is not SupportContentType.TEXT or not question:
            return SupportReply(
                SupportDecision.UNSUPPORTED,
                "لطفاً سؤال خود را به‌صورت پیام متنی ارسال کنید.",
            )

        if not context.knowledge_text.strip():
            return self._handoff(context)

        proposed = self.provider.answer(question, context)
        if proposed.decision is SupportDecision.IRRELEVANT:
            return SupportReply(
                SupportDecision.IRRELEVANT,
                (
                    f"من برای پاسخ‌گویی درباره محصولات و خدمات {context.business_name} "
                    "در خدمت شما هستم."
                ),
            )

        if proposed.decision is SupportDecision.CLARIFICATION:
            return SupportReply(
                SupportDecision.CLARIFICATION,
                (
                    "برای راهنمایی دقیق‌تر، لطفاً نوع محصول یا کاربرد مدنظر، "
                    "سبک، ابعاد و رنگ دلخواه را بفرمایید."
                ),
            )

        if (
            proposed.decision is SupportDecision.GROUNDED
            and proposed.confidence < 0.9
        ):
            return self._handoff(context)

        if proposed.decision is SupportDecision.GROUNDED and not proposed.source_refs:
            return self._handoff(context)

        text = (proposed.text or "").strip()
        if not text:
            return self._handoff(context)

        source_refs = tuple(dict.fromkeys(proposed.source_refs))
        return SupportReply(
            decision=proposed.decision,
            text=text[: self.max_reply_chars],
            source_refs=source_refs,
            needs_admin=(
                proposed.needs_admin or proposed.decision is SupportDecision.HANDOFF
            ),
            confidence=proposed.confidence,
        )

    @staticmethod
    def _handoff(context: SupportContext) -> SupportReply:
        contacts = [value for value in (context.support_handle, context.support_phone) if value]
        contact = f" از طریق {' یا '.join(contacts)}" if contacts else ""
        return SupportReply(
            SupportDecision.HANDOFF,
            f"برای پاسخ دقیق، لطفاً با پشتیبانی{contact} در ارتباط باشید.",
            needs_admin=True,
        )
