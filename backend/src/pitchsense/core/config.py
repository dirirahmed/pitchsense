"""Application settings, read from environment variables (and .env files in development)."""

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Hosting providers (e.g. Neon) issue plain "postgresql://" or "postgres://" URLs, which
# SQLAlchemy maps to psycopg2. We use psycopg 3, so the driver is made explicit.
_PSYCOPG_SCHEME = "postgresql+psycopg://"
_PLAIN_SCHEMES = ("postgresql://", "postgres://")


class Settings(BaseSettings):
    # The repository-root .env is found when running from backend/; real environment
    # variables always take precedence over both files.
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = "development"
    database_url: str
    cors_origins: str = "http://localhost:5173"

    @field_validator("database_url")
    @classmethod
    def use_psycopg_driver(cls, value: str) -> str:
        for scheme in _PLAIN_SCHEMES:
            if value.startswith(scheme):
                return _PSYCOPG_SCHEME + value.removeprefix(scheme)
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        """CORS_ORIGINS is comma-separated so it stays a plain string in hosting dashboards."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
