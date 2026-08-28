from fastapi import FastAPI

from app.core.config import Settings


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title=settings.app_name, debug=settings.debug)
    app.state.settings = settings

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "agentic-content-platform"}

    return app
