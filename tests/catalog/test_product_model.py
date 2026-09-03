from app.catalog.models import Product


def test_product_round_trip(db_session):
    product = Product(
        name="میز کانتر",
        description="کانتر چوبی با نمای شیاردار",
        availability="available",
        shipping_info="ارسال سراسر ایران",
        attributes={"material": "MDF"},
        tags=["کانتر", "دکوراسیون"],
        active=True,
    )
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)

    assert product.id is not None
    assert product.legacy_price == 0
    assert product.attributes == {"material": "MDF"}
    assert product.tags == ["کانتر", "دکوراسیون"]
    assert product.created_at.tzinfo is not None
