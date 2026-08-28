from pathlib import PurePosixPath, PureWindowsPath

from app.catalog.models import Product
from app.catalog.repository import ProductRepository
from app.catalog.schemas import ProductCreate, ProductUpdate


class ProductNotFound(LookupError):
    def __init__(self, product_id: int) -> None:
        super().__init__(f"Product {product_id} was not found")
        self.product_id = product_id


class InvalidProductImagePath(ValueError):
    pass


class ProductService:
    def __init__(self, repository: ProductRepository) -> None:
        self.repository = repository

    def create(self, data: ProductCreate) -> Product:
        product = Product(**data.model_dump())
        try:
            self.repository.add(product)
            self.repository.commit()
            self.repository.refresh(product)
        except Exception:
            self.repository.rollback()
            raise
        return product

    def update(self, product_id: int, data: ProductUpdate) -> Product:
        product = self._required_product(product_id)
        try:
            for field, value in data.model_dump(exclude_unset=True).items():
                setattr(product, field, value)
            self.repository.commit()
            self.repository.refresh(product)
        except Exception:
            self.repository.rollback()
            raise
        return product

    def set_image(self, product_id: int, path: str) -> Product:
        product = self._required_product(product_id)
        safe_path = self._validated_image_path(product_id, path)
        try:
            product.primary_image_path = safe_path
            self.repository.commit()
            self.repository.refresh(product)
        except Exception:
            self.repository.rollback()
            raise
        return product

    def delete(self, product_id: int) -> None:
        product = self._required_product(product_id)
        try:
            self.repository.delete(product)
            self.repository.commit()
        except Exception:
            self.repository.rollback()
            raise

    def _required_product(self, product_id: int) -> Product:
        product = self.repository.get(product_id)
        if product is None:
            self.repository.rollback()
            raise ProductNotFound(product_id)
        return product

    @staticmethod
    def _validated_image_path(product_id: int, path: str) -> str:
        normalized = path.replace("\\", "/")
        candidate = PurePosixPath(normalized)
        windows_candidate = PureWindowsPath(path)
        expected_prefix = ("products", str(product_id))
        if (
            not normalized
            or candidate.is_absolute()
            or windows_candidate.is_absolute()
            or ".." in candidate.parts
            or candidate.parts[:2] != expected_prefix
        ):
            raise InvalidProductImagePath("image path must stay inside the product directory")
        return candidate.as_posix()
