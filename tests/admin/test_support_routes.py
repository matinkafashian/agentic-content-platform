from app.support.engine import SupportDecision, SupportReply
from app.support.models import SupportKnowledge


class StubSupportProvider:
    embedding_model = "embedding-test"

    def embed(self, texts: list[str]) -> list[tuple[float, ...]]:
        return [(1.0, 0.0) for _text in texts]

    def answer(self, question, context):
        assert question == "ارسال شهرستان دارید؟"
        assert context.knowledge_chunks
        return SupportReply(
            SupportDecision.GROUNDED,
            "بله، ارسال به سراسر ایران انجام می‌شود.",
            source_refs=("knowledge:1",),
        )


def test_support_page_requires_login(client):
    response = client.get("/admin/support", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_admin_can_save_support_knowledge(authenticated_client, csrf_token):
    page = authenticated_client.get("/admin/support")

    assert page.status_code == 200
    assert "اطلاعات کسب‌وکار را یک‌جا وارد کنید" in page.text

    response = authenticated_client.post(
        "/admin/support",
        data={
            "csrf_token": csrf_token,
            "content": "آدرس: تهران\nشماره تماس: ۰۲۱۱۲۳۴۵۶۷۸",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/support?saved=1"
    with authenticated_client.app.state.session_factory() as session:
        knowledge = session.get(SupportKnowledge, 1)
        assert knowledge is not None
        assert "شماره تماس" in knowledge.content


def test_support_navigation_is_visible(authenticated_client):
    page = authenticated_client.get("/admin")

    assert 'href="/admin/support"' in page.text
    assert "دانش پاسخ‌گویی" in page.text


def test_admin_can_preview_a_grounded_support_answer(authenticated_client, csrf_token):
    authenticated_client.app.state.support_provider = StubSupportProvider()
    with authenticated_client.app.state.session_factory() as session:
        session.add(
            SupportKnowledge(id=1, content="ارسال به سراسر ایران انجام می‌شود.")
        )
        session.commit()

    response = authenticated_client.post(
        "/admin/support/test",
        data={
            "csrf_token": csrf_token,
            "question": "ارسال شهرستان دارید؟",
        },
    )

    assert response.status_code == 200
    assert "بله، ارسال به سراسر ایران انجام می‌شود." in response.text
    assert "پاسخ ربات" in response.text
    assert "data-persistent" in response.text
    assert "knowledge:1" not in response.text
    assert "بخش‌های استفاده‌شده از مرجع" in response.text


def test_support_preview_explains_when_openai_is_unavailable(
    authenticated_client, csrf_token
):
    response = authenticated_client.post(
        "/admin/support/test",
        data={"csrf_token": csrf_token, "question": "سؤال"},
    )

    assert response.status_code == 503
    assert "پاسخ‌گوی هوشمند فعال نیست" in response.text
