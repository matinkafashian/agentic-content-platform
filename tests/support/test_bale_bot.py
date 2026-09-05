import httpx
from sqlalchemy import select

from app.core.database import Base, build_engine, build_session_factory
from app.support.bale import BaleSupportBot
from app.support.models import SupportInteraction, SupportKnowledge
from tests.support.test_telegram_bot import StubProvider


def test_bale_private_question_uses_shared_support_engine(tmp_path):
    engine = build_engine(f"sqlite:///{tmp_path / 'bale-support.db'}")
    Base.metadata.create_all(engine)
    session_factory = build_session_factory(engine)
    with session_factory() as db:
        db.add(SupportKnowledge(id=1, content="ارسال به سراسر ایران انجام می‌شود."))
        db.commit()

    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/getUpdates"):
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "result": [
                        {
                            "update_id": 501,
                            "message": {
                                "message_id": 9,
                                "chat": {"id": 81, "type": "private"},
                                "from": {"id": 81},
                                "text": "ارسال شهرستان دارید؟",
                            },
                        }
                    ],
                },
            )
        if request.url.path.endswith("/sendMessage"):
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 10}})
        raise AssertionError(request.url.path)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = StubProvider()
    bot = BaleSupportBot(
        bot_token="bale-token",
        session_factory=session_factory,
        provider=provider,
        poll_timeout_seconds=1,
        client=client,
    )
    try:
        bot.poll_once()
        assert provider.questions == ["ارسال شهرستان دارید؟"]
        assert requests[0].url.host == "tapi.bale.ai"
        with session_factory() as db:
            interaction = db.scalar(select(SupportInteraction))
            assert interaction is not None
            assert interaction.platform == "bale"
            assert interaction.status == "answered"
    finally:
        client.close()
        engine.dispose()
