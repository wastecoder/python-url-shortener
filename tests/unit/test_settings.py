"""The settings are read from the environment, and refuse to be guessed."""

import pytest
from pydantic import ValidationError

from url_shortener.adapter.config.settings import Settings


def test_settings_come_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Given DATABASE_URL and BASE_URL present in the environment,
    when the settings are built,
    then both values are read from it.
    """
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/db")
    monkeypatch.setenv("BASE_URL", "http://localhost:8000")

    settings = Settings()

    assert settings.database_url == "postgresql+psycopg://user:pass@localhost:5432/db"
    assert settings.base_url == "http://localhost:8000"


def test_a_missing_setting_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Given BASE_URL missing from the environment,
    when the settings are built,
    then construction fails instead of falling back to a default.
    """
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/db")
    monkeypatch.delenv("BASE_URL", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
