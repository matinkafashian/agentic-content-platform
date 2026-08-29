import mimetypes
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.admin.routes import router as admin_router
from app.catalog.routes import router as catalog_router
from app.core.config import Settings
from app.core.database import build_engine, build_session_factory
from app.core.logging import configure_logging


def create_app(settings: Settings) -> FastAPI:
    mimetypes.add_type("font/woff2", ".woff2")
    configure_logging(debug=settings.debug)
    app = FastAPI(title=settings.app_name, debug=settings.debug)
    app.state.settings = settings
    app.state.engine = build_engine(settings.database_url)
    app.state.session_factory = build_session_factory(app.state.engine)
    product_upload_root = settings.upload_dir / "products"
    product_upload_root.mkdir(parents=True, exist_ok=True)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        same_site="lax",
        https_only=not settings.debug,
    )
    app.include_router(admin_router)
    app.include_router(catalog_router)
    app.mount(
        "/uploads/products",
        StaticFiles(directory=product_upload_root),
        name="product-uploads",
    )
    app.mount(
        "/static",
        StaticFiles(directory=Path(__file__).resolve().parent / "static"),
        name="static",
    )

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "agentic-content-platform"}

    return app
