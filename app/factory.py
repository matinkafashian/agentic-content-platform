import asyncio
import mimetypes
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
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
from app.media.openai_image_editor import OpenAIImageEditor
from app.publishing.adapters import SandboxAdapter
from app.publishing.bale import BaleAdapter
from app.publishing.routes import router as publishing_router
from app.publishing.rubika import RubikaAdapter
from app.publishing.telegram import TelegramAdapter, TelegramVoicePreparer
from app.publishing.whatsapp import WhatsAppAdapter
from app.publishing.worker import PublishingWorker, stop_worker
from app.support.bale import BaleSupportBot
from app.support.openai_provider import OpenAISupportProvider
from app.support.routes import router as support_router
from app.support.rubika import RubikaSupportBot
from app.support.telegram import TelegramSupportBot


def create_app(settings: Settings) -> FastAPI:
    mimetypes.add_type("font/woff2", ".woff2")
    configure_logging(debug=settings.debug)
    openai_api_key = (
        settings.openai_api_key.get_secret_value().strip()
        if settings.openai_api_key is not None
        else ""
    )
    if settings.content_provider == "template":
        provider = TemplateContentProvider()
    elif settings.content_provider == "openai":
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when CONTENT_PROVIDER=openai")
        provider = OpenAIContentProvider(
            api_key=openai_api_key,
            model=settings.openai_text_model,
            timeout_seconds=settings.openai_timeout_seconds,
        )
    else:
        raise ValueError("CONTENT_PROVIDER must be either 'template' or 'openai'")

    image_editor = None
    support_provider = None
    if openai_api_key:
        image_editor = OpenAIImageEditor(
            api_key=openai_api_key,
            model=settings.openai_image_model,
            quality=settings.openai_image_quality,
            timeout_seconds=settings.openai_image_timeout_seconds,
        )
        support_provider = OpenAISupportProvider(
            api_key=openai_api_key,
            model=settings.openai_text_model,
            embedding_model=settings.openai_embedding_model,
            timeout_seconds=settings.openai_timeout_seconds,
        )

    telegram_bot_token = (
        settings.telegram_bot_token.get_secret_value().strip()
        if settings.telegram_bot_token is not None
        else ""
    )
    platform_adapters = {"sandbox": SandboxAdapter()}
    telegram_adapter = None
    if telegram_bot_token:
        telegram_adapter = TelegramAdapter(
            bot_token=telegram_bot_token,
            upload_root=settings.upload_dir,
            timeout_seconds=settings.telegram_timeout_seconds,
            voice_preparer=TelegramVoicePreparer(
                ffmpeg_binary=settings.telegram_ffmpeg_binary
            ),
        )
        platform_adapters["telegram"] = telegram_adapter

    bale_bot_token = (
        settings.bale_bot_token.get_secret_value().strip()
        if settings.bale_bot_token is not None
        else ""
    )
    bale_adapter = None
    if bale_bot_token:
        bale_adapter = BaleAdapter(
            bot_token=bale_bot_token,
            upload_root=settings.upload_dir,
            timeout_seconds=settings.bale_timeout_seconds,
            voice_preparer=TelegramVoicePreparer(
                ffmpeg_binary=settings.telegram_ffmpeg_binary
            ),
        )
        platform_adapters["bale"] = bale_adapter

    rubika_bot_token = (
        settings.rubika_bot_token.get_secret_value().strip()
        if settings.rubika_bot_token is not None
        else ""
    )
    rubika_adapter = None
    if rubika_bot_token:
        rubika_adapter = RubikaAdapter(
            bot_token=rubika_bot_token,
            upload_root=settings.upload_dir,
            timeout_seconds=settings.rubika_timeout_seconds,
        )
        platform_adapters["rubika"] = rubika_adapter

    whatsapp_bridge_token = (
        settings.whatsapp_bridge_token.get_secret_value().strip()
        if settings.whatsapp_bridge_token is not None
        else ""
    )
    if not whatsapp_bridge_token:
        with suppress(FileNotFoundError):
            whatsapp_bridge_token = (
                settings.whatsapp_bridge_token_file.read_text(encoding="utf-8").strip()
            )
    whatsapp_adapter = None
    if whatsapp_bridge_token:
        whatsapp_adapter = WhatsAppAdapter(
            bridge_url=settings.whatsapp_bridge_url,
            bridge_token=whatsapp_bridge_token,
            upload_root=settings.upload_dir,
            timeout_seconds=settings.whatsapp_timeout_seconds,
        )
        platform_adapters["whatsapp"] = whatsapp_adapter

    telegram_support_bot = None
    bale_support_bot = None
    rubika_support_bot = None

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        worker_task = None
        support_tasks = []
        if settings.publishing_worker_enabled:
            worker = PublishingWorker(
                _app.state.session_factory,
                settings.upload_dir,
                _app.state.platform_adapters,
                poll_seconds=settings.publishing_poll_seconds,
            )
            worker_task = asyncio.create_task(worker.run_forever())
        for support_bot in (
            telegram_support_bot,
            bale_support_bot,
            rubika_support_bot,
        ):
            if support_bot is not None:
                support_tasks.append(asyncio.create_task(support_bot.run_forever()))
        try:
            yield
        finally:
            await stop_worker(worker_task)
            for support_task in support_tasks:
                await stop_worker(support_task)
            for resource in (
                provider,
                image_editor,
                telegram_adapter,
                bale_adapter,
                rubika_adapter,
                whatsapp_adapter,
                support_provider,
                telegram_support_bot,
                bale_support_bot,
                rubika_support_bot,
            ):
                close = getattr(resource, "close", None)
                if close is not None:
                    close()

    app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = build_engine(settings.database_url)
    app.state.session_factory = build_session_factory(app.state.engine)
    app.state.content_provider = provider
    app.state.image_editor = image_editor
    app.state.support_provider = support_provider
    app.state.platform_adapters = platform_adapters
    if settings.telegram_support_enabled:
        if not telegram_bot_token:
            raise ValueError(
                "TELEGRAM_BOT_TOKEN is required when TELEGRAM_SUPPORT_ENABLED=true"
            )
        if support_provider is None:
            raise ValueError(
                "OPENAI_API_KEY is required when TELEGRAM_SUPPORT_ENABLED=true"
            )
        telegram_support_bot = TelegramSupportBot(
            bot_token=telegram_bot_token,
            session_factory=app.state.session_factory,
            provider=support_provider,
            poll_timeout_seconds=settings.telegram_support_poll_timeout_seconds,
            retry_seconds=settings.telegram_support_retry_seconds,
        )
    app.state.telegram_support_bot = telegram_support_bot
    if settings.bale_support_enabled:
        if not bale_bot_token:
            raise ValueError(
                "BALE_BOT_TOKEN is required when BALE_SUPPORT_ENABLED=true"
            )
        if support_provider is None:
            raise ValueError(
                "OPENAI_API_KEY is required when BALE_SUPPORT_ENABLED=true"
            )
        bale_support_bot = BaleSupportBot(
            bot_token=bale_bot_token,
            session_factory=app.state.session_factory,
            provider=support_provider,
            poll_timeout_seconds=settings.telegram_support_poll_timeout_seconds,
            retry_seconds=settings.telegram_support_retry_seconds,
        )
    app.state.bale_support_bot = bale_support_bot
    if settings.rubika_support_enabled:
        if not rubika_bot_token:
            raise ValueError(
                "RUBIKA_BOT_TOKEN is required when RUBIKA_SUPPORT_ENABLED=true"
            )
        if support_provider is None:
            raise ValueError(
                "OPENAI_API_KEY is required when RUBIKA_SUPPORT_ENABLED=true"
            )
        rubika_support_bot = RubikaSupportBot(
            bot_token=rubika_bot_token,
            session_factory=app.state.session_factory,
            provider=support_provider,
            retry_seconds=settings.telegram_support_retry_seconds,
            poll_interval_seconds=settings.rubika_support_poll_seconds,
        )
    app.state.rubika_support_bot = rubika_support_bot
    app.state.telegram_default_destination = settings.telegram_default_destination.strip()
    app.state.platform_default_destinations = {
        "sandbox": "کانال آزمایشی",
        "telegram": settings.telegram_default_destination.strip(),
        "bale": settings.bale_default_destination.strip(),
        "rubika": settings.rubika_default_destination.strip(),
        "whatsapp": settings.whatsapp_default_destination.strip(),
    }
    product_upload_root = settings.upload_dir / "products"
    product_upload_root.mkdir(parents=True, exist_ok=True)
    (settings.upload_dir / "private" / "voices").mkdir(parents=True, exist_ok=True)
    (settings.upload_dir / "private" / "edited_images").mkdir(
        parents=True, exist_ok=True
    )
    (settings.upload_dir / "private" / "bundles").mkdir(parents=True, exist_ok=True)
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
    app.include_router(publishing_router)
    app.include_router(support_router)
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

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse("/admin")

    return app
