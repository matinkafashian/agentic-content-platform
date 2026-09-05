import json

import httpx
from sqlalchemy import func, select

from app.core.database import Base, build_engine, build_session_factory
from app.support.models import SupportInteraction, SupportKnowledge
from app.support.rubika import RubikaSupportBot
from tests.support.test_telegram_bot import StubProvider


def _create_bot(tmp_path, updates, chat_type="User"):
    engine = build_engine(f"sqlite:///{tmp_path / 'rubika-support.db'}")
    Base.metadata.create_all(engine)
    session_factory = build_session_factory(engine)
    with session_factory() as db:
        db.add(SupportKnowledge(id=1, content="ارسال به سراسر ایران انجام می‌شود."))
        db.commit()
    requests: list[tuple[str, dict[str, object]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        method = request.url.path.rsplit("/", 1)[-1]
        requests.append((method, json.loads(request.content)))
        if method == "getUpdates":
            return httpx.Response(
                200,
                json={
                    "status": "OK",
                    "data": {"updates": updates, "next_offset_id": "next-2"},
                },
            )
        if method == "getChat":
            return httpx.Response(
                200,
                json={"status": "OK", "data": {"chat": {"chat_type": chat_type}}},
            )
        if method == "sendMessage":
            return httpx.Response(
                200,
                json={"status": "OK", "data": {"message_id": "reply-1"}},
            )
        raise AssertionError(method)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = StubProvider()
    bot = RubikaSupportBot(
        bot_token="rubika-token",
        session_factory=session_factory,
        provider=provider,
        poll_timeout_seconds=1,
        poll_interval_seconds=1,
        client=client,
    )
    return bot, provider, requests, session_factory, engine, client


def test_rubika_private_question_uses_shared_support_engine(tmp_path):
    updates = [
        {
            "type": "NewMessage",
            "chat_id": "b-chat-1",
            "new_message": {
                "message_id": "message-1",
                "text": "ارسال شهرستان دارید؟",
                "sender_type": "User",
                "sender_id": "u-user-1",
            },
        }
    ]
    bot, provider, requests, session_factory, engine, client = _create_bot(
        tmp_path, updates
    )
    try:
        bot.poll_once()
        assert provider.questions == ["ارسال شهرستان دارید؟"]
        assert [method for method, _ in requests] == [
            "getUpdates",
            "getChat",
            "sendMessage",
        ]
        with session_factory() as db:
            interaction = db.scalar(select(SupportInteraction))
            assert interaction is not None
            assert interaction.platform == "rubika"
            assert interaction.external_update_id == "b-chat-1:message-1"
            assert interaction.status == "answered"
    finally:
        client.close()
        engine.dispose()


def test_rubika_group_message_is_ignored(tmp_path):
    updates = [
        {
            "type": "NewMessage",
            "chat_id": "g-chat-1",
            "new_message": {
                "message_id": "message-2",
                "text": "پیام گروه",
                "sender_type": "User",
                "sender_id": "u-user-1",
            },
        }
    ]
    bot, provider, requests, session_factory, engine, client = _create_bot(
        tmp_path, updates, chat_type="Group"
    )
    try:
        bot.poll_once()
        assert provider.questions == []
        assert [method for method, _ in requests] == ["getUpdates", "getChat"]
        with session_factory() as db:
            assert db.scalar(select(func.count(SupportInteraction.id))) == 0
    finally:
        client.close()
        engine.dispose()
