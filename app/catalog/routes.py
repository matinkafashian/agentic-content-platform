from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.admin.dependencies import require_admin
from app.catalog.models import Product
from app.catalog.repository import ProductRepository
from app.catalog.schemas import ProductCreate, ProductUpdate
from app.catalog.service import ProductNotFound, ProductService
from app.core.database import get_db
from app.core.security import ensure_csrf_token, validate_csrf
from app.media.images import (
    MAX_IMAGE_BYTES,
    InvalidImage,
    ValidatedImage,
    save_product_image,
    validate_image,
)

router = APIRouter(prefix="/admin/products", tags=["products"])
templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "templates")


def format_price_fa(value: Decimal) -> str:
    western = f"{value:,.0f}"
    return western.translate(str.maketrans("0123456789,", "۰۱۲۳۴۵۶۷۸۹٬"))


templates.env.filters["price_fa"] = format_price_fa


@dataclass(frozen=True)
class ProductFormData:
    csrf_token: str
    name: str
    description: str
    price: str
    availability: str
    shipping_info: str
    tags: str
    active: bool
    attribute_keys: list[str]
    attribute_values: list[str]

    def values(self) -> dict[str, object]:
        return {
            "name": self.name,
            "description": self.description,
            "price": self.price,
            "availability": self.availability,
            "shipping_info": self.shipping_info,
            "tags": self.tags,
            "active": self.active,
            "attributes": dict(zip(self.attribute_keys, self.attribute_values, strict=False)),
        }

    def product_data(self) -> dict[str, object]:
        attributes = {
            key.strip(): value.strip()
            for key, value in zip(self.attribute_keys, self.attribute_values, strict=False)
            if key.strip() and value.strip()
        }
        tags = [item.strip() for item in self.tags.replace("،", ",").split(",")]
        return {
            "name": self.name,
            "description": self.description,
            "price": self.price,
            "availability": self.availability,
            "shipping_info": self.shipping_info,
            "attributes": attributes,
            "tags": tags,
            "active": self.active,
        }


def parse_product_form(
    csrf_token: Annotated[str, Form()] = "",
    name: Annotated[str, Form()] = "",
    description: Annotated[str, Form()] = "",
    price: Annotated[str, Form()] = "",
    availability: Annotated[str, Form()] = "available",
    shipping_info: Annotated[str, Form()] = "",
    tags: Annotated[str, Form()] = "",
    active: Annotated[str | None, Form()] = None,
    attribute_key: Annotated[list[str] | None, Form()] = None,
    attribute_value: Annotated[list[str] | None, Form()] = None,
) -> ProductFormData:
    return ProductFormData(
        csrf_token=csrf_token,
        name=name,
        description=description,
        price=price,
        availability=availability,
        shipping_info=shipping_info,
        tags=tags,
        active=active in {"1", "on", "true"},
        attribute_keys=attribute_key or [],
        attribute_values=attribute_value or [],
    )


def product_values(product: Product) -> dict[str, object]:
    return {
        "name": product.name,
        "description": product.description,
        "price": product.price,
        "availability": product.availability,
        "shipping_info": product.shipping_info,
        "tags": "، ".join(product.tags),
        "active": product.active,
        "attributes": product.attributes,
    }


def validation_errors(exc: ValidationError) -> dict[str, str]:
    labels = {
        "name": "نام محصول باید بین ۲ تا ۲۰۰ نویسه باشد",
        "price": "قیمت باید عددی معتبر و بزرگ‌تر یا مساوی صفر باشد",
        "availability": "وضعیت موجودی معتبر نیست",
        "tags": "هشتگ‌های واردشده معتبر نیستند",
        "attributes": "ویژگی‌های محصول معتبر نیستند",
    }
    errors: dict[str, str] = {}
    for error in exc.errors():
        field = str(error["loc"][-1])
        errors.setdefault(field, labels.get(field, "مقدار واردشده معتبر نیست"))
    return errors


def read_validated_image(upload: UploadFile | None, *, required: bool) -> ValidatedImage | None:
    if upload is None or not upload.filename:
        if required:
            raise InvalidImage("انتخاب تصویر محصول الزامی است")
        return None
    data = upload.file.read(MAX_IMAGE_BYTES + 1)
    return validate_image(data, upload.filename, upload.content_type or "")


