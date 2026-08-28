import hmac
from html import escape
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.admin.dependencies import require_admin
from app.core.security import ensure_csrf_token, validate_csrf, verify_password

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "templates")
INVALID_CREDENTIALS = "نام کاربری یا رمز عبور صحیح نیست"


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    if request.session.get("admin_username"):
        return RedirectResponse("/admin", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="auth/login.html",
        context={"csrf_token": ensure_csrf_token(request), "error": None},
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
            context={"csrf_token": ensure_csrf_token(request), "error": INVALID_CREDENTIALS},
            status_code=401,
        )

    request.session.clear()
    request.session["admin_username"] = settings.admin_username
    ensure_csrf_token(request)
    return RedirectResponse("/admin", status_code=303)


@router.get("", response_class=HTMLResponse)
def dashboard(request: Request, admin: str = Depends(require_admin)) -> HTMLResponse:
    csrf_token = escape(ensure_csrf_token(request), quote=True)
    username = escape(admin, quote=True)
    return HTMLResponse(
        f'<main data-page="dashboard"><h1>داشبورد</h1><p>{username}</p>'
        f'<form method="post" action="/admin/logout">'
        f'<input type="hidden" name="csrf_token" value="{csrf_token}">'
        '<button type="submit">خروج</button></form></main>'
    )


@router.post("/logout")
def logout(request: Request, csrf_token: str = Form(default="")) -> RedirectResponse:
    validate_csrf(request, csrf_token)
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=303)
