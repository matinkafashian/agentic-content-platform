from fastapi import FastAPI

from app.core.config import Settings
from app.core.database import build_engine, build_session_factory


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title=settings.app_name, debug=settings.debug)
    app.state.settings = settings
    app.state.engine = build_engine(settings.database_url)
    app.state.session_factory = build_session_factory(app.state.engine)

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "agentic-content-platform"}

    return app
