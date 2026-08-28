import pytest
from fastapi.testclient import TestClient
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

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
        debug=True,
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def db_session(tmp_path) -> Session:
    engine = build_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    session_factory = build_session_factory(engine)

    with session_factory() as session:
        yield session

    Base.metadata.drop_all(engine)
    engine.dispose()
