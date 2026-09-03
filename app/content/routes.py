from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.admin.dependencies import require_admin
from app.brand.repository import BrandRepository
from app.brand.service import BrandService
from app.catalog.repository import ProductRepository
from app.content.openai_provider import ContentProviderError
from app.content.repository import ContentRepository
from app.content.service import (
    ContentInputError,
    ContentNotFound,
    ContentService,
    ContentStateError,
)
from app.content.workflow import build_content_workflow
from app.core.database import get_db
from app.core.security import ensure_csrf_token, validate_csrf
from app.core.templating import templates
from app.media.image_edit_service import (
    EditedImageRepository,
    EditedImageService,
    InvalidStoredImagePath,
    resolve_product_original_path,
)
from app.media.openai_image_editor import ImageEditorError, build_product_edit_prompt
from app.media.voice import InvalidVoice, validate_voice
from app.media.voice_service import VoiceRepository, VoiceService
from app.publishing.repository import PublishingRepository
from app.publishing.routes import MODE_LABELS, PLATFORM_LABELS
from app.publishing.service import BundleInputError, PublishingService

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


def _image_service(request: Request, db: Session) -> EditedImageService:
    return EditedImageService(
        EditedImageRepository(db), request.app.state.settings.upload_dir
    )


def _generate_and_store_edited_image(
    draft_id: int,
    request: Request,
    db: Session,
    *,
    mode: str,
    background_style: str,
    overlay_text: str = "",
    topic: str = "",
    message: str = "",
):
    editor = request.app.state.image_editor
    if editor is None:
        raise ImageEditorError("سرویس ویرایش تصویر فعال نیست")
    draft = _content_service(request, db).get(draft_id)
    relative_path = draft.product.primary_image_path
    if not relative_path:
        raise ValueError("برای این محصول هنوز تصویر اصلی ثبت نشده است")
    source_path = resolve_product_original_path(
        request.app.state.settings.upload_dir,
        draft.product.id,
        relative_path,
    )
    if not source_path.is_file():
        raise ValueError("فایل تصویر اصلی محصول پیدا نشد")
    mime_type = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(source_path.suffix.lower())
    if mime_type is None:
        raise ValueError("فرمت تصویر اصلی برای ویرایش پشتیبانی نمی‌شود")
    build_product_edit_prompt(
        mode=mode,
        background_style=background_style,
        overlay_text=overlay_text,
        topic=topic,
        message=message,
    )
    edited = editor.edit(
        source=source_path.read_bytes(),
        filename=source_path.name,
        mime_type=mime_type,
        mode=mode,
        background_style=background_style,
        overlay_text=overlay_text,
        topic=topic,
        message=message,
    )
    return _image_service(request, db).attach_or_replace(draft_id, edited)


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
    voice_saved: bool = False,
    image_saved: bool = False,
    bundle_saved: bool = False,
    approved: bool = False,
    rejected: bool = False,
    caption_saved: bool = False,
    status_code: int = 200,
):
    service = _content_service(request, db)
    try:
        draft = service.get(draft_id)
    except ContentNotFound as exc:
        raise HTTPException(status_code=404, detail="Content draft not found") from exc
    voice = VoiceRepository(db).for_draft(draft_id)
    edited_image = EditedImageRepository(db).for_draft(draft_id)
    publishing_repository = PublishingRepository(db)
    publishing_control = publishing_repository.control()
    bundle = publishing_repository.bundle_for_draft(draft_id)
    publishing_repository.commit()
    workflow = build_content_workflow(
        draft_status=draft.status,
        publishing_mode=publishing_control.mode,
        has_original_image=bool(draft.product.primary_image_path),
        has_edited_image=edited_image is not None,
        image_editor_available=request.app.state.image_editor is not None,
        has_voice=voice is not None,
        has_bundle=bundle is not None,
        product_edit_url=f"/admin/products/{draft.product.id}/edit",
    )
    publishing_default_destinations = dict(
        request.app.state.platform_default_destinations
    )
    publishing_default_destinations["telegram"] = (
        request.app.state.telegram_default_destination
    )
    active_real_destinations = [
        (
            name,
            PLATFORM_LABELS.get(name, name),
            publishing_default_destinations.get(name, "").strip(),
        )
        for name in request.app.state.platform_adapters
        if name != "sandbox"
        and publishing_default_destinations.get(name, "").strip()
    ]
    if not active_real_destinations and "sandbox" in request.app.state.platform_adapters:
        active_real_destinations = [
            ("sandbox", PLATFORM_LABELS["sandbox"], "کانال آزمایشی")
        ]
    return templates.TemplateResponse(
        request=request,
        name="content/detail.html",
        context={
            "csrf_token": ensure_csrf_token(request),
            "current_page": "content",
            "draft": draft,
            "history": service.history(draft_id),
            "voice": voice,
            "edited_image": edited_image,
            "status_label": STATUS_LABELS[draft.status],
            "status_labels": STATUS_LABELS,
            "voice_saved": voice_saved,
            "image_saved": image_saved,
            "bundle_saved": bundle_saved,
            "approved": approved,
            "rejected": rejected,
            "caption_saved": caption_saved,
            "bundle": bundle,
            "publishing_control": publishing_control,
            "workflow": workflow,
            "workflow_steps": workflow.by_key,
            "publishing_mode_label": MODE_LABELS[publishing_control.mode],
            "publishing_platforms": [
                (name, PLATFORM_LABELS.get(name, name))
                for name in request.app.state.platform_adapters
            ],
            "default_publishing_platform": next(
                (
                    name
                    for name in ("telegram", "bale", "rubika", "sandbox")
                    if name in request.app.state.platform_adapters
                ),
                "sandbox",
            ),
            "publishing_default_destinations": (
                publishing_default_destinations
            ),
            "publishing_active_destinations": active_real_destinations,
            "default_publishing_destination": next(
                (
                    publishing_default_destinations.get(name, "")
                    for name in ("telegram", "bale", "rubika", "sandbox")
                    if name in request.app.state.platform_adapters
                ),
                "کانال آزمایشی",
            ),
            "telegram_default_destination": (
                request.app.state.telegram_default_destination
            ),
            "image_editor_available": request.app.state.image_editor is not None,
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
    content_mode: Annotated[str, Form()] = "ai",
    ai_brief: Annotated[str, Form()] = "",
    manual_caption: Annotated[str, Form()] = "",
    requested_angle: Annotated[str, Form()] = "product_intro",
):
    validate_csrf(request, csrf_token)
    BrandService(BrandRepository(db)).get_or_create()
    content_input = manual_caption if content_mode == "manual" else ai_brief
    form_values = {
        "content_mode": content_mode,
        "ai_brief": ai_brief,
        "manual_caption": manual_caption,
        "requested_angle": requested_angle,
    }
    try:
        draft = _content_service(request, db).generate(
            product_id,
            user_brief=content_input,
            requested_angle=requested_angle,
            content_mode=content_mode,
        )
    except ContentInputError as exc:
        return _render_new(
            request,
            db,
            selected_product_id=product_id,
            values=form_values,
            error=str(exc),
            status_code=422,
        )
    except ContentProviderError as exc:
        return _render_new(
            request,
            db,
            selected_product_id=product_id,
            values=form_values,
            error=str(exc),
            status_code=503,
        )
    return RedirectResponse(f"/admin/content/{draft.id}", status_code=303)


@router.get("/{draft_id}", response_class=HTMLResponse)
def content_detail(
    draft_id: int,
    request: Request,
    _admin: Annotated[str, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    voice_saved: bool = False,
    image_saved: bool = False,
    bundle_saved: bool = False,
    approved: bool = False,
    rejected: bool = False,
    caption_saved: bool = False,
):
    return _render_detail(
        request,
        db,
        draft_id,
        voice_saved=voice_saved,
        image_saved=image_saved,
        bundle_saved=bundle_saved,
        approved=approved,
        rejected=rejected,
        caption_saved=caption_saved,
    )


@router.post("/{draft_id}/bundle")
def create_post_bundle(
    draft_id: int,
    request: Request,
    _admin: Annotated[str, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    csrf_token: Annotated[str, Form()] = "",
):
    validate_csrf(request, csrf_token)
    service = PublishingService(
        PublishingRepository(db),
        request.app.state.settings.upload_dir,
        request.app.state.platform_adapters,
        require_edited_image=request.app.state.image_editor is not None,
    )
    try:
        control = service.control()
        edited_image = EditedImageRepository(db).for_draft(draft_id)
        if (
            control.mode == "automatic"
            and request.app.state.image_editor is not None
            and edited_image is None
        ):
            draft = _content_service(request, db).get(draft_id)
            _generate_and_store_edited_image(
                draft_id,
                request,
                db,
                mode="studio",
                background_style="adaptive_studio",
                overlay_text=draft.product.name,
            )
        service.create_bundle(draft_id)
    except BundleInputError as exc:
        return _render_detail(request, db, draft_id, error=str(exc), status_code=422)
    except ContentNotFound as exc:
        raise HTTPException(status_code=404, detail="Content draft not found") from exc
    except (ImageEditorError, InvalidStoredImagePath) as exc:
        return _render_detail(request, db, draft_id, error=str(exc), status_code=503)
    except ValueError as exc:
        return _render_detail(request, db, draft_id, error=str(exc), status_code=422)
    return RedirectResponse(
        f"/admin/content/{draft_id}?bundle_saved=1#publishing-bundle",
        status_code=303,
    )


@router.post("/{draft_id}/image/generate")
def generate_edited_image(
    draft_id: int,
    request: Request,
    _admin: Annotated[str, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    csrf_token: Annotated[str, Form()] = "",
    image_mode: Annotated[str, Form()] = "studio",
    background_style: Annotated[str, Form()] = "adaptive_studio",
    overlay_text: Annotated[str, Form()] = "",
    topic: Annotated[str, Form()] = "",
    message: Annotated[str, Form()] = "",
):
    validate_csrf(request, csrf_token)
    editor = request.app.state.image_editor
    if editor is None:
        return _render_detail(
            request,
            db,
            draft_id,
            error="سرویس ویرایش تصویر فعال نیست؛ کلید OpenAI باید تنظیم شود.",
            status_code=503,
        )
    try:
        _generate_and_store_edited_image(
            draft_id,
            request,
            db,
            mode=image_mode,
            background_style=background_style,
            overlay_text=overlay_text,
            topic=topic,
            message=message,
        )
    except ContentNotFound as exc:
        raise HTTPException(status_code=404, detail="Content draft not found") from exc
    except (ImageEditorError, InvalidStoredImagePath) as exc:
        return _render_detail(
            request, db, draft_id, error=str(exc), status_code=503
        )
    except ValueError as exc:
        return _render_detail(
            request, db, draft_id, error=str(exc), status_code=422
        )
    return RedirectResponse(
        f"/admin/content/{draft_id}?image_saved=1#image-studio",
        status_code=303,
    )


@router.get("/{draft_id}/image")
def private_edited_image(
    draft_id: int,
    request: Request,
    _admin: Annotated[str, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    download: bool = False,
):
    asset = EditedImageRepository(db).for_draft(draft_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Edited image not found")
    path = _image_service(request, db).path_for(asset)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Edited image not found")
    return FileResponse(
        path,
        media_type=asset.mime_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="edited-product-{draft_id}.png"'
                if download
                else "inline"
            ),
        },
    )


@router.post("/{draft_id}/image/delete")
def delete_edited_image(
    draft_id: int,
    request: Request,
    _admin: Annotated[str, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    csrf_token: Annotated[str, Form()] = "",
):
    validate_csrf(request, csrf_token)
    _image_service(request, db).delete(draft_id)
    return RedirectResponse(f"/admin/content/{draft_id}#image-studio", status_code=303)


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
    return RedirectResponse(
        f"/admin/content/{draft_id}?caption_saved=1#caption-studio",
        status_code=303,
    )


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
    except ContentProviderError as exc:
        return _render_detail(request, db, draft_id, error=str(exc), status_code=503)
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
    query_flag = "approved" if action == "approve" else "rejected"
    return RedirectResponse(
        f"/admin/content/{draft_id}?{query_flag}=1#caption-studio",
        status_code=303,
    )


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
    return RedirectResponse(
        f"/admin/content/{draft_id}?voice_saved=1#voice-studio",
        status_code=303,
    )


@router.get("/{draft_id}/voice")
def private_voice(
    draft_id: int,
    request: Request,
    _admin: Annotated[str, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    download: bool = False,
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
        headers={
            "Accept-Ranges": "bytes",
            "Content-Disposition": (
                f'attachment; filename="voice-{draft_id}{path.suffix}"'
                if download
                else "inline"
            ),
        },
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
