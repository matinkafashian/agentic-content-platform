import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.factory import create_app


def make_settings(
    tmp_path, *, secret_key: str = "t" * 32, **overrides: object
) -> Settings:
    values: dict[str, object] = {
        "database_url": f"sqlite:///{tmp_path / 'test.db'}",
        "upload_dir": tmp_path / "uploads",
        "secret_key": secret_key,
        "admin_username": "admin",
        "admin_password_hash": "$argon2id$v=19$m=65536,t=3,p=4$invalid$invalid",
        "openai_api_key": None,
        "publishing_worker_enabled": False,
        "debug": True,
    }
    values.update(overrides)
    return Settings(**values)


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


def test_app_can_select_openai_content_provider_without_exposing_key(tmp_path):
    settings = make_settings(
        tmp_path,
        content_provider="openai",
        openai_api_key="sk-test-provider-key",
        openai_text_model="gpt-test-model",
    )

    app = create_app(settings)

    assert app.state.content_provider.name == "openai:gpt-test-model"
    assert "sk-test-provider-key" not in repr(settings)
    app.state.content_provider.close()


def test_openai_provider_requires_api_key(tmp_path):
    settings = make_settings(
        tmp_path,
        content_provider="openai",
        openai_api_key=None,
        openai_text_model="gpt-test-model",
    )

    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        create_app(settings)


def test_template_mode_treats_blank_openai_key_as_image_editor_disabled(tmp_path):
    app = create_app(
        make_settings(
            tmp_path,
            content_provider="template",
            openai_api_key="",
        )
    )

    assert app.state.image_editor is None
