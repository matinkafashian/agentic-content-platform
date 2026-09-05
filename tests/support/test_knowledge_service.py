from app.support.repository import SupportKnowledgeRepository
from app.support.schemas import SupportKnowledgeInput
from app.support.service import SupportKnowledgeService, split_knowledge


class StubEmbeddingProvider:
    embedding_model = "embedding-test"

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed(self, texts: list[str]) -> list[tuple[float, ...]]:
        self.calls.append(texts)
        return [(float(index), 1.0) for index, _text in enumerate(texts, start=1)]


def test_support_knowledge_is_a_single_editable_record(db_session):
    service = SupportKnowledgeService(SupportKnowledgeRepository(db_session))

    initial = service.get_or_create()
    updated = service.update(
        SupportKnowledgeInput(content="  ارسال به سراسر ایران انجام می‌شود.  ")
    )

    assert initial.id == 1
    assert updated.id == 1
    assert updated.content == "ارسال به سراسر ایران انجام می‌شود."
    assert service.get_or_create().id == 1


def test_knowledge_index_is_persisted_and_reused_until_content_changes(db_session):
    service = SupportKnowledgeService(SupportKnowledgeRepository(db_session))
    knowledge = service.update(
        SupportKnowledgeInput(content="ارسال به سراسر ایران انجام می‌شود.\n\nآدرس دفتر تهران است.")
    )
    provider = StubEmbeddingProvider()

    indexed = service.ensure_index(knowledge, provider)
    reused = service.ensure_index(indexed, provider)

    assert len(indexed.index_chunks) == 2
    assert reused.indexed_content_hash
    assert reused.embedding_model == "embedding-test"
    assert len(provider.calls) == 1
    assert service.indexed_chunks(reused)[0].source_ref == "knowledge:1"

    updated = service.update(SupportKnowledgeInput(content="متن تازه"))
    assert updated.index_chunks == []
    assert updated.indexed_content_hash == ""


def test_split_knowledge_keeps_each_line_as_a_focused_fact():
    chunks = split_knowledge("خط اول\nخط دوم\n\nبخش مستقل")

    assert chunks == ["خط اول", "خط دوم", "بخش مستقل"]


def test_split_knowledge_keeps_a_heading_with_its_related_facts():
    chunks = split_knowledge(
        "مراحل تولید\n"
        "مرحله اول، برش CNC انجام می‌شود.\n"
        "مرحله دوم، چسب‌زنی انجام می‌شود.\n"
        "مرحله سوم، قطعه در دستگاه وکیوم قرار می‌گیرد."
    )

    assert chunks == [
        "مراحل تولید\n"
        "مرحله اول، برش CNC انجام می‌شود.\n"
        "مرحله دوم، چسب‌زنی انجام می‌شود.\n"
        "مرحله سوم، قطعه در دستگاه وکیوم قرار می‌گیرد."
    ]
