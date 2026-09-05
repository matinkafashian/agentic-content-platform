from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.admin.dependencies import require_admin
from app.brand.models import BrandProfile
from app.brand.repository import BrandRepository
from app.brand.schemas import BrandProfileInput
from app.brand.service import BrandService
from app.core.database import get_db
from app.core.security import ensure_csrf_token, validate_csrf
from app.core.templating import templates

router = APIRouter(prefix="/admin/brand", tags=["brand"])


def _values(profile: BrandProfile) -> dict[str, object]:
    return {
        "business_name": profile.business_name,
        "tagline": profile.tagline,
        "audience": profile.audience,
        "tone_guidelines": profile.tone_guidelines,
        "support_handle": profile.support_handle,
        "support_phone": profile.support_phone,
        "default_cta": profile.default_cta,
        "approved_claims": profile.approved_claims,
        "default_hashtags": profile.default_hashtags,
    }


def _render(
    request: Request,
    values: dict[str, object],
    *,
    error: str | None = None,
    status_code: int = 200,
):
    return templates.TemplateResponse(
        request=request,
        name="brand/form.html",
        context={
            "csrf_token": ensure_csrf_token(request),
            "current_page": "brand",
            "values": values,
            "error": error,
        },
        status_code=status_code,
    )


@router.get("", response_class=HTMLResponse)
def brand_page(
    request: Request,
    _admin: Annotated[str, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    profile = BrandService(BrandRepository(db)).get_or_create()
    return _render(request, _values(profile))


@router.post("", response_class=HTMLResponse)
def update_brand(
    request: Request,
    _admin: Annotated[str, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    csrf_token: Annotated[str, Form()] = "",
    business_name: Annotated[str, Form()] = "",
    tagline: Annotated[str, Form()] = "",
    audience: Annotated[str, Form()] = "",
    tone_guidelines: Annotated[str, Form()] = "",
    support_handle: Annotated[str, Form()] = "",
    support_phone: Annotated[str, Form()] = "",
    default_cta: Annotated[str, Form()] = "",
    approved_claim: Annotated[list[str] | None, Form()] = None,
    default_hashtag: Annotated[list[str] | None, Form()] = None,
):
    validate_csrf(request, csrf_token)
    raw = {
        "business_name": business_name,
        "tagline": tagline,
        "audience": audience,
        "tone_guidelines": tone_guidelines,
        "support_handle": support_handle,
        "support_phone": support_phone,
        "default_cta": default_cta,
        "approved_claims": approved_claim or [],
        "default_hashtags": default_hashtag or [],
    }
    try:
        data = BrandProfileInput(**raw)
    except ValidationError:
        return _render(
            request,
            raw,
            error="اطلاعات برند کامل یا معتبر نیست",
            status_code=422,
        )
    BrandService(BrandRepository(db)).update(data)
    return RedirectResponse("/admin/brand", status_code=303)
