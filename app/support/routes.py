from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.admin.dependencies import require_admin
from app.core.database import get_db
from app.core.security import ensure_csrf_token, validate_csrf
from app.core.templating import templates
from app.support.engine import (
    IncomingSupportMessage,
    SupportChatType,
    SupportContentType,
    SupportEngine,
    SupportReply,
)
from app.support.openai_provider import SupportProviderError
from app.support.repository import SupportKnowledgeRepository
from app.support.schemas import SupportKnowledgeInput
from app.support.service import SupportKnowledgeService, build_support_context

router = APIRouter(prefix="/admin/support", tags=["support"])


def _render(
    request: Request,
    *,
    content: str,
    saved: bool = False,
    error: str | None = None,
    question: str = "",
    reply: SupportReply | None = None,
    source_texts: tuple[str, ...] = (),
    provider_available: bool = False,
    status_code: int = 200,
):
    return templates.TemplateResponse(
        request=request,
        name="support/knowledge.html",
        context={
            "csrf_token": ensure_csrf_token(request),
            "current_page": "support",
            "content": content,
            "saved": saved,
            "error": error,
            "question": question,
            "reply": reply,
            "source_texts": source_texts,
            "provider_available": provider_available,
        },
        status_code=status_code,
    )


@router.get("", response_class=HTMLResponse)
def support_page(
    request: Request,
    _admin: Annotated[str, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    saved: bool = False,
):
    knowledge = SupportKnowledgeService(SupportKnowledgeRepository(db)).get_or_create()
    return _render(
        request,
        content=knowledge.content,
        saved=saved,
        provider_available=request.app.state.support_provider is not None,
    )


@router.post("", response_class=HTMLResponse)
def update_support_knowledge(
    request: Request,
    _admin: Annotated[str, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    csrf_token: Annotated[str, Form()] = "",
    content: Annotated[str, Form()] = "",
):
    validate_csrf(request, csrf_token)
    try:
        data = SupportKnowledgeInput(content=content)
    except ValidationError:
        return _render(
            request,
            content=content,
            error="متن اطلاعات کسب‌وکار معتبر نیست یا بیش از اندازه طولانی است.",
            provider_available=request.app.state.support_provider is not None,
            status_code=422,
        )
    SupportKnowledgeService(SupportKnowledgeRepository(db)).update(data)
    return RedirectResponse("/admin/support?saved=1", status_code=303)


@router.post("/test", response_class=HTMLResponse)
def test_support_answer(
    request: Request,
    _admin: Annotated[str, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    csrf_token: Annotated[str, Form()] = "",
    question: Annotated[str, Form()] = "",
):
    validate_csrf(request, csrf_token)
    service = SupportKnowledgeService(SupportKnowledgeRepository(db))
    knowledge = service.get_or_create()
    clean_question = question.strip()
    provider = request.app.state.support_provider
    if not clean_question:
        return _render(
            request,
            content=knowledge.content,
            error="برای تست، یک سؤال متنی وارد کنید.",
            provider_available=provider is not None,
            status_code=422,
        )
    if provider is None:
        return _render(
            request,
            content=knowledge.content,
            question=clean_question,
            error="پاسخ‌گوی هوشمند فعال نیست؛ تنظیمات OpenAI را بررسی کنید.",
            provider_available=False,
            status_code=503,
        )

    try:
        knowledge = service.ensure_index(knowledge, provider)
        context = build_support_context(db, knowledge, service)
        reply = SupportEngine(provider).respond(
            IncomingSupportMessage(
                platform="admin_test",
                chat_id="admin",
                user_id=_admin,
                message_id="preview",
                chat_type=SupportChatType.PRIVATE,
                content_type=SupportContentType.TEXT,
                text=clean_question,
            ),
            context,
        )
    except SupportProviderError as exc:
        return _render(
            request,
            content=knowledge.content,
            question=clean_question,
            error=str(exc),
            provider_available=True,
            status_code=502,
        )

    sources_by_ref = {chunk.source_ref: chunk.text for chunk in context.knowledge_chunks}
    return _render(
        request,
        content=knowledge.content,
        question=clean_question,
        reply=reply,
        source_texts=tuple(
            sources_by_ref[ref] for ref in reply.source_refs if ref in sources_by_ref
        ),
        provider_available=True,
    )
