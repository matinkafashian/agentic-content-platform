import httpx
from sqlalchemy import func, select

from app.core.database import Base, build_engine, build_session_factory
from app.support.engine import SupportContext, SupportDecision, SupportReply
from app.support.models import SupportInteraction, SupportKnowledge
from app.support.telegram import TelegramSupportBot


class StubProvider:
    embedding_model = "embedding-test"

    def __init__(self) -> None:
        self.questions: list[str] = []

    def embed(self, texts: list[str]) -> list[tuple[float, ...]]:
        return [(1.0, float(index)) for index, _ in enumerate(texts, start=1)]

    def answer(self, question: str, context: SupportContext) -> SupportReply:
        self.questions.append(question)
        return SupportReply(
            SupportDecision.GROUNDED,
            "بله، ارسال به سراسر ایران انجام می‌شود.",
            source_refs=(context.knowledge_chunks[0].source_ref,),
        )


def _update(
    *,
    update_id: int = 101,
    message_id: int = 7,
    chat_id: int = 9001,
    chat_type: str = "private",
    content: dict[str, object] | None = None,
) -> dict[str, object]:
    message: dict[str, object] = {
        "message_id": message_id,
        "chat": {"id": chat_id, "type": chat_type},
        "from": {"id": 42},
    }
    message.update(content or {"text": "ارسال شهرستان دارید؟"})
    return {"update_id": update_id, "message": message}


def _bot(tmp_path, update: dict[str, object]):
    engine = build_engine(f"sqlite:///{tmp_path / 'telegram-support.db'}")
    Base.metadata.create_all(engine)
    session_factory = build_session_factory(engine)
    with session_factory() as db:
        db.add(SupportKnowledge(id=1, content="ارسال به سراسر ایران انجام می‌شود."))
        db.commit()

    sent_payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/getUpdates"):
            return httpx.Response(200, json={"ok": True, "result": [update]})
        if request.url.path.endswith("/sendMessage"):
            sent_payloads.append(__import__("json").loads(request.content))
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 99}})
        raise AssertionError(f"Unexpected Telegram method: {request.url.path}")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = StubProvider()
    bot = TelegramSupportBot(
        bot_token="test-token",
        session_factory=session_factory,
        provider=provider,
        poll_timeout_seconds=1,
        client=client,
    )
    return bot, provider, session_factory, sent_payloads, engine, client


def test_private_text_is_answered_and_logged_once(tmp_path):
    bot, provider, session_factory, sent, engine, client = _bot(tmp_path, _update())
    try:
        assert bot.poll_once() == 1
        assert bot.poll_once() == 1

        assert provider.questions == ["ارسال شهرستان دارید؟"]
        assert sent == [
            {
                "chat_id": "9001",
                "text": "بله، ارسال به سراسر ایران انجام می‌شود.",
            }
        ]
        with session_factory() as db:
            interaction = db.scalar(select(SupportInteraction))
            assert interaction is not None
            assert interaction.external_update_id == "101"
            assert interaction.external_message_id == "7"
            assert interaction.status == "answered"
            assert interaction.decision == "grounded"
    finally:
        client.close()
        engine.dispose()


def test_same_message_id_in_two_chats_is_not_treated_as_duplicate(tmp_path):
    first = _update(update_id=201, message_id=1, chat_id=7001)
    second = _update(update_id=202, message_id=1, chat_id=7002)
    updates = [first, second]
    bot, provider, session_factory, sent, engine, client = _bot(tmp_path, first)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/getUpdates"):
            return httpx.Response(200, json={"ok": True, "result": updates})
        if request.url.path.endswith("/sendMessage"):
            sent.append(__import__("json").loads(request.content))
            return httpx.Response(200, json={"ok": True, "result": {}})
        raise AssertionError(request.url.path)

    client.close()
    replacement = httpx.Client(transport=httpx.MockTransport(handler))
    bot._client = replacement
    try:
        bot.poll_once()
        assert len(provider.questions) == 2
        assert [payload["chat_id"] for payload in sent] == ["7001", "7002"]
        with session_factory() as db:
            assert db.scalar(select(func.count(SupportInteraction.id))) == 2
    finally:
        replacement.close()
        engine.dispose()


def test_group_message_is_ignored(tmp_path):
    bot, provider, session_factory, sent, engine, client = _bot(
        tmp_path,
        _update(chat_type="group"),
    )
    try:
        bot.poll_once()
        assert provider.questions == []
        assert sent == []
        with session_factory() as db:
            assert db.scalar(select(func.count(SupportInteraction.id))) == 0
    finally:
        client.close()
        engine.dispose()


def test_private_voice_gets_text_only_instruction(tmp_path):
    bot, provider, session_factory, sent, engine, client = _bot(
        tmp_path,
        _update(content={"voice": {"file_id": "voice-1"}}),
    )
    try:
        bot.poll_once()
        assert provider.questions == []
        assert len(sent) == 1
        assert "پیام متنی" in str(sent[0]["text"])
        with session_factory() as db:
            interaction = db.scalar(select(SupportInteraction))
            assert interaction is not None
            assert interaction.decision == "unsupported"
            assert interaction.status == "answered"
    finally:
        client.close()
        engine.dispose()


def test_start_command_returns_welcome_without_calling_openai(tmp_path):
    bot, provider, session_factory, sent, engine, client = _bot(
        tmp_path,
        _update(content={"text": "/start support"}),
    )
    try:
        bot.poll_once()
        assert provider.questions == []
        assert len(sent) == 1
        assert "پاسخ‌گوی هایکا" in str(sent[0]["text"])
        assert "پیام متنی" in str(sent[0]["text"])
        with session_factory() as db:
            interaction = db.scalar(select(SupportInteraction))
            assert interaction is not None
            assert interaction.decision == "general_guidance"
            assert interaction.status == "answered"
    finally:
        client.close()
        engine.dispose()
