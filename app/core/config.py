from functools import lru_cache
from pathlib import Path

from pydantic import Field
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
    debug: bool = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
