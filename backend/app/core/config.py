from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "说明书核对系统"
    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    database_url: str = "sqlite:///./data/app.db"
    data_root: Path = Path("./data")
    frontend_origin: str = "http://localhost:5173"

    openai_api_key: str | None = Field(default=None, repr=False)
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str | None = None
    openai_agents_disable_tracing: bool = True
    model_max_concurrency: int = Field(default=3, ge=1, le=20)
    model_timeout_seconds: int = Field(default=90, ge=1)
    model_max_retries: int = Field(default=2, ge=0, le=10)

    reviewer_name: str = "本地用户"
    retention_days: int | None = Field(default=None, ge=1)

    @property
    def tasks_root(self) -> Path:
        return self.data_root / "tasks"


@lru_cache
def get_settings() -> Settings:
    return Settings()
