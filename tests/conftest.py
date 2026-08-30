import re
from decimal import Decimal
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.catalog.models import Product
from app.core.config import Settings
from app.core.database import Base, build_engine, build_session_factory
from app.factory import create_app


@pytest.fixture(scope="session")
def admin_credentials() -> dict[str, str]:
    return {
        "username": "admin",
        "password": "correct-password",
        "password_hash": PasswordHash.recommended().hash("correct-password"),
    }


@pytest.fixture
def client(tmp_path, admin_credentials) -> TestClient:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        upload_dir=tmp_path / "uploads",
        secret_key="test-secret-key-that-is-at-least-32-characters",
        admin_username=admin_credentials["username"],
        admin_password_hash=admin_credentials["password_hash"],
        openai_api_key=None,
        publishing_worker_enabled=False,
        debug=True,
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as test_client:
        yield test_client
    Base.metadata.drop_all(app.state.engine)
    app.state.engine.dispose()


def _extract_csrf(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match is not None, "CSRF field was not rendered"
    return match.group(1)


@pytest.fixture
def authenticated_client(client) -> TestClient:
    login_page = client.get("/admin/login")
    response = client.post(
        "/admin/login",
        data={
            "username": "admin",
            "password": "correct-password",
            "csrf_token": _extract_csrf(login_page.text),
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    return client


@pytest.fixture
def csrf_token(authenticated_client) -> str:
    return _extract_csrf(authenticated_client.get("/admin").text)


@pytest.fixture
def png_upload() -> bytes:
    output = BytesIO()
    Image.new("RGB", (32, 32), "white").save(output, format="PNG")
    return output.getvalue()


@pytest.fixture
def db_session(tmp_path) -> Session:
    engine = build_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    session_factory = build_session_factory(engine)

    with session_factory() as session:
        yield session

    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def product(authenticated_client) -> Product:
    session_factory = authenticated_client.app.state.session_factory
    with session_factory() as session:
        item = Product(
            name="درب ممبران مدل آریا",
            description="طراحی نئوکلاسیک با خطوط عمودی",
            price=Decimal("12500000"),
            availability="available",
            shipping_info="ارسال به سراسر ایران",
            attributes={"متریال": "MDF"},
            tags=["درب ممبران", "نئوکلاسیک"],
            active=True,
        )
        session.add(item)
        session.commit()
        session.refresh(item)
        return item
