import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.admin.dependencies import require_admin
from app.catalog.repository import ProductRepository
from app.core.database import get_db
from app.core.security import ensure_csrf_token, validate_csrf, verify_password
from app.core.templating import templates

router = APIRouter(prefix="/admin", tags=["admin"])
INVALID_CREDENTIALS = "نام کاربری یا رمز عبور صحیح نیست"


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    if request.session.get("admin_username"):
        return RedirectResponse("/admin", status_code=303)
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
    username: str = Form(),
    password: str = Form(),
    csrf_token: str = Form(default=""),
) -> HTMLResponse:
    validate_csrf(request, csrf_token)
    settings = request.app.state.settings
    username_matches = hmac.compare_digest(username, settings.admin_username)
    password_matches = verify_password(password, settings.admin_password_hash)
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
    ensure_csrf_token(request)
    return RedirectResponse("/admin", status_code=303)


@router.get("", response_class=HTMLResponse)
def dashboard(
    request: Request,
    admin: Annotated[str, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
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
        },
    )


@router.post("/logout")
def logout(request: Request, csrf_token: str = Form(default="")) -> RedirectResponse:
    validate_csrf(request, csrf_token)
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=303)
