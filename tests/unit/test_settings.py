"""The settings are read from the environment, and refuse to be guessed."""

import pytest
from pydantic import ValidationError

from url_shortener.adapter.config.settings import Settings, get_settings


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


def test_the_settings_are_read_once_and_reused(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Given the environment carrying both settings,
    when `get_settings` is called twice,
    then both calls hand back the same object.

    This is the production path and it had no test: `create_app()` with no argument leaves the
    lifespan to call this function, so it is what a process started by uvicorn actually runs. The
    identity assertion is the point of the `lru_cache` -- reading and validating the environment on
    every request would be work repeated for a value that cannot change while the process lives.

    The cache is cleared on both sides. It is process-wide state, so a value left in it would
    travel into whatever test runs next, and a value left there *by* another test would make this
    one pass without reading anything.
    """
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/db")
    monkeypatch.setenv("BASE_URL", "https://sho.rt")
    get_settings.cache_clear()

    try:
        first = get_settings()
        second = get_settings()

        assert first is second
        assert first.base_url == "https://sho.rt"
    finally:
        get_settings.cache_clear()
