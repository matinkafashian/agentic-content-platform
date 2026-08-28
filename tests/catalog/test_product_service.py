from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.catalog.repository import ProductRepository
from app.catalog.schemas import ProductCreate, ProductUpdate
from app.catalog.service import InvalidProductImagePath, ProductNotFound, ProductService


def test_create_product_normalizes_text_and_tags(db_session):
    service = ProductService(ProductRepository(db_session))
    product = service.create(
        ProductCreate(
            name="  میز کانتر  ",
            description="  مدل منحنی  ",
            price=Decimal("25000000"),
            availability="available",
            shipping_info="ارسال سراسر ایران",
            attributes={"جنس": "MDF"},
            tags=["دکوراسیون", " دکوراسیون ", "کانتر"],
            active=True,
        )
    )

    assert product.name == "میز کانتر"
    assert product.description == "مدل منحنی"
    assert product.tags == ["دکوراسیون", "کانتر"]


def test_product_rejects_negative_price():
    with pytest.raises(ValidationError):
        ProductCreate(name="محصول", price=Decimal("-1"))


def test_update_unknown_product_raises(db_session):
    service = ProductService(ProductRepository(db_session))

    with pytest.raises(ProductNotFound):
        service.update(999, ProductUpdate(name="نام جدید"))


def test_image_path_cannot_escape_its_product_directory(db_session):
    service = ProductService(ProductRepository(db_session))
    product = service.create(ProductCreate(name="محصول", price=Decimal("1")))

    with pytest.raises(InvalidProductImagePath):
        service.set_image(product.id, "../private/secret.png")
