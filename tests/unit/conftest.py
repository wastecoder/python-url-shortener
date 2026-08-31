"""Fixtures for the API tests: the real application, with the driven ports swapped for fakes.

What is overridden here is deliberately narrow: the three **driven** ports -- the two repositories
and the clock -- plus the health probe, which is the one thing `/health` asks about. The settings
are not overridden at all; they are handed to `create_app`. Neither are the use cases, so every one
of these tests runs the real `CreateLinkUseCaseImpl`, the real deduplication flow and the real
wiring in `dependencies.py`.

FastAPI resolves overrides through sub-dependencies, so replacing a leaf is enough -- and that is
why none of these tests opens a database connection despite the application being wired to
PostgreSQL: `get_session` sits *under* the repositories that were replaced, so it is never
resolved at all.

The app is built per test by `create_app()`. `dependency_overrides` is state on the app object, so
sharing one app across tests would leak one test's fakes into the next.
"""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.fakes import (
    FixedClock,
    InMemoryClickRepository,
    InMemoryLinkRepository,
    StubHealthProbe,
)
from url_shortener.adapter.config.dependencies import (
    get_click_repository,
    get_clock,
    get_health_probe,
    get_link_repository,
)
from url_shortener.adapter.config.settings import Settings
from url_shortener.main import create_app

BASE_URL = "https://sho.rt"
NOW = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)
# How that instant looks once Pydantic has serialised it: RFC 3339, with the UTC offset
# written as `Z` rather than as `+00:00`. Both spell the same instant; only one is what the
# API actually puts on the wire, and a test that guesses is a test that passes for the wrong
# reason.
NOW_ON_THE_WIRE = "2026-08-31T12:00:00Z"
CLIENT_ADDRESS = "203.0.113.7"
CLIENT_PORT = 51234


@pytest.fixture
def links() -> InMemoryLinkRepository:
    """The `link` table, empty."""
    return InMemoryLinkRepository()


@pytest.fixture
def clicks() -> InMemoryClickRepository:
    """The `click` table, empty."""
    return InMemoryClickRepository()


@pytest.fixture
def clock() -> FixedClock:
    """A clock frozen at a known instant, so a response body can be asserted exactly."""
    return FixedClock(NOW)


@pytest.fixture
def probe() -> StubHealthProbe:
    """A health probe reporting the database as answering, which tests can flip."""
    return StubHealthProbe()


@pytest.fixture
def settings() -> Settings:
    """Settings built in the test rather than read from the environment.

    `_env_file=None` keeps a developer's local `.env` out of the run: with it, the origin the
    short URLs are built from would depend on whose machine the suite is on.
    """
    return Settings(
        _env_file=None,
        database_url="postgresql+psycopg://unused:unused@localhost:5432/unused",
        base_url=BASE_URL,
    )


@pytest.fixture
def app(
    links: InMemoryLinkRepository,
    clicks: InMemoryClickRepository,
    clock: FixedClock,
    probe: StubHealthProbe,
    settings: Settings,
) -> FastAPI:
    """The real application, with only its driven ports replaced.

    The settings are handed to `create_app` and **not** overridden as a dependency, and that is a
    correction rather than a simplification: an adversarial review found that `SettingsDep` used to
    call the environment reader on every request, so an application built with explicit settings
    still consulted the environment and only this override hid it. The startup hook now stores what
    it was given and `SettingsDep` reads it back, so one object serves both -- the engine's DSN and
    the origin `short_url` is built from. The DSN points at nothing, and nothing ever connects to
    it: building an engine opens no socket.
    """
    application = create_app(settings=settings)
    application.dependency_overrides[get_link_repository] = lambda: links
    application.dependency_overrides[get_click_repository] = lambda: clicks
    application.dependency_overrides[get_clock] = lambda: clock
    application.dependency_overrides[get_health_probe] = lambda: probe
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """A client that never follows a redirect and reports a routable address.

    `follow_redirects=False` is not a preference, and the reason is **not** the network -- which
    is what this paragraph used to say, until Fase 5 measured it. The test client dispatches every
    request through its one ASGI transport whatever host the URL names, so the hop never leaves the
    process and no name is ever resolved. It re-enters *this* application, where the target URL
    matches the catch-all `GET /{code}` and answers `404`; the `302` and its `Location` end up in
    `response.history`, where the assertions naming them cannot see them.

    `client=` fixes the peer address, which is what the redirect controller reads to fill
    `Click.ip`. The default the test client reports is the literal string `testclient`, which does
    not parse as an address, so without this every click in the suite would record `None` and the
    parsing would never be exercised.
    """
    with TestClient(
        app, follow_redirects=False, client=(CLIENT_ADDRESS, CLIENT_PORT)
    ) as test_client:
        yield test_client
