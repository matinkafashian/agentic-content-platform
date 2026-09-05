from pathlib import Path

from app.core.config import Settings

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy"


def _environment_keys(path: Path) -> set[str]:
    return {
        line.split("=", 1)[0]
        for line in path.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#") and "=" in line
    }


def test_production_environment_documents_every_application_setting():
    documented = _environment_keys(DEPLOY / "app.env.example")
    expected = {name.upper() for name in Settings.model_fields}

    assert expected <= documented


def test_production_services_prevent_duplicate_workers_and_public_bindings():
    app_service = (DEPLOY / "hayka-app.service").read_text(encoding="utf-8")
    whatsapp_service = (DEPLOY / "hayka-whatsapp.service").read_text(encoding="utf-8")
    compose = (DEPLOY / "compose.n8n.yml").read_text(encoding="utf-8")

    assert "--workers 1" in app_service
    assert "--host 127.0.0.1" in app_service
    assert "alembic upgrade head" in app_service
    assert "127.0.0.1:8780" not in whatsapp_service
    assert '"127.0.0.1:5678:5678"' in compose
    assert "n8nio/n8n:${N8N_VERSION}" in compose
    assert "n8nio/n8n:latest" not in compose


def test_reverse_proxy_requires_https_for_panel_and_n8n():
    nginx = (DEPLOY / "nginx.conf.example").read_text(encoding="utf-8")

    assert nginx.count("return 301 https://$host$request_uri;") == 2
    assert "proxy_pass http://127.0.0.1:8000;" in nginx
    assert "proxy_pass http://127.0.0.1:5678;" in nginx
