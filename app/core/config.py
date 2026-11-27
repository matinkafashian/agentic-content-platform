from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Agentic Content Platform"
    app_timezone: str = "Asia/Tehran"
    database_url: str = "sqlite:///./data/app.db"
    upload_dir: Path = Path("uploads")
    secret_key: str = Field(min_length=32)
    admin_username: str = "admin"
    admin_password_hash: str
    content_provider: str = "template"
    openai_api_key: SecretStr | None = None
    openai_text_model: str = "gpt-5.4-nano"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_timeout_seconds: float = Field(default=45.0, gt=0, le=180)
    openai_image_model: str = "gpt-image-2"
    openai_image_quality: Literal["low", "medium", "high"] = "high"
    openai_image_timeout_seconds: float = Field(default=180.0, gt=0, le=300)
    max_voice_bytes: int = Field(default=25 * 1024 * 1024, gt=0)
    telegram_bot_token: SecretStr | None = None
    telegram_default_destination: str = ""
    telegram_message_thread_id: int | None = Field(default=None, ge=1)
    telegram_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    telegram_ffmpeg_binary: str = "ffmpeg"
    telegram_support_enabled: bool = False
    telegram_support_poll_timeout_seconds: int = Field(default=20, ge=1, le=50)
    telegram_support_retry_seconds: float = Field(default=3.0, ge=1.0, le=60.0)
    bale_bot_token: SecretStr | None = None
    bale_default_destination: str = ""
    bale_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    bale_support_enabled: bool = False
    rubika_bot_token: SecretStr | None = None
    rubika_default_destination: str = ""
    rubika_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    rubika_support_enabled: bool = False
    rubika_support_poll_seconds: float = Field(default=5.0, ge=1.0, le=60.0)
    whatsapp_bridge_url: str = "http://127.0.0.1:8780"
    whatsapp_bridge_token: SecretStr | None = None
    whatsapp_bridge_token_file: Path = Path(".whatsapp-runtime/bridge-token")
    whatsapp_default_destination: str = ""
    whatsapp_timeout_seconds: float = Field(default=60.0, gt=0, le=180)
    publishing_worker_enabled: bool = True
    publishing_poll_seconds: float = Field(default=15.0, ge=2.0, le=300.0)
    debug: bool = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
