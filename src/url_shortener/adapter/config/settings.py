"""Application settings, read from the environment."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Everything this application needs from its environment.

    Values come from real environment variables first and from a local `.env` second. Nothing here
    has a default: a missing setting must fail loudly at startup rather than quietly run against
    the wrong database.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
    )

    database_url: str = Field(
        description="PostgreSQL DSN used by SQLAlchemy.",
    )
    base_url: str = Field(
        description="Public origin the short URLs are built from, without a trailing slash.",
    )


@lru_cache
def get_settings() -> Settings:
    """Read the settings once and reuse them on every later call."""
    return Settings()
