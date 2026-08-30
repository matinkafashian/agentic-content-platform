from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.admin.dependencies import require_admin
from app.brand.repository import BrandRepository
from app.brand.service import BrandService
from app.catalog.repository import ProductRepository
from app.content.repository import ContentRepository
from app.content.service import (
    ContentInputError,
    ContentNotFound,
    ContentService,
    ContentStateError,
)
from app.core.database import get_db
from app.core.security import ensure_csrf_token, validate_csrf
from app.core.templating import templates
from app.media.voice import InvalidVoice, validate_voice
from app.media.voice_service import VoiceRepository, VoiceService

router = APIRouter(prefix="/admin/content", tags=["content"])

STATUS_LABELS = {
    "draft": "پیش‌نویس",
    "waiting_approval": "منتظر تأیید",
    "approved": "تأییدشده",
    "rejected": "ردشده",
    "superseded": "نسخه قدیمی",
}


def _content_service(request: Request, db: Session) -> ContentService:
    return ContentService(
        ContentRepository(db),
        ProductRepository(db),
        BrandRepository(db),
        request.app.state.content_provider,
    )


def _voice_service(request: Request, db: Session) -> VoiceService:
    return VoiceService(VoiceRepository(db), request.app.state.settings.upload_dir)


def _render_new(
    request: Request,
    db: Session,
    *,
    selected_product_id: int | None = None,
    values: dict[str, object] | None = None,
    error: str | None = None,
    status_code: int = 200,
):
    BrandService(BrandRepository(db)).get_or_create()
    products = [product for product in ProductRepository(db).list() if product.active]
    return templates.TemplateResponse(
        request=request,
        name="content/new.html",
        context={
            "csrf_token": ensure_csrf_token(request),
            "current_page": "content",
            "products": products,
            "selected_product_id": selected_product_id,
            "values": values or {"requested_angle": "product_intro"},
            "error": error,
        },
        status_code=status_code,
    )


def _render_detail(
    request: Request,
    db: Session,
    draft_id: int,
    *,
    error: str | None = None,
    status_code: int = 200,
):
    service = _content_service(request, db)
    try:
        draft = service.get(draft_id)
    except ContentNotFound as exc:
        raise HTTPException(status_code=404, detail="Content draft not found") from exc
    voice = VoiceRepository(db).for_draft(draft_id)
    return templates.TemplateResponse(
        request=request,
        name="content/detail.html",
        context={
            "csrf_token": ensure_csrf_token(request),
            "current_page": "content",
            "draft": draft,
            "history": service.history(draft_id),
            "voice": voice,
            "status_label": STATUS_LABELS[draft.status],
            "status_labels": STATUS_LABELS,
            "error": error,
        },
        status_code=status_code,
    )


