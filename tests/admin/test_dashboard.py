from decimal import Decimal

from app.catalog.models import Product


def test_dashboard_has_useful_phase_one_metrics(authenticated_client):
    with authenticated_client.app.state.session_factory() as session:
        session.add_all(
            [
                Product(name="محصول فعال", price=Decimal("100"), active=True),
                Product(name="محصول غیرفعال", price=Decimal("200"), active=False),
            ]
        )
        session.commit()

    response = authenticated_client.get("/admin")

    assert response.status_code == 200
    assert 'dir="rtl"' in response.text
    assert 'data-metric="total-products"' in response.text
    assert 'data-metric="active-products"' in response.text
    assert 'data-value="2"' in response.text
    assert 'data-value="1"' in response.text
    assert 'data-action="create-product"' in response.text
    assert 'aria-label="ناوبری اصلی"' in response.text
    assert "Pause All Publishing" not in response.text


def test_dashboard_static_assets_are_served(authenticated_client):
    stylesheet = authenticated_client.get("/static/css/app.css")
    script = authenticated_client.get("/static/js/app.js")

    assert stylesheet.status_code == 200
    assert "--color-accent" in stylesheet.text
    assert script.status_code == 200
    assert "data-nav-toggle" in script.text
