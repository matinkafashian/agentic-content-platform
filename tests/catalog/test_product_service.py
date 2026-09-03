from unittest.mock import MagicMock

import pytest

from app.catalog.models import Product
from app.catalog.repository import ProductRepository
from app.catalog.schemas import ProductCreate, ProductUpdate
from app.catalog.service import InvalidProductImagePath, ProductNotFound, ProductService


def test_create_product_normalizes_text_and_tags(db_session):
    service = ProductService(ProductRepository(db_session))
    product = service.create(
        ProductCreate(
            name="  میز کانتر  ",
            description="  مدل منحنی  ",
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


def test_product_input_has_no_price_field():
    product = ProductCreate(name="محصول")

    assert "price" not in product.model_dump()


def test_update_unknown_product_raises(db_session):
    service = ProductService(ProductRepository(db_session))

    with pytest.raises(ProductNotFound):
        service.update(999, ProductUpdate(name="نام جدید"))


def test_image_path_cannot_escape_its_product_directory(db_session):
    service = ProductService(ProductRepository(db_session))
    product = service.create(ProductCreate(name="محصول"))

    with pytest.raises(InvalidProductImagePath):
        service.set_image(product.id, "../private/secret.png")


def test_set_image_persists_only_the_expected_product_subtree(db_session):
    repository = ProductRepository(db_session)
    service = ProductService(repository)
    product = service.create(ProductCreate(name="محصول"))

    updated = service.set_image(product.id, f"products/{product.id}/original/safe.png")

    assert updated.primary_image_path == f"products/{product.id}/original/safe.png"
    assert repository.get(product.id).primary_image_path == updated.primary_image_path


def test_create_rolls_back_when_commit_fails():
    repository = MagicMock(spec=ProductRepository)
    repository.commit.side_effect = RuntimeError("database unavailable")
    service = ProductService(repository)

    with pytest.raises(RuntimeError, match="database unavailable"):
        service.create(ProductCreate(name="محصول"))

    repository.commit.assert_called_once_with()
    repository.rollback.assert_called_once_with()


def test_update_rolls_back_when_commit_fails():
    repository = MagicMock(spec=ProductRepository)
    repository.get.return_value = Product(name="محصول")
    repository.commit.side_effect = RuntimeError("database unavailable")
    service = ProductService(repository)

    with pytest.raises(RuntimeError, match="database unavailable"):
        service.update(1, ProductUpdate(name="نام جدید"))

    repository.rollback.assert_called_once_with()
