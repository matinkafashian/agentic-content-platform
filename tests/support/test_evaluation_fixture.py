import json
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
ACTIVE_KNOWLEDGE = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "knowledge"
    / "hayka_knowledge_active_fa.txt"
)


def test_active_hayka_knowledge_contains_required_operational_sections():
    knowledge = ACTIVE_KNOWLEDGE.read_text(encoding="utf-8")

    assert "اطلاعات تماس" in knowledge
    assert "محصولات اصلی هایکا" in knowledge
    assert "پاسخ‌های پرتکرار" in knowledge
    assert "+989183962948" in knowledge
    assert "آزمایشی" not in knowledge


def test_support_evaluation_set_has_twenty_unique_questions_and_all_decisions():
    questions = json.loads(
        (FIXTURES / "support_questions_fa.json").read_text(encoding="utf-8")
    )

    assert len(questions) == 20
    assert len({item["id"] for item in questions}) == 20
    assert len({item["question"] for item in questions}) == 20
    assert {item["expected_decision"] for item in questions} == {
        "grounded",
        "general_guidance",
        "clarification",
        "handoff",
        "irrelevant",
    }
    assert all(item["expected_fact"].strip() for item in questions)
