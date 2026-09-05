import json

import httpx
import pytest

from app.support.engine import IndexedKnowledgeChunk, SupportContext, SupportDecision
from app.support.openai_provider import OpenAISupportProvider, SupportProviderError


def _response_payload(content: dict[str, object]) -> dict[str, object]:
    return {
        "id": "resp_support_test",
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(content, ensure_ascii=False),
                    }
                ],
            }
        ],
    }


def test_hybrid_provider_embeds_retrieves_and_returns_structured_grounded_reply():
    captured: list[tuple[str, dict[str, object]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        captured.append((request.url.path, payload))
        if request.url.path == "/v1/embeddings":
            return httpx.Response(
                200,
                json={"data": [{"index": 0, "embedding": [1.0, 0.0]}]},
                request=request,
            )
        return httpx.Response(
            200,
            json=_response_payload(
                {
                    "decision": "grounded",
                    "answer": "بله، ارسال به سراسر ایران انجام می‌شود.",
                    "source_refs": ["knowledge:1"],
                    "needs_admin": False,
                    "confidence": 0.96,
                }
            ),
            request=request,
        )

    provider = OpenAISupportProvider(
        api_key="sk-test-not-real",
        model="gpt-test",
        embedding_model="embedding-test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    context = SupportContext(
        business_name="هایکا",
        knowledge_text="ارسال به سراسر ایران انجام می‌شود.",
        support_phone="+989183962948",
        knowledge_chunks=(
            IndexedKnowledgeChunk(
                "knowledge:1", "ارسال به سراسر ایران انجام می‌شود.", (1.0, 0.0)
            ),
            IndexedKnowledgeChunk("knowledge:2", "نشانی دفتر تهران است.", (0.0, 1.0)),
        ),
    )

    reply = provider.answer("ارسال شهرستان دارید؟", context)

    assert reply.decision is SupportDecision.GROUNDED
    assert reply.source_refs == ("knowledge:1",)
    assert [path for path, _payload in captured] == ["/v1/embeddings", "/v1/responses"]
    response_input = json.loads(captured[1][1]["input"])
    assert response_input["retrieved_sources"] == [
        {
            "source_ref": "knowledge:1",
            "text": "ارسال به سراسر ایران انجام می‌شود.",
        }
    ]
    assert response_input["support_phone"] == "+989183962948"
    assert captured[1][1]["store"] is False
    assert captured[1][1]["text"]["format"]["strict"] is True
    assert "پاسخ grounded است" in captured[1][1]["instructions"]
    assert "موجودی فعلی" in captured[1][1]["instructions"]
    assert "نگهداری یا تمیزکردن" in captured[1][1]["instructions"]


def test_provider_removes_source_references_that_were_not_supplied():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/embeddings":
            return httpx.Response(
                200,
                json={"data": [{"index": 0, "embedding": [1.0]}]},
                request=request,
            )
        return httpx.Response(
            200,
            json=_response_payload(
                {
                    "decision": "grounded",
                    "answer": "پاسخ",
                    "source_refs": ["knowledge:999"],
                    "needs_admin": False,
                    "confidence": 0.96,
                }
            ),
            request=request,
        )

    provider = OpenAISupportProvider(
        api_key="sk-test-not-real",
        model="gpt-test",
        embedding_model="embedding-test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    reply = provider.answer(
        "سؤال",
        SupportContext(
            business_name="هایکا",
            knowledge_text="دانش",
            knowledge_chunks=(IndexedKnowledgeChunk("knowledge:1", "دانش", (1.0,)),),
        ),
    )

    assert reply.source_refs == ()


def test_provider_does_not_show_sources_for_general_guidance():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/embeddings":
            return httpx.Response(
                200,
                json={"data": [{"index": 0, "embedding": [1.0]}]},
                request=request,
            )
        return httpx.Response(
            200,
            json=_response_payload(
                {
                    "decision": "general_guidance",
                    "answer": "این یک راهنمای عمومی است.",
                    "source_refs": ["knowledge:1"],
                    "needs_admin": False,
                    "confidence": 0.96,
                }
            ),
            request=request,
        )

    provider = OpenAISupportProvider(
        api_key="sk-test-not-real",
        model="gpt-test",
        embedding_model="embedding-test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    reply = provider.answer(
        "راهنمایی عمومی",
        SupportContext(
            business_name="هایکا",
            knowledge_text="دانش",
            knowledge_chunks=(IndexedKnowledgeChunk("knowledge:1", "دانش", (1.0,)),),
        ),
    )

    assert reply.decision is SupportDecision.GENERAL_GUIDANCE
    assert reply.source_refs == ()


def test_provider_returns_safe_error_without_leaking_api_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"error": {"message": "sk-sensitive"}},
            request=request,
        )

    provider = OpenAISupportProvider(
        api_key="sk-sensitive",
        model="gpt-test",
        embedding_model="embedding-test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(SupportProviderError) as exc_info:
        provider.embed(["متن"])

    assert "sk-sensitive" not in str(exc_info.value)
    assert "دسترسی OpenAI" in str(exc_info.value)