def render_form(
    request: Request,
    values: dict[str, object],
    errors: dict[str, str],
    *,
    product: Product | None = None,
    status_code: int = 200,
):
    return templates.TemplateResponse(
        request=request,
        name="products/form.html",
        context={
            "csrf_token": ensure_csrf_token(request),
            "values": values,
            "errors": errors,
            "product": product,
        },
        status_code=status_code,
    )


@router.get("", response_class=HTMLResponse)
def product_index(
    request: Request,
    _admin: Annotated[str, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    products = ProductRepository(db).list()
    return templates.TemplateResponse(
        request=request,
        name="products/index.html",
        context={"products": products},
    )


@router.get("/new", response_class=HTMLResponse)
def new_product(request: Request, _admin: Annotated[str, Depends(require_admin)]):
    return render_form(
        request,
        values={"availability": "available", "active": True, "attributes": {}},
        errors={},
    )


@router.post("", response_class=HTMLResponse)
def create_product(
    request: Request,
    form: Annotated[ProductFormData, Depends(parse_product_form)],
    _admin: Annotated[str, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    image: Annotated[UploadFile | None, File()] = None,
):
    validate_csrf(request, form.csrf_token)
    try:
        validated_image = read_validated_image(image, required=True)
        data = ProductCreate(**form.product_data())
    except InvalidImage as exc:
        return render_form(request, form.values(), {"image": str(exc)}, status_code=422)
    except ValidationError as exc:
        return render_form(
            request,
            form.values(),
            validation_errors(exc),
            status_code=422,
        )

    service = ProductService(ProductRepository(db))
    product = service.create(data)
    stored_path = None
    try:
        if validated_image is None:
            raise InvalidImage("انتخاب تصویر محصول الزامی است")
        upload_root = request.app.state.settings.upload_dir
        stored_path = save_product_image(upload_root, product.id, validated_image)
        relative_path = stored_path.relative_to(upload_root).as_posix()
        service.set_image(product.id, relative_path)
    except Exception:
        if stored_path is not None:
            stored_path.unlink(missing_ok=True)
        service.delete(product.id)
        return render_form(
            request,
            form.values(),
            {"image": "ذخیره تصویر انجام نشد؛ لطفاً دوباره تلاش کنید"},
            status_code=500,
        )

    return RedirectResponse(f"/admin/products/{product.id}", status_code=303)


@router.get("/{product_id}", response_class=HTMLResponse)
def product_detail(
    product_id: int,
    request: Request,
    _admin: Annotated[str, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    product = ProductRepository(db).get(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return templates.TemplateResponse(
        request=request,
        name="products/detail.html",
        context={"product": product},
    )


@router.get("/{product_id}/edit", response_class=HTMLResponse)
def edit_product_page(
    product_id: int,
    request: Request,
    _admin: Annotated[str, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    product = ProductRepository(db).get(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return render_form(request, product_values(product), {}, product=product)


@router.post("/{product_id}", response_class=HTMLResponse)
def update_product(
    product_id: int,
    request: Request,
    form: Annotated[ProductFormData, Depends(parse_product_form)],
    _admin: Annotated[str, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    image: Annotated[UploadFile | None, File()] = None,
):
    validate_csrf(request, form.csrf_token)
    repository = ProductRepository(db)
    product = repository.get(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    try:
        validated_image = read_validated_image(image, required=False)
        data = ProductUpdate(**form.product_data())
    except InvalidImage as exc:
        return render_form(
            request,
            form.values(),
            {"image": str(exc)},
            product=product,
            status_code=422,
        )
    except ValidationError as exc:
        return render_form(
            request,
            form.values(),
            validation_errors(exc),
            product=product,
            status_code=422,
        )

    service = ProductService(repository)
    stored_path = None
    try:
        if validated_image is not None:
            upload_root = request.app.state.settings.upload_dir
            stored_path = save_product_image(upload_root, product.id, validated_image)
        product = service.update(product_id, data)
        if stored_path is not None:
            relative_path = stored_path.relative_to(upload_root).as_posix()
            service.set_image(product_id, relative_path)
    except ProductNotFound as exc:
        if stored_path is not None:
            stored_path.unlink(missing_ok=True)
        raise HTTPException(status_code=404, detail="Product not found") from exc
    except Exception:
        if stored_path is not None:
            stored_path.unlink(missing_ok=True)
        return render_form(
            request,
            form.values(),
            {"image": "ذخیره تغییرات انجام نشد؛ لطفاً دوباره تلاش کنید"},
            product=product,
            status_code=500,
        )

    return RedirectResponse(f"/admin/products/{product.id}", status_code=303)