@router.get("/new", response_class=HTMLResponse)
def new_content_page(
    request: Request,
    _admin: Annotated[str, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    product_id: int | None = None,
):
    return _render_new(request, db, selected_product_id=product_id)


@router.post("", response_class=HTMLResponse)
def generate_content(
    request: Request,
    _admin: Annotated[str, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    csrf_token: Annotated[str, Form()] = "",
    product_id: Annotated[int, Form()] = 0,
    user_brief: Annotated[str, Form()] = "",
    requested_angle: Annotated[str, Form()] = "product_intro",
):
    validate_csrf(request, csrf_token)
    BrandService(BrandRepository(db)).get_or_create()
    try:
        draft = _content_service(request, db).generate(
            product_id,
            user_brief=user_brief,
            requested_angle=requested_angle,
        )
    except ContentInputError as exc:
        return _render_new(
            request,
            db,
            selected_product_id=product_id,
            values={"user_brief": user_brief, "requested_angle": requested_angle},
            error=str(exc),
            status_code=422,
        )
    return RedirectResponse(f"/admin/content/{draft.id}", status_code=303)


@router.get("/{draft_id}", response_class=HTMLResponse)
def content_detail(
    draft_id: int,
    request: Request,
    _admin: Annotated[str, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    return _render_detail(request, db, draft_id)


@router.post("/{draft_id}/edit", response_class=HTMLResponse)
def edit_content(
    draft_id: int,
    request: Request,
    _admin: Annotated[str, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    csrf_token: Annotated[str, Form()] = "",
    final_caption: Annotated[str, Form()] = "",
):
    validate_csrf(request, csrf_token)
    try:
        _content_service(request, db).edit_caption(draft_id, final_caption)
    except (ContentInputError, ContentStateError) as exc:
        return _render_detail(request, db, draft_id, error=str(exc), status_code=422)
    return RedirectResponse(f"/admin/content/{draft_id}", status_code=303)


@router.post("/{draft_id}/regenerate")
def regenerate_content(
    draft_id: int,
    request: Request,
    _admin: Annotated[str, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    csrf_token: Annotated[str, Form()] = "",
):
    validate_csrf(request, csrf_token)
    try:
        draft = _content_service(request, db).regenerate(draft_id)
    except ContentNotFound as exc:
        raise HTTPException(status_code=404, detail="Content draft not found") from exc
    return RedirectResponse(f"/admin/content/{draft.id}", status_code=303)


def _change_state(
    action: str,
    draft_id: int,
    request: Request,
    db: Session,
):
    service = _content_service(request, db)
    try:
        getattr(service, action)(draft_id)
    except ContentStateError as exc:
        return _render_detail(request, db, draft_id, error=str(exc), status_code=422)
    except ContentNotFound as exc:
        raise HTTPException(status_code=404, detail="Content draft not found") from exc
    return RedirectResponse(f"/admin/content/{draft_id}", status_code=303)


@router.post("/{draft_id}/approve")
def approve_content(
    draft_id: int,
    request: Request,
    _admin: Annotated[str, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    csrf_token: Annotated[str, Form()] = "",
):
    validate_csrf(request, csrf_token)
    return _change_state("approve", draft_id, request, db)


@router.post("/{draft_id}/reject")
def reject_content(
    draft_id: int,
    request: Request,
    _admin: Annotated[str, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    csrf_token: Annotated[str, Form()] = "",
):
    validate_csrf(request, csrf_token)
    return _change_state("reject", draft_id, request, db)


@router.post("/{draft_id}/voice")
def upload_voice(
    draft_id: int,
    request: Request,
    _admin: Annotated[str, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    csrf_token: Annotated[str, Form()] = "",
    duration_ms: Annotated[str, Form()] = "",
    voice: Annotated[UploadFile | None, File()] = None,
):
    validate_csrf(request, csrf_token)
    if voice is None or not voice.filename:
        return _render_detail(
            request, db, draft_id, error="انتخاب Voice الزامی است", status_code=422
        )
    data = voice.file.read(request.app.state.settings.max_voice_bytes + 1)
    try:
        duration = int(duration_ms) if duration_ms else None
        validated = validate_voice(
            data,
            voice.filename,
            voice.content_type or "",
            duration_ms=duration,
        )
        _voice_service(request, db).attach_or_replace(draft_id, validated)
    except (InvalidVoice, ValueError) as exc:
        return _render_detail(request, db, draft_id, error=str(exc), status_code=422)
    return RedirectResponse(f"/admin/content/{draft_id}", status_code=303)


@router.get("/{draft_id}/voice")
def private_voice(
    draft_id: int,
    request: Request,
    _admin: Annotated[str, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    voice_repository = VoiceRepository(db)
    asset = voice_repository.for_draft(draft_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Voice not found")
    path = _voice_service(request, db).path_for(asset)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Voice not found")
    return FileResponse(
        path,
        media_type=asset.mime_type,
        headers={"Accept-Ranges": "bytes", "Content-Disposition": "inline"},
    )


@router.post("/{draft_id}/voice/delete")
def delete_voice(
    draft_id: int,
    request: Request,
    _admin: Annotated[str, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    csrf_token: Annotated[str, Form()] = "",
):
    validate_csrf(request, csrf_token)
    _voice_service(request, db).delete(draft_id)
    return RedirectResponse(f"/admin/content/{draft_id}", status_code=303)
