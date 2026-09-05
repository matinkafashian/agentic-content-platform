import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.admin.credentials import effective_password, replace_password
from app.admin.dependencies import admin_session_is_current, require_admin
from app.admin.reporting import DashboardReportingService
from app.catalog.repository import ProductRepository
from app.core.database import get_db
from app.core.security import ensure_csrf_token, validate_csrf, verify_password
from app.core.templating import templates

router = APIRouter(prefix="/admin", tags=["admin"])
INVALID_CREDENTIALS = "نام کاربری یا رمز عبور صحیح نیست"


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    if admin_session_is_current(request):
        return RedirectResponse("/admin", status_code=303)
    request.session.clear()
    return templates.TemplateResponse(
        request=request,
        name="auth/login.html",
        context={
            "csrf_token": ensure_csrf_token(request),
            "error": None,
            "public_page": True,
        },
    )


@router.post("/login", response_class=HTMLResponse)
def login(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    username: str = Form(),
    password: str = Form(),
    csrf_token: str = Form(default=""),
) -> HTMLResponse:
    validate_csrf(request, csrf_token)
    settings = request.app.state.settings
    username_matches = hmac.compare_digest(username, settings.admin_username)
    password_hash, session_version = effective_password(db, settings)
    password_matches = verify_password(password, password_hash)
    if not username_matches or not password_matches:
        return templates.TemplateResponse(
            request=request,
            name="auth/login.html",
            context={
                "csrf_token": ensure_csrf_token(request),
                "error": INVALID_CREDENTIALS,
                "public_page": True,
            },
            status_code=401,
        )

    request.session.clear()
    request.session["admin_username"] = settings.admin_username
    request.session["admin_session_version"] = session_version
    ensure_csrf_token(request)
    return RedirectResponse("/admin", status_code=303)


@router.get("/security", response_class=HTMLResponse)
def security_page(
    request: Request,
    admin: Annotated[str, Depends(require_admin)],
    changed: int = 0,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="auth/security.html",
        context={
            "csrf_token": ensure_csrf_token(request),
            "current_page": "security",
            "admin_username": admin,
            "changed": changed == 1,
            "error": None,
        },
    )


@router.post("/security", response_class=HTMLResponse)
def change_password(
    request: Request,
    admin: Annotated[str, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    current_password: str = Form(default=""),
    new_password: str = Form(default=""),
    confirm_password: str = Form(default=""),
    csrf_token: str = Form(default=""),
) -> HTMLResponse:
    validate_csrf(request, csrf_token)
    current_hash, _ = effective_password(db, request.app.state.settings)
    error = None
    if not verify_password(current_password, current_hash):
        error = "رمز فعلی صحیح نیست."
    elif len(new_password) < 10:
        error = "رمز جدید باید حداقل ۱۰ نویسه داشته باشد."
    elif new_password != confirm_password:
        error = "تکرار رمز جدید با رمز واردشده یکسان نیست."
    elif verify_password(new_password, current_hash):
        error = "رمز جدید باید با رمز فعلی متفاوت باشد."

    if error:
        return templates.TemplateResponse(
            request=request,
            name="auth/security.html",
            context={
                "csrf_token": ensure_csrf_token(request),
                "current_page": "security",
                "admin_username": admin,
                "changed": False,
                "error": error,
            },
            status_code=422,
        )

    credential = replace_password(db, new_password)
    request.session.clear()
    request.session["admin_username"] = request.app.state.settings.admin_username
    request.session["admin_session_version"] = credential.session_version
    ensure_csrf_token(request)
    return RedirectResponse("/admin/security?changed=1", status_code=303)


@router.get("", response_class=HTMLResponse)
def dashboard(
    request: Request,
    admin: Annotated[str, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    days: int = 30,
):
    repository = ProductRepository(db)
    total_products = repository.count()
    active_products = repository.count(active=True)
    products_with_image = repository.count_with_image()
    active_rate = round((active_products / total_products) * 100) if total_products else 0
    return templates.TemplateResponse(
        request=request,
        name="dashboard/index.html",
        context={
            "csrf_token": ensure_csrf_token(request),
            "current_page": "dashboard",
            "admin_username": admin,
            "total_products": total_products,
            "active_products": active_products,
            "inactive_products": total_products - active_products,
            "products_with_image": products_with_image,
            "active_rate": active_rate,
            "recent_products": repository.list(limit=5),
            "report": DashboardReportingService(db).build(days=days),
        },
    )


@router.post("/logout")
def logout(request: Request, csrf_token: str = Form(default="")) -> RedirectResponse:
    validate_csrf(request, csrf_token)
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=303)
