import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.factory import create_app


def make_settings(tmp_path, *, secret_key: str = "t" * 32) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        upload_dir=tmp_path / "uploads",
        secret_key=secret_key,
        admin_username="admin",
        admin_password_hash="$argon2id$v=19$m=65536,t=3,p=4$invalid$invalid",
        debug=True,
    )


def test_health_returns_service_status(tmp_path):
    client = TestClient(create_app(make_settings(tmp_path)))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "agentic-content-platform",
    }


def test_settings_reject_short_secret(tmp_path):
    with pytest.raises(ValidationError, match="secret_key"):
        make_settings(tmp_path, secret_key="short")
