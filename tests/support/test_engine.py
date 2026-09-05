from app.support.engine import (
    IncomingSupportMessage,
    SupportChatType,
    SupportContentType,
    SupportContext,
    SupportDecision,
    SupportEngine,
    SupportReply,
)


class StubProvider:
    def __init__(self, reply: SupportReply) -> None:
        self.reply = reply
        self.calls: list[str] = []

    def answer(self, question: str, context: SupportContext) -> SupportReply:
        self.calls.append(question)
        return self.reply


def _message(
    *,
    chat_type: SupportChatType = SupportChatType.PRIVATE,
    content_type: SupportContentType = SupportContentType.TEXT,
    text: str = "ارسال شهرستان دارید؟",
) -> IncomingSupportMessage:
    return IncomingSupportMessage(
        platform="telegram",
        chat_id="chat-1",
        user_id="user-1",
        message_id="message-1",
        chat_type=chat_type,
        content_type=content_type,
        text=text,
    )


def _context(*, knowledge_text: str = "ارسال به سراسر ایران انجام می‌شود") -> SupportContext:
    return SupportContext(
        business_name="هایکا",
        knowledge_text=knowledge_text,
        tone_guidelines="حرفه‌ای و محترمانه",
        support_handle="@hayka_poshtibani",
        support_phone="+989183962948",
    )


def test_private_text_is_delegated_to_the_central_provider():
    provider = StubProvider(
        SupportReply(
            SupportDecision.GROUNDED,
            "بله، ارسال به سراسر ایران انجام می‌شود.",
            source_refs=("knowledge:shipping",),
        )
    )

    result = SupportEngine(provider).respond(_message(), _context())

    assert result.decision is SupportDecision.GROUNDED
    assert provider.calls == ["ارسال شهرستان دارید؟"]


def test_group_message_is_ignored_without_calling_provider():
    provider = StubProvider(SupportReply(SupportDecision.GENERAL_GUIDANCE, "پاسخ"))

    result = SupportEngine(provider).respond(
        _message(chat_type=SupportChatType.GROUP),
        _context(),
    )

    assert result == SupportReply(SupportDecision.IGNORED, None)
    assert provider.calls == []


def test_private_non_text_message_gets_a_short_instruction():
    provider = StubProvider(SupportReply(SupportDecision.GENERAL_GUIDANCE, "پاسخ"))

    result = SupportEngine(provider).respond(
        _message(content_type=SupportContentType.VOICE, text=""),
        _context(),
    )

    assert result.decision is SupportDecision.UNSUPPORTED
    assert "پیام متنی" in (result.text or "")
    assert provider.calls == []


def test_empty_knowledge_routes_customer_to_support():
    provider = StubProvider(SupportReply(SupportDecision.GENERAL_GUIDANCE, "پاسخ"))

    result = SupportEngine(provider).respond(_message(), _context(knowledge_text=""))

    assert result.decision is SupportDecision.HANDOFF
    assert result.needs_admin is True
    assert "@hayka_poshtibani" in (result.text or "")
    assert "+989183962948" in (result.text or "")
    assert provider.calls == []


def test_grounded_answer_without_a_source_is_not_allowed_through():
    provider = StubProvider(SupportReply(SupportDecision.GROUNDED, "یک ادعای بدون منبع"))

    result = SupportEngine(provider).respond(_message(), _context())

    assert result.decision is SupportDecision.HANDOFF
    assert result.needs_admin is True


def test_irrelevant_answer_uses_fixed_business_scoped_copy():
    provider = StubProvider(SupportReply(SupportDecision.IRRELEVANT, "پاسخ مدل"))

    result = SupportEngine(provider).respond(
        _message(text="پایتخت ژاپن کجاست؟"),
        _context(),
    )

    assert result.decision is SupportDecision.IRRELEVANT
    assert result.text == "من برای پاسخ‌گویی درباره محصولات و خدمات هایکا در خدمت شما هستم."


def test_clarification_uses_safe_business_scoped_copy():
    provider = StubProvider(
        SupportReply(
            SupportDecision.CLARIFICATION,
            "مثال‌های ساخته‌شده و تأییدنشده",
        )
    )

    result = SupportEngine(provider).respond(
        _message(text="برای پروژه من کدام محصول بهتر است؟"),
        _context(),
    )

    assert result.decision is SupportDecision.CLARIFICATION
    assert result.text == (
        "برای راهنمایی دقیق‌تر، لطفاً نوع محصول یا کاربرد مدنظر، "
        "سبک، ابعاد و رنگ دلخواه را بفرمایید."
    )


def test_handoff_decision_always_marks_the_reply_for_admin_attention():
    provider = StubProvider(
        SupportReply(SupportDecision.HANDOFF, "برای قیمت با پشتیبانی در ارتباط باشید.")
    )

    result = SupportEngine(provider).respond(_message(text="قیمت چقدر است؟"), _context())

    assert result.decision is SupportDecision.HANDOFF
    assert result.needs_admin is True


def test_reply_below_ninety_percent_confidence_is_handed_off():
    provider = StubProvider(
        SupportReply(
            SupportDecision.GROUNDED,
            "پاسخی که اطمینان کافی ندارد",
            source_refs=("knowledge:shipping",),
            confidence=0.89,
        )
    )

    result = SupportEngine(provider).respond(_message(), _context())

    assert result.decision is SupportDecision.HANDOFF
    assert result.needs_admin is True


def test_general_industry_guidance_does_not_use_company_confidence_gate():
    provider = StubProvider(
        SupportReply(
            SupportDecision.GENERAL_GUIDANCE,
            "به‌طور کلی، تمیزکردن ملایم برای روکش MDF مناسب‌تر است.",
            confidence=0.75,
        )
    )

    result = SupportEngine(provider).respond(
        _message(text="به‌طور کلی روکش MDF را چطور تمیز کنم؟"),
        _context(),
    )

    assert result.decision is SupportDecision.GENERAL_GUIDANCE
    assert result.needs_admin is False
