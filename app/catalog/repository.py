from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.catalog.models import Product


class ProductRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(self, *, limit: int | None = None) -> list[Product]:
        statement = select(Product).order_by(Product.created_at.desc())
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.session.scalars(statement))

    def count(self, *, active: bool | None = None) -> int:
        statement = select(func.count(Product.id))
        if active is not None:
            statement = statement.where(Product.active.is_(active))
        return int(self.session.scalar(statement) or 0)

    def count_with_image(self) -> int:
        statement = select(func.count(Product.id)).where(Product.primary_image_path.is_not(None))
        return int(self.session.scalar(statement) or 0)

    def get(self, product_id: int) -> Product | None:
        return self.session.get(Product, product_id)

    def add(self, product: Product) -> None:
        self.session.add(product)

    def delete(self, product: Product) -> None:
        self.session.delete(product)

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()

    def refresh(self, product: Product) -> None:
        self.session.refresh(product)
