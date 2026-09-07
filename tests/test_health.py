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
        "content_provider": "template",
        "openai_api_key": None,
        "telegram_bot_token": None,
        "telegram_default_destination": "",
        "bale_bot_token": None,
        "bale_default_destination": "",
        "rubika_bot_token": None,
        "rubika_default_destination": "",
        "whatsapp_bridge_token": None,
        "whatsapp_bridge_token_file": tmp_path / "whatsapp-bridge-token",
        "whatsapp_default_destination": "",
        "publishing_worker_enabled": False,
        "debug": True,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_health_returns_service_status(tmp_path):
    client = TestClient(create_app(make_settings(tmp_path)))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "agentic-content-platform",
    }


def test_root_redirects_to_admin_panel(tmp_path):
    client = TestClient(create_app(make_settings(tmp_path)))

    response = client.get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/admin"


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


def test_app_registers_telegram_only_when_secret_token_is_configured(tmp_path):
    without_token = create_app(make_settings(tmp_path, telegram_bot_token=None))
    settings = make_settings(
        tmp_path,
        telegram_bot_token="123456:test-telegram-token",
        telegram_default_destination="@test_channel",
    )
    with_token = create_app(settings)

    assert set(without_token.state.platform_adapters) == {"sandbox"}
    assert set(with_token.state.platform_adapters) == {"sandbox", "telegram"}
    assert with_token.state.telegram_default_destination == "@test_channel"
    assert "test-telegram-token" not in repr(settings)
    with_token.state.platform_adapters["telegram"].close()


def test_app_registers_bale_only_when_secret_token_is_configured(tmp_path):
    without_token = create_app(
        make_settings(tmp_path, telegram_bot_token=None, bale_bot_token=None)
    )
    settings = make_settings(
        tmp_path,
        telegram_bot_token=None,
        bale_bot_token="123456:test-bale-token",
        bale_default_destination="@bale_test_channel",
    )
    with_token = create_app(settings)

    assert set(without_token.state.platform_adapters) == {"sandbox"}
    assert set(with_token.state.platform_adapters) == {"sandbox", "bale"}
    assert with_token.state.platform_default_destinations["bale"] == (
        "@bale_test_channel"
    )
    assert "test-bale-token" not in repr(settings)
    with_token.state.platform_adapters["bale"].close()


def test_app_registers_rubika_only_when_secret_token_is_configured(tmp_path):
    without_token = create_app(make_settings(tmp_path, rubika_bot_token=None))
    settings = make_settings(
        tmp_path,
        telegram_bot_token=None,
        bale_bot_token=None,
        rubika_bot_token="rubika-test-secret-token",
        rubika_default_destination="rubika-channel-chat-id",
    )
    with_token = create_app(settings)

    assert set(without_token.state.platform_adapters) == {"sandbox"}
    assert set(with_token.state.platform_adapters) == {"sandbox", "rubika"}
    assert with_token.state.platform_default_destinations["rubika"] == (
        "rubika-channel-chat-id"
    )
    assert "rubika-test-secret-token" not in repr(settings)
    with_token.state.platform_adapters["rubika"].close()


def test_app_registers_whatsapp_only_when_bridge_token_is_configured(tmp_path):
    without_token = create_app(make_settings(tmp_path, whatsapp_bridge_token=None))
    settings = make_settings(
        tmp_path,
        telegram_bot_token=None,
        bale_bot_token=None,
        rubika_bot_token=None,
        whatsapp_bridge_token="whatsapp-test-bridge-secret",
        whatsapp_default_destination="120363123456789@g.us",
    )
    with_token = create_app(settings)

    assert set(without_token.state.platform_adapters) == {"sandbox"}
    assert set(with_token.state.platform_adapters) == {"sandbox", "whatsapp"}
    assert with_token.state.platform_default_destinations["whatsapp"] == (
        "120363123456789@g.us"
    )
    assert "whatsapp-test-bridge-secret" not in repr(settings)
    with_token.state.platform_adapters["whatsapp"].close()


def test_app_can_load_whatsapp_bridge_token_from_ignored_runtime_file(tmp_path):
    token_file = tmp_path / "runtime" / "bridge-token"
    token_file.parent.mkdir()
    token_file.write_text("runtime-whatsapp-test-secret-123456", encoding="utf-8")
    settings = make_settings(
        tmp_path,
        whatsapp_bridge_token=None,
        whatsapp_bridge_token_file=token_file,
        whatsapp_default_destination="120363123456789@g.us",
    )

    app = create_app(settings)

    assert set(app.state.platform_adapters) == {"sandbox", "whatsapp"}
    app.state.platform_adapters["whatsapp"].close()
