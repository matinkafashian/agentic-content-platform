import mimetypes
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.admin.routes import router as admin_router
from app.brand.routes import router as brand_router
from app.catalog.routes import router as catalog_router
from app.content.openai_provider import OpenAIContentProvider
from app.content.providers import TemplateContentProvider
from app.content.routes import router as content_router
from app.core.config import Settings
from app.core.database import build_engine, build_session_factory
from app.core.logging import configure_logging


def create_app(settings: Settings) -> FastAPI:
    mimetypes.add_type("font/woff2", ".woff2")
    configure_logging(debug=settings.debug)
    if settings.content_provider == "template":
        provider = TemplateContentProvider()
    elif settings.content_provider == "openai":
        if settings.openai_api_key is None:
            raise ValueError("OPENAI_API_KEY is required when CONTENT_PROVIDER=openai")
        provider = OpenAIContentProvider(
            api_key=settings.openai_api_key.get_secret_value(),
            model=settings.openai_text_model,
            timeout_seconds=settings.openai_timeout_seconds,
        )
    else:
        raise ValueError("CONTENT_PROVIDER must be either 'template' or 'openai'")

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        close = getattr(provider, "close", None)
        if close is not None:
            close()

    app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = build_engine(settings.database_url)
    app.state.session_factory = build_session_factory(app.state.engine)
    app.state.content_provider = provider
    product_upload_root = settings.upload_dir / "products"
    product_upload_root.mkdir(parents=True, exist_ok=True)
    (settings.upload_dir / "private" / "voices").mkdir(parents=True, exist_ok=True)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        same_site="lax",
        https_only=not settings.debug,
    )
    app.include_router(admin_router)
    app.include_router(catalog_router)
    app.include_router(brand_router)
    app.include_router(content_router)
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
