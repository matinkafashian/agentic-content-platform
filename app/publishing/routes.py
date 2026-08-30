from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.admin.dependencies import require_admin
from app.core.database import get_db
from app.core.security import ensure_csrf_token, validate_csrf
from app.core.templating import templates
from app.publishing.models import PublicationStatus, PublishingMode
from app.publishing.repository import PublishingRepository
from app.publishing.service import (
    PublishingPaused,
    PublishingService,
    ScheduleInputError,
)

router = APIRouter(prefix="/admin/publishing", tags=["publishing"])

MODE_LABELS = {
    PublishingMode.MANUAL_APPROVAL.value: "تأیید دستی",
    PublishingMode.AUTOMATIC.value: "خودکار",
    PublishingMode.PAUSED.value: "توقف انتشار",
}
STATUS_LABELS = {
    PublicationStatus.SCHEDULED.value: "زمان‌بندی‌شده",
    PublicationStatus.PUBLISHING.value: "در حال ارسال",
    PublicationStatus.RETRY_SCHEDULED.value: "در انتظار تلاش مجدد",
    PublicationStatus.SUCCEEDED.value: "موفق",
    PublicationStatus.FAILED.value: "ناموفق",
    PublicationStatus.CANCELLED.value: "لغوشده",
}


def publishing_service(request: Request, db: Session) -> PublishingService:
    return PublishingService(
        PublishingRepository(db),
        request.app.state.settings.upload_dir,
        request.app.state.platform_adapters,
    )


@router.get("", response_class=HTMLResponse)
def publishing_page(
    request: Request,
    _admin: Annotated[str, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    scheduled: bool = False,
    processed: int = 0,
    paused: bool = False,
    mode_saved: bool = False,
):
    repository = PublishingRepository(db)
    control = repository.control()
    repository.commit()
    publications = repository.list_publications()
    display_timezone = _timezone(request.app.state.settings.app_timezone)
    publication_times = {
        item.id: item.scheduled_for.astimezone(display_timezone).strftime("%Y-%m-%d %H:%M")
        for item in publications
    }
    return templates.TemplateResponse(
        request=request,
        name="publishing/index.html",
        context={
            "csrf_token": ensure_csrf_token(request),
            "current_page": "publishing",
            "control": control,
            "mode_labels": MODE_LABELS,
            "status_labels": STATUS_LABELS,
            "publications": publications,
            "publication_times": publication_times,
            "scheduled": scheduled,
            "processed": processed,
            "paused": paused,
            "mode_saved": mode_saved,
            "timezone": request.app.state.settings.app_timezone,
        },
    )


@router.post("/mode")
def change_mode(
    request: Request,
    _admin: Annotated[str, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    csrf_token: Annotated[str, Form()] = "",
    mode: Annotated[str, Form()] = PublishingMode.MANUAL_APPROVAL.value,
):
    validate_csrf(request, csrf_token)
    try:
        publishing_service(request, db).set_mode(mode)
    except ScheduleInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return RedirectResponse("/admin/publishing?mode_saved=1", status_code=303)


@router.post("/bundles/{bundle_id}/schedule")
def schedule_bundle(
    bundle_id: int,
    request: Request,
    _admin: Annotated[str, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    csrf_token: Annotated[str, Form()] = "",
    destination: Annotated[str, Form()] = "کانال آزمایشی",
    scheduled_for: Annotated[str, Form()] = "",
):
    validate_csrf(request, csrf_token)
    try:
        when = _parse_local_datetime(
            scheduled_for, request.app.state.settings.app_timezone
        )
        publishing_service(request, db).schedule(
            bundle_id,
            platform="sandbox",
            destination=destination,
            scheduled_for=when,
        )
    except ScheduleInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return RedirectResponse("/admin/publishing?scheduled=1", status_code=303)


@router.post("/run-due")
def run_due_now(
    request: Request,
    _admin: Annotated[str, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    csrf_token: Annotated[str, Form()] = "",
):
    validate_csrf(request, csrf_token)
    try:
        processed = len(publishing_service(request, db).run_due())
    except PublishingPaused:
        return RedirectResponse("/admin/publishing?paused=1", status_code=303)
    return RedirectResponse(
        f"/admin/publishing?processed={processed}", status_code=303
    )


@router.get("/bundles/{bundle_id}/image")
def bundle_image(
    bundle_id: int,
    request: Request,
    _admin: Annotated[str, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    bundle = PublishingRepository(db).get_bundle(bundle_id)
    if bundle is None:
        raise HTTPException(status_code=404, detail="Bundle not found")
    path = _bundle_path(
        request.app.state.settings.upload_dir,
        bundle.bundle_key,
        bundle.image_relative_path,
    )
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Bundle image not found")
    return FileResponse(path, media_type=bundle.image_mime_type)


@router.get("/bundles/{bundle_id}/voice")
def bundle_voice(
    bundle_id: int,
    request: Request,
    _admin: Annotated[str, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    bundle = PublishingRepository(db).get_bundle(bundle_id)
    if bundle is None or not bundle.voice_relative_path:
        raise HTTPException(status_code=404, detail="Bundle voice not found")
    path = _bundle_path(
        request.app.state.settings.upload_dir,
        bundle.bundle_key,
        bundle.voice_relative_path,
    )
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Bundle voice not found")
    return FileResponse(
        path,
        media_type=bundle.voice_mime_type,
        headers={"Accept-Ranges": "bytes"},
    )


def _parse_local_datetime(value: str, timezone_name: str) -> datetime:
    if not value.strip():
        return datetime.now(UTC)
    try:
        local = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ScheduleInputError("زمان انتخاب‌شده معتبر نیست") from exc
    if local.tzinfo is None:
        local = local.replace(tzinfo=_timezone(timezone_name))
    return local.astimezone(UTC)


def _timezone(timezone_name: str):
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        if timezone_name == "Asia/Tehran":
            return timezone(timedelta(hours=3, minutes=30), name="Asia/Tehran")
        return UTC


def _bundle_path(upload_root: Path, bundle_key: str, relative_path: str) -> Path:
    candidate = PurePosixPath(relative_path.replace("\\", "/"))
    windows = PureWindowsPath(relative_path)
    expected = ("private", "bundles", bundle_key)
    if (
        candidate.is_absolute()
        or windows.is_absolute()
        or ".." in candidate.parts
        or candidate.parts[:3] != expected
    ):
        raise HTTPException(status_code=404, detail="Bundle file not found")
    return upload_root.joinpath(*candidate.parts)
