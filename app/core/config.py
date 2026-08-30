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
    openai_timeout_seconds: float = Field(default=45.0, gt=0, le=180)
    openai_image_model: str = "gpt-image-2"
    openai_image_quality: Literal["low", "medium", "high"] = "high"
    openai_image_timeout_seconds: float = Field(default=180.0, gt=0, le=300)
    max_voice_bytes: int = Field(default=25 * 1024 * 1024, gt=0)
    debug: bool = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
